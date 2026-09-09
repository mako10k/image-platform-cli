"""Registered-font text controls for deterministic V4 drawing."""

import re
from dataclasses import dataclass
from typing import Any

from ..common.errors import ApiError
from .shapes import rgba
from .single_edits import single_edit_program


@dataclass(frozen=True)
class TextOptions:
    text: str
    position: tuple[int, int]
    font_id: str
    font_sha256: str
    font_size: int
    fill: tuple[int, int, int, int]
    stroke: tuple[int, int, int, int] | None = None
    stroke_width: int = 0

    def program(self) -> dict[str, Any]:
        if not 1 <= len(self.text) <= 4096:
            raise ApiError("text must contain 1 through 4096 characters")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.font_id) or not re.fullmatch(
            r"[0-9a-f]{64}", self.font_sha256
        ):
            raise ApiError("font requires a valid registered ID and lowercase SHA-256")
        if len(self.position) != 2 or any(
            isinstance(v, bool) or not isinstance(v, int) or not -1_000_000 <= v <= 1_000_000
            for v in self.position
        ):
            raise ApiError("text position must contain two bounded integer coordinates")
        if isinstance(self.font_size, bool) or not 1 <= self.font_size <= 2048:
            raise ApiError("font size must be from 1 through 2048")
        if isinstance(self.stroke_width, bool) or not 0 <= self.stroke_width <= 128:
            raise ApiError("text stroke width must be from zero through 128")
        fill = rgba(self.fill)
        if fill is None:
            raise ApiError("text requires a fill color")
        program = single_edit_program()
        program["commands"] = [
            {
                "id": "draw-text",
                "op": "draw_text",
                "text": self.text,
                "position": {"x": self.position[0], "y": self.position[1]},
                "font": {"id": self.font_id, "sha256": self.font_sha256},
                "font_size_px": self.font_size,
                "fill": fill,
                "stroke": rgba(self.stroke),
                "stroke_width": self.stroke_width,
                "coverage": None,
            }
        ]
        return program
