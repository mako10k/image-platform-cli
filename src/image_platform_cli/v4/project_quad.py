"""Convex quadrilateral projection controls for V4 raster editing."""

from dataclasses import dataclass
from typing import Any

from ..common.errors import ApiError
from .single_edits import single_edit_program


@dataclass(frozen=True)
class QuadOptions:
    destination: tuple[int, ...]
    composite: str = "source_over"

    def program(self) -> dict[str, Any]:
        if self.composite not in {"source_over", "replace", "multiply", "screen"}:
            raise ApiError("unsupported projection composite mode")
        values = self.destination
        if len(values) != 8 or any(
            isinstance(v, bool) or not isinstance(v, int) or not -1_000_000 <= v <= 1_000_000
            for v in values
        ):
            raise ApiError("destination must contain eight bounded integer coordinates")
        points = list(zip(values[::2], values[1::2], strict=True))
        turns = []
        for index, (x, y) in enumerate(points):
            next_x, next_y = points[(index + 1) % 4]
            after_x, after_y = points[(index + 2) % 4]
            turns.append((next_x - x) * (after_y - y) - (next_y - y) * (after_x - x))
        if not (all(turn > 0 for turn in turns) or all(turn < 0 for turn in turns)):
            raise ApiError("destination must be a non-degenerate convex perimeter")
        program = single_edit_program()
        program["inputs"]["texture"] = "image"
        program["commands"] = [
            {
                "id": "project-quad",
                "op": "project_quad",
                "texture_input": "texture",
                "destination": [{"x": x, "y": y} for x, y in points],
                "interpolation": "bilinear",
                "composite": self.composite,
                "coverage": None,
            }
        ]
        return program
