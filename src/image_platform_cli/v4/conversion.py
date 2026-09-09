"""Format and quality controls for V4 image conversion."""

from pathlib import Path
from typing import Any

from ..common.errors import ApiError
from .single_edits import prepare_single_edit, single_edit_program


def prepare_conversion(
    path: Path, format_name: str, quality: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if format_name not in {"png", "jpeg", "webp"}:
        raise ApiError("conversion format must be png, jpeg or webp")
    if isinstance(quality, bool) or not 1 <= quality <= 100:
        raise ApiError("quality must be from 1 through 100")
    if format_name == "png" and quality != 90:
        raise ApiError("quality is not configurable for PNG")
    program = single_edit_program()
    program["encoding"].update(format=format_name, quality=quality)
    return prepare_single_edit(path, program)
