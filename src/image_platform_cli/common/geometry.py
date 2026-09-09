"""Shared local affine geometry calculations, extracted unchanged from image1."""

import argparse
from decimal import Decimal
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .errors import CliError


def _geometry_command(args: argparse.Namespace) -> dict[str, object]:
    source_width, source_height = _image_dimensions(args.input)
    width, height = source_width, source_height
    matrix = (Decimal(1), Decimal(0), Decimal(0), Decimal(1), Decimal(0), Decimal(0))
    background = {"r": 0, "g": 0, "b": 0, "a": 0}
    if args.raster_command == "resize":
        _validate_canvas(args.width, args.height)
        width, height = args.width, args.height
        if args.fit:
            scale = min(Decimal(width) / source_width, Decimal(height) / source_height)
            x = (Decimal(width) - Decimal(source_width) * scale) / 2
            y = (Decimal(height) - Decimal(source_height) * scale) / 2
            matrix = (scale, Decimal(0), Decimal(0), scale, x, y)
        else:
            matrix = (
                Decimal(width) / source_width,
                Decimal(0),
                Decimal(0),
                Decimal(height) / source_height,
                Decimal(0),
                Decimal(0),
            )
    elif args.raster_command == "flip":
        matrix = (
            (Decimal(-1), Decimal(0), Decimal(0), Decimal(1), Decimal(width), Decimal(0))
            if args.axis == "horizontal"
            else (Decimal(1), Decimal(0), Decimal(0), Decimal(-1), Decimal(0), Decimal(height))
        )
    elif args.raster_command == "rotate":
        matrix, width, height = _rotation_geometry(args.degrees, source_width, source_height)
    else:
        _validate_canvas(args.width, args.height)
        width, height = args.width, args.height
        matrix = (Decimal(1), Decimal(0), Decimal(0), Decimal(1), Decimal(args.x), Decimal(args.y))
        background = args.background
    return {
        "id": args.raster_command,
        "op": "affine",
        "transform": dict(zip(("a", "b", "c", "d", "e", "f"), map(str, matrix), strict=True)),
        "output_width": width,
        "output_height": height,
        "interpolation": "lanczos" if args.raster_command == "resize" else "bicubic",
        "border": "constant",
        "background": background,
    }


def _rotation_geometry(
    degrees: int, width: int, height: int
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal], int, int]:
    if degrees == 90:
        return (
            (Decimal(0), Decimal(1), Decimal(-1), Decimal(0), Decimal(height), Decimal(0)),
            height,
            width,
        )
    if degrees == 180:
        return (
            (Decimal(-1), Decimal(0), Decimal(0), Decimal(-1), Decimal(width), Decimal(height)),
            width,
            height,
        )
    return (
        (Decimal(0), Decimal(-1), Decimal(1), Decimal(0), Decimal(0), Decimal(width)),
        height,
        width,
    )


def _image_dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except (OSError, UnidentifiedImageError) as error:
        raise CliError(f"input image is not readable: {path}") from error


def _validate_canvas(width: int, height: int) -> None:
    if not 1 <= width <= 8_192 or not 1 <= height <= 8_192:
        raise CliError("canvas width and height must be from 1 through 8192")
    if width * height > 4_194_304:
        raise CliError("canvas exceeds the 4194304 pixel limit")
