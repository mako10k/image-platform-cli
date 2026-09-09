"""Bounded filter controls for the fixed deterministic raster contract."""

from decimal import Decimal
from typing import Any

from ..common.errors import ApiError
from .single_edits import single_edit_program


def filter_program(kind: str, radius: Decimal, amount: Decimal = Decimal(1)) -> dict[str, Any]:
    if kind not in {"gaussian_blur", "box_blur", "unsharp_mask"}:
        raise ApiError("unsupported raster filter")
    if not radius.is_finite() or not Decimal(0) < radius <= Decimal(64):
        raise ApiError("filter radius must be finite, greater than zero and at most 64")
    if not amount.is_finite() or not Decimal(0) <= amount <= Decimal(16):
        raise ApiError("filter amount must be finite and from zero through 16")
    program = single_edit_program()
    program["commands"] = [
        {
            "id": "filter",
            "op": "filter",
            "filter": kind,
            "radius": str(radius),
            "amount": str(amount),
            "border": "reflect",
            "coverage": None,
        }
    ]
    return program
