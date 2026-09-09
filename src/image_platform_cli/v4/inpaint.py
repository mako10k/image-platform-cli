"""Mask-native inpainting request and receipt checks for V4."""

import base64
import hashlib
from pathlib import Path
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import MAX_IMAGE_BYTES, read_image
from ..common.models import GeneratedImage
from .image_results import decode_output, verify_image_headers

PROFILE = "inpaint-stable-diffusion-v1-5"


def prepare_inpaint(
    image_path: Path, mask_path: Path, prompt: str, seed: int, profile: str, safety: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if profile != PROFILE or safety not in {"default", "enabled", "disabled"}:
        raise ApiError("unsupported inpaint profile or safety mode")
    if not prompt.strip() or len(prompt) > 2048:
        raise ApiError("inpaint prompt must contain 1 to 2048 characters")
    if isinstance(seed, bool) or not 0 <= seed < 2**63:
        raise ApiError("inpaint seed is outside the supported range")
    image, mime, width, height = read_image(image_path)
    mask, mask_mime, mask_width, mask_height = read_image(mask_path)
    if (width, height) != (mask_width, mask_height):
        raise ApiError("inpaint mask dimensions must match the image")
    if len(image) + len(mask) > MAX_IMAGE_BYTES:
        raise ApiError("combined inpaint input exceeds 10 MiB")
    source = {"sha256": hashlib.sha256(image).hexdigest(), "width": width, "height": height}
    mask_metadata = {**source, "sha256": hashlib.sha256(mask).hexdigest()}
    request = {
        "prompt": prompt,
        "seed": seed,
        "safety_filter": safety,
        "image": {"mime_type": mime, "data_base64": base64.b64encode(image).decode("ascii")},
        "mask": {"mime_type": mask_mime, "data_base64": base64.b64encode(mask).decode("ascii")},
    }
    return request, source, mask_metadata


def verify_inpaint(
    response: httpx.Response,
    data: dict[str, Any],
    request: dict[str, Any],
    source: dict[str, Any],
    mask: dict[str, Any],
) -> GeneratedImage:
    output, receipt = data["output"], data["receipt"]
    raw = decode_output(output)
    metadata = output["image"]
    expected = {
        "operation": "inpaint",
        "profile": PROFILE,
        "model_id": "stable-diffusion-v1-5/stable-diffusion-inpainting",
        "model_revision": "8a4288a76071f7280aedbdb3253bdb9e9d5d84bb",
        "seed": request["seed"],
        "input_image": source,
        "mask_image": mask,
        "output_image": {
            "sha256": metadata["sha256"],
            "width": source["width"],
            "height": source["height"],
        },
    }
    if any(receipt[key] != value for key, value in expected.items()):
        raise ApiError("image API returned an inconsistent inpaint receipt")
    if (metadata["mime_type"], metadata["width"], metadata["height"]) != (
        "image/png",
        source["width"],
        source["height"],
    ):
        raise ApiError("inpaint output must retain the source geometry")
    safety = receipt["safety_filter"]
    verify_safety(response, safety, request["safety_filter"])
    cost = verify_image_headers(response, receipt, metadata["sha256"], request["seed"])
    return GeneratedImage(
        raw,
        "image/png",
        metadata["sha256"],
        metadata["width"],
        metadata["height"],
        request["seed"],
        cost,
        receipt["model_id"],
        receipt["model_revision"],
        safety["requested"],
        safety["effective"],
        safety["outcome"],
    )


def verify_safety(response: httpx.Response, evidence: dict[str, Any], requested: str) -> None:
    effective = evidence["effective"]
    expected_outcome = {"enabled": "passed", "disabled": "not_run"}.get(effective)
    if (
        evidence["requested"] != requested
        or expected_outcome is None
        or evidence["outcome"] != expected_outcome
        or (requested != "default" and effective != requested)
    ):
        raise ApiError("inpaint safety evidence disagrees with the request")
    for name in ("requested", "effective", "outcome"):
        if response.headers[f"x-image-safety-filter-{name}"] != evidence[name]:
            raise ApiError("inpaint safety headers disagree with the receipt")
