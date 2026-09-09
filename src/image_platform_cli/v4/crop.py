"""Exact rectangle crop program, including transparent out-of-image padding."""

from typing import Any

from ..common.errors import ApiError
from .single_edits import single_edit_program


def crop_program(rect: tuple[int, int, int, int]) -> dict[str, Any]:
    if len(rect) != 4 or any(
        isinstance(value, bool) or not isinstance(value, int) for value in rect
    ):
        raise ApiError("crop rectangle must contain four integers")
    x, y, width, height = rect
    if not (-1_000_000 <= x <= 1_000_000 and -1_000_000 <= y <= 1_000_000):
        raise ApiError("crop origin must be from -1000000 through 1000000")
    if not (1 <= width <= 8192 and 1 <= height <= 8192) or width * height > 4_194_304:
        raise ApiError("crop size must be 1 through 8192 per axis and at most 4194304 pixels")
    program = single_edit_program()
    program["commands"] = [
        {"id": "crop", "op": "crop", "rect": {"x": x, "y": y, "width": width, "height": height}}
    ]
    return program
