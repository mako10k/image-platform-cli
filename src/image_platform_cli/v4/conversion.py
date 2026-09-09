"""Pinned single-command conversion through the V4 image-operations contract."""

import base64
import hashlib
import json
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


def prepare_conversion(
    path: Path, format_name: str, quality: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if format_name not in {"png", "jpeg", "webp"}:
        raise ApiError("conversion format must be png, jpeg or webp")
    if isinstance(quality, bool) or not 1 <= quality <= 100:
        raise ApiError("quality must be from 1 through 100")
    if format_name == "png" and quality != 90:
        raise ApiError("quality is not configurable for PNG")
    program = json.loads(
        files("image_platform_cli.v4").joinpath("conversion_program.json").read_text()
    )
    program["encoding"].update(format=format_name, quality=quality)
    raw, mime, width, height = read_image(path)
    payload = {
        "program": program,
        "inputs": {
            "source": {"mime_type": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
        },
    }
    return payload, {"sha256": hashlib.sha256(raw).hexdigest(), "width": width, "height": height}


def verify_conversion(
    response: httpx.Response, data: dict[str, Any], program: dict[str, Any], source: dict[str, Any]
) -> DeterministicEditResult:
    try:
        cost = number(data["actual_cost_usd"])
        number(data["estimated_cost_usd"])
    except ApiError as error:
        raise ApiError("conversion costs must be finite and nonnegative") from error
    raw = decode_output(data)
    image, receipt = data["image"], data["receipt"]
    program_hash = canonical_hash(program)
    expected = {
        "input_sha256s": {"source": source["sha256"]},
        "program_sha256": program_hash,
        "output_sha256": image["sha256"],
        "output_width": source["width"],
        "output_height": source["height"],
    }
    if any(receipt[key] != value for key, value in expected.items()):
        raise ApiError("conversion receipt disagrees with the input or output")
    command = receipt["commands"]
    if len(command) != 1 or any(
        command[0][key] != value
        for key, value in {
            "id": "convert",
            "op": "convert",
            "normalized_command_sha256": canonical_hash(program["commands"][0]),
        }.items()
    ):
        raise ApiError("conversion command receipt disagrees with the request")
    if (image["mime_type"], image["width"], image["height"]) != (
        f"image/{program['encoding']['format']}",
        source["width"],
        source["height"],
    ):
        raise ApiError("conversion output format or geometry disagrees with the request")
    verify_conversion_headers(response, image, receipt)
    verify_conversion_planner(response, data["planner_receipt"], program_hash, source)
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
                "convert",
                "convert",
                command[0]["normalized_command_sha256"],
                command[0]["output_pixel_sha256"],
            ),
        ),
    )


def verify_conversion_headers(
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
        raise ApiError("conversion headers disagree with the receipt")


def verify_conversion_planner(
    response: httpx.Response,
    planner: dict[str, Any] | None,
    program_hash: str,
    source: dict[str, Any],
) -> None:
    if planner is None:
        if any(
            key in response.headers
            for key in ("x-image-logical-program-sha256", "x-image-physical-graph-sha256")
        ):
            raise ApiError("conversion planner headers lack a receipt")
        return
    nodes = planner["nodes"]
    expected_node = {
        "program_sha256": program_hash,
        "width": source["width"],
        "height": source["height"],
        "command_ids": ["convert"],
    }
    if (
        planner["logical_program_sha256"] != program_hash
        or len(nodes) != 1
        or any(nodes[0][key] != value for key, value in expected_node.items())
    ):
        raise ApiError("conversion planner receipt disagrees with the request")
    for field in ("logical_program_sha256", "physical_graph_sha256"):
        key = "x-image-" + field.replace("_", "-")
        if response.headers.get(key) != planner[field]:
            raise ApiError("conversion planner headers disagree with the receipt")
