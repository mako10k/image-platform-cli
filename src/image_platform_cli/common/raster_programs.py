"""API-independent raster program builders shared with image1."""

import argparse
import json
import re
from decimal import Decimal
from pathlib import Path

from .errors import CliError
from .geometry import _geometry_command


def _raster_commands(args: argparse.Namespace) -> list[dict[str, object]]:
    if args.raster_command == "grayscale":
        return [
            {
                "id": "grayscale",
                "op": "grayscale",
                "luminance": "rec709_linear_srgb_v1",
            }
        ]
    if args.raster_command == "crop":
        x, y, width, height = args.rect
        if width <= 0 or height <= 0:
            raise CliError("crop width and height must be positive")
        return [
            {
                "id": "crop",
                "op": "crop",
                "rect": {"x": x, "y": y, "width": width, "height": height},
            }
        ]
    if args.raster_command == "filter":
        if not Decimal(0) < args.radius <= Decimal(64):
            raise CliError("filter radius must be greater than 0 and at most 64")
        if not Decimal(0) <= args.amount <= Decimal(16):
            raise CliError("filter amount must be from 0 through 16")
        return [
            {
                "id": "filter",
                "op": "filter",
                "filter": args.kind,
                "radius": str(args.radius),
                "amount": str(args.amount),
            }
        ]
    if args.raster_command == "auto-crop":
        _validate_optional_decimal(args.threshold, "threshold", Decimal(0), Decimal(1))
        if not 0 <= args.padding <= 8_192:
            raise CliError("padding must be from 0 through 8192")
        return [
            {
                "id": "auto-crop",
                "op": "auto_crop",
                "coverage": {"base": {"source": {"kind": "mask_input", "input": "selection"}}},
                "threshold": str(args.threshold),
                "padding": args.padding,
            }
        ]
    if args.raster_command == "shape":
        if args.fill is None and args.stroke is None:
            raise CliError("shape requires --fill or --stroke")
        if not 1 <= args.stroke_width <= 1_024:
            raise CliError("stroke-width must be from 1 through 1024")
        x, y, width, height = args.rect
        return [
            {
                "id": "draw-shape",
                "op": "draw_shape",
                "shape": args.kind,
                "rect": {"x": x, "y": y, "width": width, "height": height},
                "fill": args.fill,
                "stroke": args.stroke,
                "stroke_width": args.stroke_width,
            }
        ]
    if args.raster_command == "text":
        if not args.text or len(args.text) > 4_096:
            raise CliError("text must contain 1 to 4096 characters")
        if not re.fullmatch(r"[0-9a-f]{64}", args.font_sha256):
            raise CliError("font-sha256 must contain 64 lowercase hexadecimal characters")
        if not 1 <= args.font_size <= 2_048 or not 0 <= args.stroke_width <= 128:
            raise CliError("font-size or stroke-width is outside the supported bounds")
        x, y = args.position
        return [
            {
                "id": "draw-text",
                "op": "draw_text",
                "text": args.text,
                "position": {"x": x, "y": y},
                "font": {"id": args.font_id, "sha256": args.font_sha256},
                "font_size_px": args.font_size,
                "fill": args.fill,
                "stroke": args.stroke,
                "stroke_width": args.stroke_width,
            }
        ]
    if args.raster_command == "color-match":
        _validate_optional_decimal(args.strength, "strength", Decimal(0), Decimal(1))
        return [
            {
                "id": "color-match",
                "op": "color_match",
                "reference_input": "reference",
                "algorithm": args.algorithm,
                "strength": str(args.strength),
                "preserve_luminance": args.preserve_luminance,
            }
        ]
    if args.raster_command in {"resize", "flip", "rotate", "canvas"}:
        return [_geometry_command(args)]
    if args.raster_command == "project-quad":
        coordinates = iter(args.destination)
        points = [{"x": x, "y": y} for x, y in zip(coordinates, coordinates, strict=True)]
        return [
            {
                "id": "project-quad",
                "op": "project_quad",
                "texture_input": "texture",
                "destination": points,
                "composite": args.composite,
            }
        ]
    if args.raster_command == "mesh":
        spec = _read_json_object(args.mesh_spec, "mesh spec")
        forbidden = {"id", "op", "texture_input"} & set(spec)
        if forbidden:
            raise CliError("mesh spec must not override id, op, or texture_input")
        return [{"id": "render-mesh", "op": "render_mesh", "texture_input": "texture", **spec}]
    return _adjustment_commands(args)


def _raster_input_paths(args: argparse.Namespace) -> tuple[dict[str, Path], dict[str, Path]]:
    inputs = {"source": args.input}
    masks: dict[str, Path] = {}
    if args.raster_command == "auto-crop":
        masks["selection"] = args.mask
    if args.raster_command == "color-match":
        inputs["reference"] = args.reference
    if args.raster_command in {"project-quad", "mesh"}:
        inputs["texture"] = args.texture
    return inputs, masks


def _adjustment_commands(args: argparse.Namespace) -> list[dict[str, object]]:
    _validate_optional_decimal(args.hue, "hue", Decimal(-180), Decimal(180))
    _validate_optional_decimal(args.saturation, "saturation", Decimal(0), Decimal(4))
    _validate_optional_decimal(args.tint, "tint", Decimal(-1), Decimal(1))
    _validate_optional_decimal(args.exposure, "exposure", Decimal(-10), Decimal(10))
    _validate_optional_decimal(args.brightness, "brightness", Decimal(-1), Decimal(1))
    _validate_optional_decimal(args.contrast, "contrast", Decimal(0), Decimal(4))
    if args.temperature is not None and not 1_000 <= args.temperature <= 40_000:
        raise CliError("temperature must be from 1000 through 40000")
    commands: list[dict[str, object]] = []
    if args.hue is not None or args.saturation is not None:
        commands.append(
            {
                "id": "hue-saturation",
                "op": "hue_saturation",
                "hue_degrees": str(args.hue if args.hue is not None else 0),
                "saturation_scale": str(args.saturation if args.saturation is not None else 1),
            }
        )
    if args.temperature is not None:
        commands.append(
            {
                "id": "white-balance",
                "op": "white_balance",
                "temperature_kelvin": args.temperature,
                "tint": str(args.tint),
            }
        )
    if any(value is not None for value in (args.exposure, args.brightness, args.contrast)):
        commands.append(
            {
                "id": "tone",
                "op": "tone",
                "exposure_stops": str(args.exposure if args.exposure is not None else 0),
                "brightness": str(args.brightness if args.brightness is not None else 0),
                "contrast": str(args.contrast if args.contrast is not None else 1),
            }
        )
    if not commands:
        raise CliError("raster adjust requires at least one adjustment")
    return commands


def _validate_optional_decimal(
    value: Decimal | None, name: str, minimum: Decimal, maximum: Decimal
) -> None:
    if value is not None and (not value.is_finite() or not minimum <= value <= maximum):
        raise CliError(f"{name} must be from {minimum} through {maximum}")


def _read_json_object(path: Path, name: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliError(f"{name} must be a readable UTF-8 JSON file") from error
    if not isinstance(value, dict):
        raise CliError(f"{name} must contain one JSON object")
    return value
