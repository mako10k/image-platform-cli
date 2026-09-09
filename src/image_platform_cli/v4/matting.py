"""Portrait matting inputs and pinned V4 result verification."""

import base64
import hashlib
from pathlib import Path
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import read_image
from ..common.models import PortraitMattingResult
from .image_results import decode_output, verify_image_headers


def prepare_matting(
    image_path: Path, mask_path: Path, radius: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(radius, bool) or not 0 <= radius <= 64:
        raise ApiError("uncertainty radius must be from 0 through 64")
    payload: dict[str, Any] = {"uncertainty_radius": radius}
    receipts: dict[str, Any] = {}
    for key, path in (("image", image_path), ("person_mask", mask_path)):
        raw, mime, width, height = read_image(path)
        payload[key] = {"mime_type": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
        receipts[key] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "width": width,
            "height": height,
        }
    if any(receipts["image"][key] != receipts["person_mask"][key] for key in ("width", "height")):
        raise ApiError("person mask dimensions must match image dimensions")
    return payload, receipts


def verify_matting(
    response: httpx.Response, data: dict[str, Any], inputs: dict[str, Any], radius: int
) -> PortraitMattingResult:
    output, receipt = data["output"], data["receipt"]
    raw = decode_output(output)
    image = output["image"]
    source = inputs["image"]
    expected = {
        "contract_revision": "portrait-matting-v1",
        "profile": "portrait-matting-birefnet-v1",
        "model_id": "ZhengPeng7/BiRefNet-matting",
        "model_revision": "57f9f68b43ba337c75762b14cf3075d659007268",
        "input_image": source,
        "person_mask": inputs["person_mask"],
        "output_image": {**source, "sha256": image["sha256"]},
        "uncertainty_radius": radius,
    }
    if any(receipt[key] != value for key, value in expected.items()):
        raise ApiError("image API returned an inconsistent portrait matting receipt")
    if (image["mime_type"], image["width"], image["height"]) != (
        "image/png",
        source["width"],
        source["height"],
    ):
        raise ApiError("portrait matte must retain the source geometry")
    cost = verify_image_headers(response, receipt, image["sha256"], None)
    return PortraitMattingResult(
        raw,
        image["sha256"],
        image["width"],
        image["height"],
        receipt["model_id"],
        receipt["model_revision"],
        cost,
    )
