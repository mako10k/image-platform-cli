"""Affine image composition and optional final crop for V4."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..common.errors import ApiError
from .crop import crop_program
from .single_edits import single_edit_program


@dataclass(frozen=True)
class CompositeOptions:
    matrix: tuple[Decimal, ...] = (
        Decimal(1),
        Decimal(0),
        Decimal(0),
        Decimal(1),
        Decimal(0),
        Decimal(0),
    )
    opacity: Decimal = Decimal(1)
    mode: str = "source_over"
    crop: tuple[int, int, int, int] | None = None

    def program(self, *, masked: bool) -> dict[str, Any]:
        if len(self.matrix) != 6 or any(
            not v.is_finite() or not -65536 <= v <= 65536 for v in self.matrix
        ):
            raise ApiError("matrix must contain six finite values from -65536 through 65536")
        if not self.opacity.is_finite() or not 0 <= self.opacity <= 1:
            raise ApiError("opacity must be finite and from zero through one")
        if self.mode not in {"source_over", "replace", "multiply", "screen"}:
            raise ApiError("unsupported composite mode")
        program = single_edit_program()
        program["inputs"]["overlay"] = "image"
        coverage = None
        if masked:
            program["inputs"]["mask"] = "mask"
            coverage = {
                "base": {"source": {"kind": "mask_input", "input": "mask"}, "transforms": []},
                "combine": [],
            }
        program["commands"] = [
            {
                "id": "place-overlay",
                "op": "paste_image",
                "input": "overlay",
                "transform": dict(
                    zip(("a", "b", "c", "d", "e", "f"), map(str, self.matrix), strict=True)
                ),
                "interpolation": "bicubic",
                "border": "transparent",
                "opacity": str(self.opacity),
                "composite": self.mode,
                "coverage": coverage,
            }
        ]
        if self.crop is not None:
            command = crop_program(self.crop)["commands"][0]
            program["commands"].append({**command, "id": "crop-result"})
        return program
