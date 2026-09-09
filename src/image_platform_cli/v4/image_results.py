"""Shared V4 image-output and image-header checks, independent of receipt family."""

import base64
import binascii
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import verify_artifact


def decode_output(output: dict[str, Any]) -> bytes:
    try:
        raw = base64.b64decode(output["data_base64"], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ApiError("image output is not valid Base64") from error
    metadata = output["image"]
    verify_artifact(raw, metadata["mime_type"], metadata)
    return raw


def verify_image_headers(
    response: httpx.Response, receipt: dict[str, Any], digest: str, seed: int
) -> Decimal:
    try:
        cost = Decimal(str(receipt["measured_compute_cost_usd"]))
        header_cost = Decimal(response.headers["x-image-compute-cost-usd"])
    except InvalidOperation as error:
        raise ApiError("image receipt contains an invalid cost") from error
    if not cost.is_finite() or cost < 0 or header_cost != cost:
        raise ApiError("image cost header disagrees with the receipt")
    expected = {
        "x-image-sha256": digest,
        "x-image-seed": str(seed),
        "x-image-model": receipt["model_id"],
        "x-image-model-revision": receipt["model_revision"],
    }
    if any(response.headers[key] != value for key, value in expected.items()):
        raise ApiError("image headers disagree with the receipt")
    return cost
