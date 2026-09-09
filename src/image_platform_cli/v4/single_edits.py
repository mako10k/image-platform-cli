"""Request and evidence helpers for supported single-command V4 image operations."""

import base64
import hashlib
import json
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import read_image
from ..common.models import DeterministicEditResult
from .campaigns import number
from .image_results import decode_output


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def single_edit_program() -> dict[str, Any]:
    program: dict[str, Any] = json.loads(
        files("image_platform_cli.v4").joinpath("conversion_program.json").read_text()
    )
    return program


def prepare_single_edit(
    path: Path, program: dict[str, Any], *, extra_inputs: Mapping[str, Path] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = {"source": path}
    if extra_inputs:
        if "source" in extra_inputs:
            raise ApiError("extra inputs cannot replace the source")
        paths.update(extra_inputs)
    if set(paths) != set(program["inputs"]):
        raise ApiError("image inputs must match the requested program")
    inputs: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    source: dict[str, Any] = {}
    for name, input_path in paths.items():
        raw, mime, width, height = read_image(input_path)
        hashes[name] = hashlib.sha256(raw).hexdigest()
        inputs[name] = {"mime_type": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
        if name == "source":
            source = {"sha256": hashes[name], "width": width, "height": height}
    source["input_sha256s"] = hashes
    return {"program": program, "inputs": inputs}, source


def verify_single_edit(
    response: httpx.Response,
    data: dict[str, Any],
    program: dict[str, Any],
    source: dict[str, Any],
    output_size: tuple[int, int],
) -> DeterministicEditResult:
    try:
        cost = number(data["actual_cost_usd"])
        number(data["estimated_cost_usd"])
    except ApiError as error:
        raise ApiError("image operation costs must be finite and nonnegative") from error
    raw = decode_output(data)
    image, receipt = data["image"], data["receipt"]
    program_hash = canonical_hash(program)
    requested_command = program["commands"][0]
    expected = {
        "input_sha256s": source["input_sha256s"],
        "program_sha256": program_hash,
        "output_sha256": image["sha256"],
        "output_width": output_size[0],
        "output_height": output_size[1],
    }
    if any(receipt[key] != value for key, value in expected.items()):
        raise ApiError("image operation receipt disagrees with the input or output")
    command = receipt["commands"]
    if len(command) != 1 or any(
        command[0][key] != value
        for key, value in {
            "id": requested_command["id"],
            "op": requested_command["op"],
            "normalized_command_sha256": canonical_hash(program["commands"][0]),
        }.items()
    ):
        raise ApiError("image operation command receipt disagrees with the request")
    if (image["mime_type"], image["width"], image["height"]) != (
        f"image/{program['encoding']['format']}",
        *output_size,
    ):
        raise ApiError("image operation output format or geometry disagrees with the request")
    verify_single_edit_headers(response, image, receipt)
    verify_single_edit_planner(
        response, data["planner_receipt"], program_hash, source, requested_command["id"]
    )
    return DeterministicEditResult(
        raw,
        image["mime_type"],
        image["sha256"],
        image["width"],
        image["height"],
        program_hash,
        cost,
        (
            (
                requested_command["id"],
                requested_command["op"],
                command[0]["normalized_command_sha256"],
                command[0]["output_pixel_sha256"],
            ),
        ),
    )


def verify_single_edit_headers(
    response: httpx.Response, image: dict[str, Any], receipt: dict[str, Any]
) -> None:
    expected = {
        "x-image-sha256": image["sha256"],
        "x-image-width": str(image["width"]),
        "x-image-height": str(image["height"]),
        "x-image-program-sha256": receipt["program_sha256"],
        "x-image-implementation-revision": receipt["implementation_revision"],
    }
    if any(response.headers[key] != value for key, value in expected.items()):
        raise ApiError("image operation headers disagree with the receipt")


def verify_single_edit_planner(
    response: httpx.Response,
    planner: dict[str, Any] | None,
    program_hash: str,
    source: dict[str, Any],
    command_id: str,
) -> None:
    if planner is None:
        if any(
            key in response.headers
            for key in ("x-image-logical-program-sha256", "x-image-physical-graph-sha256")
        ):
            raise ApiError("image operation planner headers lack a receipt")
        return
    nodes = planner["nodes"]
    expected_node = {
        "program_sha256": program_hash,
        "width": source["width"],
        "height": source["height"],
        "command_ids": [command_id],
    }
    if (
        planner["logical_program_sha256"] != program_hash
        or len(nodes) != 1
        or any(nodes[0][key] != value for key, value in expected_node.items())
    ):
        raise ApiError("image operation planner receipt disagrees with the request")
    for field in ("logical_program_sha256", "physical_graph_sha256"):
        key = "x-image-" + field.replace("_", "-")
        if response.headers.get(key) != planner[field]:
            raise ApiError("image operation planner headers disagree with the receipt")
