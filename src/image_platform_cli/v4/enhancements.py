"""Enhancement request preparation and V4 receipt verification."""

import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import read_image
from ..common.inputs import inline_image
from .image_results import decode_output


@dataclass(frozen=True, slots=True)
class EnhancedImage:
    data: bytes
    mime_type: str
    sha256: str
    width: int
    height: int
    measured_compute_cost_usd: Decimal


def prepare_enhancement(
    input_path: Path,
    *,
    operation: str,
    quality_tier: str,
    width: int | None,
    height: int | None,
) -> tuple[dict[str, object], dict[str, object]]:
    raw, _, input_width, input_height = read_image(input_path)
    source = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "width": input_width,
        "height": input_height,
    }
    if operation == "restore":
        output_width, output_height = input_width, input_height
    elif operation == "upscale" and width is not None and height is not None:
        output_width, output_height = width, height
    else:
        raise ApiError("upscale dimensions must be supplied together")
    if quality_tier not in {"deterministic", "ai"}:
        raise ApiError("unsupported enhancement quality tier")
    if (
        any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in (output_width, output_height)
        )
        or not 1 <= output_width <= 4096
        or not 1 <= output_height <= 4096
        or output_width * output_height > 16_777_216
        or (operation == "upscale" and (output_width < input_width or output_height < input_height))
    ):
        raise ApiError("enhancement dimensions are outside the accepted bounds")
    return (
        {
            "input": inline_image(input_path),
            "operation": operation,
            "quality_tier": quality_tier,
            "width": output_width,
            "height": output_height,
        },
        source,
    )


def verify_enhancement(
    response: httpx.Response,
    data: dict[str, Any],
    payload: dict[str, object],
    source: dict[str, object],
) -> EnhancedImage:
    output, receipt = data["output"], data["receipt"]
    metadata = output["image"]
    raw = decode_output(output)
    expected_output = {
        "sha256": metadata["sha256"],
        "width": payload["width"],
        "height": payload["height"],
    }
    if (
        receipt["operation"] != payload["operation"]
        or receipt["quality_tier"] != payload["quality_tier"]
        or receipt["input_image"] != source
        or receipt["output_image"] != expected_output
        or metadata["mime_type"] != "image/png"
        or (metadata["width"], metadata["height"]) != (payload["width"], payload["height"])
    ):
        raise ApiError("image API returned an inconsistent enhancement receipt")
    try:
        cost = Decimal(str(receipt["measured_compute_cost_usd"]))
        header_cost = Decimal(response.headers["x-image-compute-cost-usd"])
    except InvalidOperation as error:
        raise ApiError("enhancement receipt contains an invalid cost") from error
    expected_headers = {
        "x-image-sha256": metadata["sha256"],
        "x-image-operation": payload["operation"],
        "x-image-enhancement-profile": receipt["profile"],
    }
    if (
        cost < 0
        or not cost.is_finite()
        or header_cost != cost
        or any(response.headers[key] != value for key, value in expected_headers.items())
    ):
        raise ApiError("enhancement headers disagree with the receipt")
    return EnhancedImage(
        raw,
        "image/png",
        metadata["sha256"],
        metadata["width"],
        metadata["height"],
        cost,
    )
