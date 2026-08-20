import base64
import binascii
import hashlib
import os
from pathlib import Path
from typing import Any

import httpx

from .errors import ApiError
from .models import GeneratedImage


class ImageApiClient:
    def __init__(self, http: httpx.Client, api_base_url: str) -> None:
        self._http = http
        self._api_base_url = api_base_url.rstrip("/")

    def generate(
        self,
        access_token: str,
        *,
        prompt: str,
        width: int,
        height: int,
        seed: int,
        optimize: bool,
    ) -> GeneratedImage:
        if not prompt.strip() or len(prompt) > 2048:
            raise ApiError("prompt must contain 1 to 2048 non-whitespace characters")
        if width < 256 or width > 1024 or width % 64:
            raise ApiError("width must be a multiple of 64 from 256 through 1024")
        if height < 256 or height > 1024 or height % 64:
            raise ApiError("height must be a multiple of 64 from 256 through 1024")
        if seed < 0 or seed > 2**63 - 1:
            raise ApiError("seed is outside the supported range")
        try:
            response = self._http.post(
                f"{self._api_base_url}/v1/generations",
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "query": prompt,
                    "profile": "generation-standard",
                    "width": width,
                    "height": height,
                    "seed": seed,
                    "optimizer_enabled": optimize,
                },
            )
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        image = _parse_generation(response)
        if image.width != width or image.height != height:
            raise ApiError("image API returned unexpected dimensions")
        return image


def save_image(image: GeneratedImage, output: Path) -> None:
    if not output.parent.is_dir():
        raise ApiError("output directory does not exist")
    try:
        with output.open("xb") as stream:
            stream.write(image.data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ApiError("output file already exists") from error
    except OSError as error:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        raise ApiError("output file could not be written") from error


def _parse_generation(response: httpx.Response) -> GeneratedImage:
    try:
        body: Any = response.json()
        output = body["output"]
        metadata = output["image"]
        receipt = body["receipt"]
        data = base64.b64decode(_required_string(output, "data_base64"), validate=True)
        sha256 = _required_string(metadata, "sha256")
        size_bytes = _required_int(metadata, "size_bytes")
        mime_type = _required_string(metadata, "mime_type")
        width = _required_int(metadata, "width")
        height = _required_int(metadata, "height")
        model_id = _required_string(receipt, "model_id")
        model_revision = _required_string(receipt, "model_revision")
    except (KeyError, TypeError, ValueError, binascii.Error) as error:
        raise ApiError("image API returned a malformed response") from error
    digest = hashlib.sha256(data).hexdigest()
    png_width, png_height = _png_dimensions(data)
    if (
        not data
        or mime_type != "image/png"
        or size_bytes != len(data)
        or sha256 != digest
        or response.headers.get("X-Image-SHA256") != digest
        or not data.startswith(b"\x89PNG\r\n\x1a\n")
        or width <= 0
        or height <= 0
        or (width, height) != (png_width, png_height)
    ):
        raise ApiError("image API response integrity check failed")
    return GeneratedImage(data, mime_type, digest, width, height, model_id, model_revision)


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ApiError("image API response integrity check failed")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _safe_api_error(response: httpx.Response) -> str:
    request_id = response.headers.get("X-Request-ID")
    suffix = f" (request {request_id})" if request_id else ""
    return f"image API returned HTTP {response.status_code}{suffix}"


def _required_string(body: Any, name: str) -> str:
    if not isinstance(body, dict):
        raise TypeError(name)
    value = body[name]
    if not isinstance(value, str) or not value:
        raise ValueError(name)
    return value


def _required_int(body: Any, name: str) -> int:
    if not isinstance(body, dict):
        raise TypeError(name)
    value = body[name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(name)
    return value
