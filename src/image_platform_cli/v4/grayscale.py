"""Fixed Rec.709 linear-sRGB grayscale program."""

from typing import Any

from .single_edits import single_edit_program


def grayscale_program() -> dict[str, Any]:
    program = single_edit_program()
    program["commands"] = [
        {
            "id": "grayscale",
            "op": "grayscale",
            "luminance": "rec709_linear_srgb_v1",
            "coverage": None,
        }
    ]
    return program
