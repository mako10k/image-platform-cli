import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

from .errors import ApiError
from .models import GeneratedImage

TERMINAL_FAILURES = frozenset({"failed", "partial", "cancelled"})


class ImageApiClient:
    def __init__(
        self,
        http: httpx.Client,
        api_base_url: str,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        polling_timeout_seconds: float = 1_500,
    ) -> None:
        self._http = http
        self._api_base_url = api_base_url.rstrip("/")
        self._api_origin = _origin(self._api_base_url)
        self._sleep = sleeper
        self._clock = clock
        self._polling_timeout_seconds = polling_timeout_seconds

    def generate(
        self,
        access_token: str,
        *,
        prompt: str,
        width: int,
        height: int,
        seed: int,
        optimize: bool,
        wait_seconds: int = 30,
        allow_long_wait: bool = False,
    ) -> GeneratedImage:
        self._validate_request(prompt, width, height, seed, wait_seconds, allow_long_wait)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": str(uuid4()),
        }
        try:
            response = self._http.post(
                f"{self._api_base_url}/v1/generations",
                headers=headers,
                json={
                    "query": prompt,
                    "profile": "generation-standard",
                    "width": width,
                    "height": height,
                    "seed": seed,
                    "optimizer_enabled": optimize,
                    "execution": {
                        "wait_seconds": wait_seconds,
                        "allow_long_wait": allow_long_wait,
                        "accept_async": True,
                    },
                },
            )
            artifact = (
                self._poll(response, headers)
                if response.status_code == 202
                else self._artifact_from_completed_response(response)
            )
            image = self._download_artifact(artifact)
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        if image.width != width or image.height != height:
            raise ApiError("image API returned unexpected dimensions")
        return image

    def _poll(self, response: httpx.Response, headers: dict[str, str]) -> dict[str, Any]:
        body = _required_dict(response.json())
        status_url = _same_origin_url(_required_string(body, "status_url"), self._api_origin)
        deadline = self._clock() + self._polling_timeout_seconds
        delay = _retry_after(response)
        while True:
            if self._clock() >= deadline:
                raise ApiError("image generation polling timed out; the Job may still be running")
            self._sleep(delay)
            status_response = self._http.get(status_url, headers=headers)
            if not status_response.is_success:
                raise ApiError(_safe_api_error(status_response))
            snapshot = _required_dict(status_response.json())
            job_status = _required_string(snapshot, "status")
            if job_status == "completed":
                outputs = snapshot.get("outputs")
                if not isinstance(outputs, list) or len(outputs) != 1:
                    raise ApiError("image API returned a malformed Job result")
                artifact_id = _required_string(_required_dict(outputs[0]), "artifact_id")
                artifact_response = self._http.get(
                    f"{self._api_base_url}/v1/artifacts/{artifact_id}", headers=headers
                )
                if not artifact_response.is_success:
                    raise ApiError(_safe_api_error(artifact_response))
                return _required_dict(artifact_response.json())
            if job_status in TERMINAL_FAILURES:
                raise ApiError(f"image generation ended with status {job_status}")
            delay = _retry_after(status_response)

    @staticmethod
    def _artifact_from_completed_response(response: httpx.Response) -> dict[str, Any]:
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        body = _required_dict(response.json())
        if _required_string(body, "status") != "completed":
            raise ApiError("image API returned a malformed completion")
        return _required_dict(body.get("result"))

    def _download_artifact(self, artifact: dict[str, Any]) -> GeneratedImage:
        ready = _required_dict(artifact.get("result"))
        metadata = _required_dict(ready.get("artifact"))
        url = _required_string(ready, "url")
        if urlsplit(url).scheme != "https":
            raise ApiError("image API returned an unsafe Artifact URL")
        response = self._http.get(url)
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        data = response.content
        sha256 = _required_string(metadata, "sha256")
        size_bytes = _required_int(metadata, "size_bytes")
        mime_type = _required_string(metadata, "mime_type")
        width = _required_int(metadata, "width")
        height = _required_int(metadata, "height")
        digest = hashlib.sha256(data).hexdigest()
        png_width, png_height = _png_dimensions(data)
        if (
            not data
            or mime_type != "image/png"
            or size_bytes != len(data)
            or sha256 != digest
            or not data.startswith(b"\x89PNG\r\n\x1a\n")
            or width <= 0
            or height <= 0
            or (width, height) != (png_width, png_height)
        ):
            raise ApiError("image API response integrity check failed")
        return GeneratedImage(data, mime_type, digest, width, height)

    @staticmethod
    def _validate_request(
        prompt: str,
        width: int,
        height: int,
        seed: int,
        wait_seconds: int,
        allow_long_wait: bool,
    ) -> None:
        if not prompt.strip() or len(prompt) > 2048:
            raise ApiError("prompt must contain 1 to 2048 non-whitespace characters")
        if width < 256 or width > 1024 or width % 64:
            raise ApiError("width must be a multiple of 64 from 256 through 1024")
        if height < 256 or height > 1024 or height % 64:
            raise ApiError("height must be a multiple of 64 from 256 through 1024")
        if seed < 0 or seed > 2**63 - 1:
            raise ApiError("seed is outside the supported range")
        if isinstance(wait_seconds, bool) or wait_seconds < 0 or wait_seconds > 120:
            raise ApiError("wait must be an integer from 0 through 120 seconds")
        if wait_seconds > 60 and not allow_long_wait:
            raise ApiError("wait above 60 seconds requires --allow-long-wait")


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


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ApiError("image API response integrity check failed")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _safe_api_error(response: httpx.Response) -> str:
    request_id = response.headers.get("X-Request-ID")
    suffix = f" (request {request_id})" if request_id else ""
    return f"image API returned HTTP {response.status_code}{suffix}"


def _required_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError("image API returned a malformed response")
    return value


def _required_string(body: dict[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value:
        raise ApiError("image API returned a malformed response")
    return value


def _required_int(body: dict[str, Any], name: str) -> int:
    value = body.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError("image API returned a malformed response")
    return value


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname is None:
        raise ValueError("API base URL must be HTTPS")
    return parsed.scheme, parsed.hostname, parsed.port


def _same_origin_url(value: str, origin: tuple[str, str, int | None]) -> str:
    absolute = urljoin(f"{origin[0]}://{origin[1]}", value)
    if _origin(absolute) != origin:
        raise ApiError("image API returned an unsafe status URL")
    return absolute


def _retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "1")
    try:
        value = float(raw)
    except ValueError:
        return 1.0
    return min(10.0, max(0.1, value))
