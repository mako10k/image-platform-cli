"""Local program loading and named bindings shared by both CLI implementations."""

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .errors import ApiError


def load_deterministic_program(
    program_path: Path,
    *,
    input_bindings: Sequence[str],
    mask_bindings: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Path], dict[str, Path]]:
    """Load and validate a local deterministic program without constructing transport."""
    try:
        raw = json.loads(program_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ApiError("program must be a readable UTF-8 JSON file") from error
    program = _validate_deterministic_program(raw)
    inputs = _parse_named_paths(input_bindings, kind="input")
    masks = _parse_named_paths(mask_bindings, kind="mask")
    if set(inputs) & set(masks):
        raise ApiError("input and mask binding names must be distinct")
    declared = program["inputs"]
    actual_kinds = {**{name: "image" for name in inputs}, **{name: "mask" for name in masks}}
    if declared != actual_kinds:
        raise ApiError("named bindings must exactly match program inputs and kinds")
    return program, inputs, masks


def _parse_named_paths(bindings: Sequence[str], *, kind: str) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for binding in bindings:
        name, separator, raw_path = binding.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name) or not raw_path:
            raise ApiError(f"{kind} bindings must use NAME=PATH")
        if name in parsed:
            raise ApiError(f"duplicate {kind} binding: {name}")
        parsed[name] = Path(raw_path)
    return parsed


def _validate_deterministic_program(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError("program JSON must be an object")
    if value.get("revision") != "deterministic-edit-v1":
        raise ApiError("program revision must be deterministic-edit-v1")
    inputs = value.get("inputs")
    if (
        not isinstance(inputs, dict)
        or not inputs
        or len(inputs) > 16
        or any(
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name)
            or kind not in {"image", "mask"}
            for name, kind in inputs.items()
        )
    ):
        raise ApiError("program inputs must declare 1 to 16 named image or mask inputs")
    if value.get("source_input") not in inputs or inputs[value["source_input"]] != "image":
        raise ApiError("program source_input must name an image input")
    commands = value.get("commands")
    if not isinstance(commands, list) or not 1 <= len(commands) <= 64:
        raise ApiError("program commands must contain 1 to 64 commands")
    identities: list[str] = []
    for command in commands:
        if not isinstance(command, dict):
            raise ApiError("each program command must be an object")
        command_id = command.get("id")
        operation = command.get("op")
        if (
            not isinstance(command_id, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", command_id)
            or not isinstance(operation, str)
            or not operation
        ):
            raise ApiError("each program command requires valid id and op strings")
        identities.append(command_id)
    if len(set(identities)) != len(identities):
        raise ApiError("program command ids must be unique")
    encoding = value.get("encoding")
    if not isinstance(encoding, dict) or encoding.get("format") not in {"png", "jpeg", "webp"}:
        raise ApiError("program encoding format must be png, jpeg, or webp")
    quality = encoding.get("quality", 90)
    if not isinstance(quality, int) or isinstance(quality, bool) or not 1 <= quality <= 100:
        raise ApiError("program encoding quality must be from 1 through 100")
    if encoding.get("format") == "png" and quality != 90:
        raise ApiError("program encoding quality is not configurable for PNG")
    return value
