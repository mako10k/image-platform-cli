"""Image-to-image controls and result integrity for the accepted V4 r8 boundary."""

import base64
import binascii
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import verify_artifact
from ..common.models import GeneratedImage


@dataclass(frozen=True)
class ImageToImageOptions:
    prompt: str
    seed: int
    profile: str = "i2i-stable-diffusion-v1-5"
    negative_prompt: str | None = None
    strength: Decimal = Decimal("0.75")
    guidance_scale: Decimal = Decimal("7.5")
    inference_steps: int = 25
    width: int | None = None
    height: int | None = None

    def validate_controls(self) -> None:
        for text in (self.prompt, self.negative_prompt):
            if text is not None and (not text.strip() or len(text) > 2048):
                raise ApiError("image-to-image prompts must contain 1 to 2048 characters")
        for value, low, high in (
            (self.strength, Decimal("0.1"), 1),
            (self.guidance_scale, Decimal(1), 15),
        ):
            if not value.is_finite() or not low <= value <= high:
                raise ApiError("image-to-image control is outside the supported range")
        if self.negative_prompt is not None and self.guidance_scale <= 1:
            raise ApiError("negative prompt requires guidance scale greater than one")
        if not 10 <= self.inference_steps <= 50 or not 0 <= self.seed < 2**63:
            raise ApiError("invalid image-to-image steps or seed")
        if self.profile != "i2i-stable-diffusion-v1-5":
            raise ApiError("unsupported image-to-image profile")

    def dimensions(self, source: dict[str, Any]) -> tuple[int, int]:
        if (self.width is None) != (self.height is None):
            raise ApiError("image-to-image dimensions must be supplied together")
        width, height = (
            self.width if self.width is not None else source["width"],
            self.height if self.height is not None else source["height"],
        )
        if any(
            not isinstance(v, int) or isinstance(v, bool) or not 256 <= v <= 768 or v % 64
            for v in (width, height)
        ):
            raise ApiError("image-to-image dimensions must be multiples of 64 between 256 and 768")
        return width, height

    def payload(self, source: dict[str, Any]) -> dict[str, Any]:
        self.validate_controls()
        width, height = self.dimensions(source)
        result: dict[str, Any] = {
            "profile": self.profile,
            "prompt": self.prompt,
            "seed": self.seed,
            "strength": str(self.strength),
            "guidance_scale": str(self.guidance_scale),
            "inference_steps": self.inference_steps,
            "width": width,
            "height": height,
        }
        if self.negative_prompt is not None:
            result["negative_prompt"] = self.negative_prompt
        return result


def verified_image(
    response: httpx.Response, data: dict[str, Any], payload: dict[str, Any], source: dict[str, Any]
) -> GeneratedImage:
    output, receipt = data["output"], data["receipt"]
    metadata = output["image"]
    try:
        raw = base64.b64decode(output["data_base64"], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ApiError("image-to-image output is not valid Base64") from error
    verify_artifact(raw, metadata["mime_type"], metadata)
    expected_controls = {
        "strength": Decimal(payload["strength"]),
        "guidance_scale": Decimal(payload["guidance_scale"]),
        "inference_steps": payload["inference_steps"],
        "width": payload["width"],
        "height": payload["height"],
        "negative_prompt_applied": "negative_prompt" in payload,
    }
    controls = dict(receipt["controls"])
    try:
        for key in ("strength", "guidance_scale"):
            controls[key] = Decimal(str(controls[key]))
        cost = Decimal(str(receipt["measured_compute_cost_usd"]))
        header_cost = Decimal(response.headers["x-image-compute-cost-usd"])
    except InvalidOperation as error:
        raise ApiError("image-to-image receipt contains an invalid number") from error
    expected_receipt = {
        "profile": payload["profile"],
        "seed": payload["seed"],
        "input_image": source,
        "output_image": {key: metadata[key] for key in ("sha256", "width", "height")},
        "implementation_revision": "diffusers-0.39.0-img2img-v1",
        "model_id": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "model_revision": "451f4fe16113bff5a5d2269ed5ad43b0592e9a14",
    }
    if any(receipt[key] != value for key, value in expected_receipt.items()):
        raise ApiError("image API returned an inconsistent image-to-image receipt")
    if controls != expected_controls or (
        metadata["mime_type"],
        metadata["width"],
        metadata["height"],
    ) != ("image/png", payload["width"], payload["height"]):
        raise ApiError("image-to-image output does not match the requested controls")
    if not cost.is_finite() or cost < 0 or header_cost != cost:
        raise ApiError("image-to-image cost header disagrees with the receipt")
    expected_headers = {
        "x-image-sha256": metadata["sha256"],
        "x-image-seed": str(payload["seed"]),
        "x-image-model": receipt["model_id"],
        "x-image-model-revision": receipt["model_revision"],
    }
    if any(response.headers[key] != value for key, value in expected_headers.items()):
        raise ApiError("image-to-image headers disagree with the receipt")
    return GeneratedImage(
        raw,
        "image/png",
        metadata["sha256"],
        metadata["width"],
        metadata["height"],
        payload["seed"],
        cost,
        receipt["model_id"],
        receipt["model_revision"],
    )
