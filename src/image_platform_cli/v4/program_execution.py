"""V4 deterministic program input binding and execution receipt validation."""

import base64
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import read_image
from ..common.models import DeterministicEditResult
from .campaigns import number
from .image_results import decode_output
from .single_edits import canonical_hash, verify_single_edit_headers


def prepare_program(
    program: dict[str, Any], paths: Mapping[str, Path]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(paths) != set(program["inputs"]):
        raise ApiError("input bindings must exactly match the program")
    inputs, metadata = {}, {}
    for name, path in paths.items():
        raw, mime, width, height = read_image(path)
        inputs[name] = {"mime_type": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
        metadata[name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "width": width,
            "height": height,
        }
    return {"program": program, "inputs": inputs}, metadata


def verify_planner(
    response: httpx.Response, planner: dict[str, Any] | None, program: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool]:
    commands = program["commands"]
    final_commands = commands
    split = False
    if planner is not None:
        if planner["logical_program_sha256"] != canonical_hash(program):
            raise ApiError("planner logical program differs from the request")
        nodes = planner["nodes"]
        identifiers = [command["id"] for command in commands]
        if not nodes or [key for node in nodes for key in node["command_ids"]] != identifiers:
            raise ApiError("planner command ordering differs from the request")
        cursor = 0
        for index, node in enumerate(nodes):
            group = commands[cursor : cursor + len(node["command_ids"])]
            cursor += len(group)
            physical = {**program, "commands": group}
            if index < len(nodes) - 1:
                physical["encoding"] = {**program["encoding"], "format": "png", "quality": 90}
            if not group or canonical_hash(physical) != node["program_sha256"]:
                raise ApiError("planner physical program differs from the request")
        final_commands = commands[-len(nodes[-1]["command_ids"]) :]
        split = len(nodes) > 1
        for field in ("logical_program_sha256", "physical_graph_sha256"):
            if response.headers.get("x-image-" + field.replace("_", "-")) != planner[field]:
                raise ApiError("planner headers disagree with receipt")
    elif any(
        key in response.headers
        for key in ("x-image-logical-program-sha256", "x-image-physical-graph-sha256")
    ):
        raise ApiError("planner headers require a receipt")
    return final_commands, split


def verify_program(
    response: httpx.Response, data: dict[str, Any], program: dict[str, Any], inputs: dict[str, Any]
) -> DeterministicEditResult:
    raw = decode_output(data)
    cost = number(data["actual_cost_usd"])
    number(data["estimated_cost_usd"])
    receipt, image = data["receipt"], data["image"]
    verify_single_edit_headers(response, image, receipt)
    final_commands, split = verify_planner(response, data["planner_receipt"], program)
    expected_program = {**program, "commands": final_commands}
    if receipt["program_sha256"] != canonical_hash(expected_program):
        raise ApiError("execution program differs from the request")
    expected_hashes = {name: meta["sha256"] for name, meta in inputs.items()}
    actual_hashes = receipt["input_sha256s"]
    if set(actual_hashes) != set(expected_hashes) or any(
        actual_hashes[name] != digest
        for name, digest in expected_hashes.items()
        if not (split and name == program["source_input"])
    ):
        raise ApiError("execution input hashes differ from the request")
    actual = receipt["commands"]
    if len(actual) != len(final_commands) or any(
        item["id"] != command["id"]
        or item["op"] != command["op"]
        or item["normalized_command_sha256"] != canonical_hash(command)
        for item, command in zip(actual, final_commands, strict=True)
    ):
        raise ApiError("execution commands differ from the request")
    if (receipt["output_sha256"], receipt["output_width"], receipt["output_height"]) != (
        image["sha256"],
        image["width"],
        image["height"],
    ) or image["mime_type"] != f"image/{program['encoding']['format']}":
        raise ApiError("execution output differs from the receipt")
    return DeterministicEditResult(
        raw,
        image["mime_type"],
        image["sha256"],
        image["width"],
        image["height"],
        canonical_hash(program),
        cost,
        tuple(
            (item["id"], item["op"], item["normalized_command_sha256"], item["output_pixel_sha256"])
            for item in actual
        ),
    )
