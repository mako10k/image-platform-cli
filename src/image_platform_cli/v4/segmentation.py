"""V4 segmentation selectors and result verification."""

import base64
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..common.errors import ApiError
from ..common.files import read_image
from ..common.models import SegmentationResult
from .image_results import decode_output, verify_image_headers


@dataclass(frozen=True)
class SegmentSelector:
    text: str | None = None
    points: Sequence[tuple[int, int, bool]] = ()
    box: tuple[int, int, int, int] | None = None

    def payload(self, width: int, height: int) -> dict[str, Any]:
        if sum((self.text is not None, bool(self.points), self.box is not None)) != 1:
            raise ApiError("choose exactly one segmentation selector")
        if self.text is not None:
            if not self.text.strip() or len(self.text) > 2048:
                raise ApiError("segmentation text must contain 1 to 2048 characters")
            return {"text": self.text}
        if self.box is not None:
            left, top, right, bottom = self.box
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ApiError("segmentation box exceeds image bounds")
            return {"box": dict(zip(("x_min", "y_min", "x_max", "y_max"), self.box, strict=True))}
        self.validate_points(width, height)
        return {
            "points": [{"x": x, "y": y, "positive": positive} for x, y, positive in self.points]
        }

    def validate_points(self, width: int, height: int) -> None:
        if len(self.points) > 32 or not any(positive for _, _, positive in self.points):
            raise ApiError("segmentation needs a positive point and at most 32 points")
        if any(not (0 <= x < width and 0 <= y < height) for x, y, _ in self.points):
            raise ApiError("segmentation point exceeds image bounds")


def prepare_segment(
    path: Path, selector: SegmentSelector
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    raw, mime, width, height = read_image(path)
    request = selector.payload(width, height)
    request["input"] = {"mime_type": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
    metadata = {"sha256": hashlib.sha256(raw).hexdigest(), "width": width, "height": height}
    return request, raw, metadata


def verify_segment(
    response: httpx.Response, data: dict[str, Any], source: bytes, metadata: dict[str, Any]
) -> SegmentationResult:
    output, receipt = data["output"], data["receipt"]
    mask = decode_output(output)
    image = output["image"]
    expected = {
        "profile": "segment-grounding-dino-sam2-tiny",
        "grounding_model_id": "IDEA-Research/grounding-dino-tiny",
        "grounding_model_revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        "segmentation_model_id": "facebook/sam2.1-hiera-tiny",
        "segmentation_model_revision": "de431c4043854a71d8101e17995dfe596bf101a5",
        "input_image": metadata,
        "mask_image": {**metadata, "sha256": image["sha256"]},
    }
    if any(receipt[key] != value for key, value in expected.items()):
        raise ApiError("image API returned an inconsistent segmentation receipt")
    if (image["mime_type"], image["width"], image["height"]) != (
        "image/png",
        metadata["width"],
        metadata["height"],
    ):
        raise ApiError("segmentation mask must retain the source geometry")
    cost = verify_image_headers(
        response,
        {
            "model_id": receipt["segmentation_model_id"],
            "model_revision": receipt["segmentation_model_revision"],
            "measured_compute_cost_usd": receipt["measured_compute_cost_usd"],
        },
        image["sha256"],
        None,
    )
    return SegmentationResult(source, mask, image["sha256"], image["width"], image["height"], cost)
