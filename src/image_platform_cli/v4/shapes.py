"""Rectangle and ellipse controls for deterministic V4 drawing."""

from dataclasses import dataclass
from typing import Any

from ..common.errors import ApiError
from .single_edits import single_edit_program


@dataclass(frozen=True)
class ShapeOptions:
    kind: str
    rect: tuple[int, int, int, int]
    fill: tuple[int, int, int, int] | None = None
    stroke: tuple[int, int, int, int] | None = None
    stroke_width: int = 1

    def program(self) -> dict[str, Any]:
        if self.kind not in {"rectangle", "ellipse"}:
            raise ApiError("shape must be rectangle or ellipse")
        if len(self.rect) != 4 or any(
            isinstance(v, bool) or not isinstance(v, int) for v in self.rect
        ):
            raise ApiError("shape rectangle must contain four integers")
        x, y, width, height = self.rect
        if not (
            -1_000_000 <= x <= 1_000_000
            and -1_000_000 <= y <= 1_000_000
            and 1 <= width <= 8192
            and 1 <= height <= 8192
        ):
            raise ApiError("shape rectangle exceeds coordinate or dimension bounds")
        if self.fill is None and self.stroke is None:
            raise ApiError("shape requires fill or stroke")
        if isinstance(self.stroke_width, bool) or not 1 <= self.stroke_width <= 1024:
            raise ApiError("stroke width must be from 1 through 1024")
        program = single_edit_program()
        program["commands"] = [
            {
                "id": "draw-shape",
                "op": "draw_shape",
                "shape": self.kind,
                "rect": {"x": x, "y": y, "width": width, "height": height},
                "points": [],
                "fill": rgba(self.fill),
                "stroke": rgba(self.stroke),
                "stroke_width": self.stroke_width,
                "coverage": None,
            }
        ]
        return program


def rgba(value: tuple[int, int, int, int] | None) -> dict[str, int] | None:
    if value is None:
        return None
    if len(value) != 4 or any(
        isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in value
    ):
        raise ApiError("color must contain four integer channels from 0 through 255")
    return dict(zip(("r", "g", "b", "a"), value, strict=True))
