"""Reference-image color matching controls for the deterministic V4 contract."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..common.errors import ApiError
from .single_edits import single_edit_program


@dataclass(frozen=True)
class ColorMatchOptions:
    algorithm: str = "lab_mean_std_v1"
    strength: Decimal = Decimal(1)
    preserve_luminance: bool = False

    def program(self) -> dict[str, Any]:
        if self.algorithm not in {"lab_mean_std_v1", "lab_histogram_256_v1"}:
            raise ApiError("unsupported color-match algorithm")
        if not self.strength.is_finite() or not Decimal(0) <= self.strength <= Decimal(1):
            raise ApiError("color-match strength must be finite and from zero through one")
        if not isinstance(self.preserve_luminance, bool):
            raise ApiError("preserve luminance must be a boolean")
        program = single_edit_program()
        program["inputs"]["reference"] = "image"
        program["commands"] = [
            {
                "id": "color-match",
                "op": "color_match",
                "reference_input": "reference",
                "algorithm": self.algorithm,
                "strength": str(self.strength),
                "preserve_luminance": self.preserve_luminance,
                "coverage": None,
            }
        ]
        return program
