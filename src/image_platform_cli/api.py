import hashlib
import os
import re
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from PIL import Image, UnidentifiedImageError

from .errors import ApiError
from .models import GeneratedImage

TERMINAL_FAILURES = frozenset({"failed", "partial", "cancelled"})
MAX_PAGE_SIZE = 100
MAX_ARTIFACT_DOWNLOAD_BYTES = 100 * 1024 * 1024
_SENSITIVE_RESPONSE_KEYS = frozenset(
    {"url", "signed_url", "object_key", "staging_key", "query", "upload"}
)
QueryValue = str | int | float | bool | None


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

    def list_jobs(
        self,
        access_token: str,
        *,
        statuses: Sequence[str] = (),
        operations: Sequence[str] = (),
        created_after: str | None = None,
        created_before: str | None = None,
        cursor: str | None = None,
        page_size: int = 20,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        params = _collection_params(
            page_size,
            cursor,
            ("status", statuses),
            ("operation", operations),
            ("created_after", created_after),
            ("created_before", created_before),
        )
        return self._collect("/v1/jobs", access_token, params, max_items)

    def get_job(self, access_token: str, job_id: str) -> dict[str, Any]:
        return self._safe_json("GET", f"/v1/jobs/{_resource_id(job_id)}", access_token)

    def cancel_job(self, access_token: str, job_id: str) -> dict[str, Any]:
        return self._safe_json("POST", f"/v1/jobs/{_resource_id(job_id)}/cancel", access_token)

    def get_job_previews(self, access_token: str, job_id: str) -> dict[str, Any]:
        return self._safe_json("GET", f"/v1/jobs/{_resource_id(job_id)}/previews", access_token)

    def list_artifacts(
        self,
        access_token: str,
        *,
        states: Sequence[str] = (),
        kinds: Sequence[str] = (),
        namespace: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        cursor: str | None = None,
        page_size: int = 20,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        params = _collection_params(
            page_size,
            cursor,
            ("state", states),
            ("kind", kinds),
            ("namespace", namespace),
            ("created_after", created_after),
            ("created_before", created_before),
        )
        return self._collect("/v1/artifacts", access_token, params, max_items)

    def get_artifact(self, access_token: str, artifact_id: str) -> dict[str, Any]:
        body = self._request_json("GET", f"/v1/artifacts/{_resource_id(artifact_id)}", access_token)
        return cast(dict[str, Any], _safe_projection(body))

    def download_artifact(self, access_token: str, artifact_id: str, output: Path) -> dict[str, Any]:
        require_available_output(output)
        body = self._request_json("GET", f"/v1/artifacts/{_resource_id(artifact_id)}", access_token)
        result = _required_dict(body.get("result"))
        metadata = _required_dict(result.get("artifact"))
        declared_size = _required_int(metadata, "size_bytes")
        if declared_size > MAX_ARTIFACT_DOWNLOAD_BYTES:
            raise ApiError("Artifact exceeds the download size limit")
        url = _required_string(result, "url")
        if urlsplit(url).scheme != "https":
            raise ApiError("image API returned an unsafe Artifact URL")
        try:
            response = self._http.get(url)
        except httpx.HTTPError as error:
            raise ApiError("Artifact download failed") from error
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        data = response.content
        _verify_artifact(data, response.headers.get("Content-Type"), metadata)
        _save_bytes_exclusive(data, output)
        return cast(dict[str, Any], _safe_projection(body))

    def search(
        self,
        access_token: str,
        *,
        query: str,
        namespace: str = "default",
        mime_types: Sequence[str] = (),
        created_after: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if not query.strip() or len(query) > 2048:
            raise ApiError("search query must contain 1 to 2048 non-whitespace characters")
        if limit < 1 or limit > 100:
            raise ApiError("limit must be from 1 through 100")
        filters: dict[str, object] = {"mime_type": list(mime_types)}
        if created_after is not None:
            filters["created_after"] = created_after
        return self._safe_json(
            "POST",
            "/v1/search",
            access_token,
            json={"query": query, "namespace": namespace, "filters": filters, "limit": limit},
        )

    def _collect(
        self,
        path: str,
        access_token: str,
        params: list[tuple[str, QueryValue]],
        max_items: int | None,
    ) -> dict[str, Any]:
        if max_items is not None and max_items < 1:
            raise ApiError("max-items must be greater than zero")
        collected: list[Any] = []
        next_cursor: str | None = None
        while True:
            page_params: list[tuple[str, QueryValue]] = [
                (key, value) for key, value in params if key != "cursor"
            ]
            if max_items is not None:
                remaining = max_items - len(collected)
                page_params = [
                    (key, min(cast(int, value), remaining) if key == "limit" else value)
                    for key, value in page_params
                ]
            if next_cursor is not None:
                page_params.append(("cursor", next_cursor))
            elif not collected:
                page_params.extend((key, value) for key, value in params if key == "cursor")
            page = self._request_json("GET", path, access_token, params=page_params)
            data = page.get("data")
            if not isinstance(data, list):
                raise ApiError("image API returned a malformed collection")
            collected.extend(data)
            next_value = page.get("next_cursor")
            if next_value is not None and not isinstance(next_value, str):
                raise ApiError("image API returned a malformed collection")
            next_cursor = next_value
            if max_items is None or next_cursor is None or len(collected) >= max_items:
                break
        if max_items is not None:
            collected = collected[:max_items]
        return cast(
            dict[str, Any],
            _safe_projection(
                {"data": collected, "next_cursor": next_cursor, "has_more": next_cursor is not None}
            ),
        )

    def _safe_json(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        json: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            _safe_projection(self._request_json(method, path, access_token, json=json)),
        )

    def _request_json(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        params: Sequence[tuple[str, str | int | float | bool | None]] = (),
        json: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(
                method,
                f"{self._api_base_url}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                params=list(params),
                json=json,
            )
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        try:
            return _required_dict(response.json())
        except ValueError as error:
            raise ApiError("image API returned a malformed response") from error

    def optimize_prompt(
        self,
        access_token: str,
        *,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        seed: int | None = None,
    ) -> str:
        """Request the server-owned Prompt Planner; never call its text provider directly."""

        if not prompt.strip() or len(prompt) > 2048:
            raise ApiError("prompt must contain 1 to 2048 non-whitespace characters")
        for name, value in (("width", width), ("height", height)):
            if value is not None and (value < 256 or value > 1024 or value % 64):
                raise ApiError(f"{name} must be a multiple of 64 from 256 through 1024")
        effective_seed = _resolve_seed(seed)
        payload: dict[str, object] = {
            "query": prompt,
            "profile": "generation-standard",
            "seed": effective_seed,
        }
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        try:
            response = self._http.post(
                f"{self._api_base_url}/v1/prompt-plans",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
            )
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        body = _required_dict(response.json())
        if _required_int(body, "seed") != effective_seed:
            raise ApiError("image API returned an unexpected effective seed")
        return _required_string(body, "prompt")

    def generate(
        self,
        access_token: str,
        *,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
        optimize: bool,
        wait_seconds: int = 30,
        allow_long_wait: bool = False,
    ) -> GeneratedImage:
        effective_seed = _resolve_seed(seed)
        self._validate_request(prompt, width, height, effective_seed, wait_seconds, allow_long_wait)
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
                    "seed": effective_seed,
                    "optimizer_enabled": optimize,
                    "execution": {
                        "wait_seconds": wait_seconds,
                        "allow_long_wait": allow_long_wait,
                        "accept_async": True,
                    },
                },
            )
            artifact, confirmed_seed = (
                self._poll(response, headers)
                if response.status_code == 202
                else self._artifact_from_completed_response(response)
            )
            if confirmed_seed != effective_seed:
                raise ApiError("image API returned an unexpected effective seed")
            image = self._download_artifact(artifact, confirmed_seed)
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        if image.width != width or image.height != height:
            raise ApiError("image API returned unexpected dimensions")
        return image

    def _poll(
        self, response: httpx.Response, headers: dict[str, str]
    ) -> tuple[dict[str, Any], int]:
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
                steps = snapshot.get("steps")
                if not isinstance(steps, list) or len(steps) != 1:
                    raise ApiError("image API returned a malformed Job result")
                values = _required_dict(_required_dict(steps[0]).get("value_outputs"))
                confirmed_seed = _required_int(values, "seed")
                artifact_response = self._http.get(
                    f"{self._api_base_url}/v1/artifacts/{artifact_id}", headers=headers
                )
                if not artifact_response.is_success:
                    raise ApiError(_safe_api_error(artifact_response))
                return _required_dict(artifact_response.json()), confirmed_seed
            if job_status in TERMINAL_FAILURES:
                raise ApiError(f"image generation ended with status {job_status}")
            delay = _retry_after(status_response)

    @staticmethod
    def _artifact_from_completed_response(
        response: httpx.Response,
    ) -> tuple[dict[str, Any], int]:
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        body = _required_dict(response.json())
        if _required_string(body, "status") != "completed":
            raise ApiError("image API returned a malformed completion")
        return _required_dict(body.get("result")), _required_int(body, "seed")

    def _download_artifact(self, artifact: dict[str, Any], seed: int) -> GeneratedImage:
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
        return GeneratedImage(data, mime_type, digest, width, height, seed)

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
    require_available_output(output)
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


def require_available_output(output: Path) -> None:
    """Reject known output conflicts before authentication or paid generation starts."""

    if not output.parent.is_dir():
        raise ApiError("output directory does not exist")
    if output.exists():
        raise ApiError("output file already exists")


def _save_bytes_exclusive(data: bytes, output: Path) -> None:
    temporary = output.with_name(f".{output.name}.{secrets.token_hex(8)}.part")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as error:
            raise ApiError("output file already exists") from error
        except OSError as error:
            raise ApiError("output file could not be written") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _verify_artifact(
    data: bytes, response_content_type: str | None, metadata: dict[str, Any]
) -> None:
    expected_sha = _required_string(metadata, "sha256")
    expected_size = _required_int(metadata, "size_bytes")
    expected_mime = _required_string(metadata, "mime_type")
    actual_content_type = response_content_type.split(";", 1)[0].strip() if response_content_type else None
    if (
        not data
        or hashlib.sha256(data).hexdigest() != expected_sha
        or len(data) != expected_size
        or actual_content_type != expected_mime
    ):
        raise ApiError("Artifact download integrity check failed")
    width = metadata.get("width")
    height = metadata.get("height")
    if width is None and height is None:
        return
    if not isinstance(width, int) or not isinstance(height, int) or isinstance(width, bool):
        raise ApiError("image API returned malformed Artifact metadata")
    expected_format = {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(expected_mime)
    if expected_format is None:
        raise ApiError("Artifact image MIME type cannot be verified")
    try:
        with Image.open(BytesIO(data)) as image:
            actual_format = image.format
            dimensions = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise ApiError("Artifact download integrity check failed") from error
    if actual_format != expected_format or dimensions != (width, height):
        raise ApiError("Artifact download integrity check failed")


def _safe_projection(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_projection(item)
            for key, item in value.items()
            if isinstance(key, str) and not _sensitive_response_key(key)
        }
    if isinstance(value, list):
        return [_safe_projection(item) for item in value]
    return value


def _sensitive_response_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _SENSITIVE_RESPONSE_KEYS or "prompt" in normalized


def _collection_params(
    page_size: int,
    cursor: str | None,
    *values: tuple[str, object],
) -> list[tuple[str, QueryValue]]:
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ApiError(f"page-size must be from 1 through {MAX_PAGE_SIZE}")
    params: list[tuple[str, QueryValue]] = [("limit", page_size)]
    if cursor is not None:
        params.append(("cursor", cursor))
    for key, value in values:
        if value is None:
            continue
        if isinstance(value, str):
            params.append((key, value))
        elif isinstance(value, Sequence):
            if not all(isinstance(item, (str, int, float, bool)) for item in value):
                raise ApiError(f"{key} contains an invalid value")
            params.extend((key, cast(str | int | float | bool, item)) for item in value)
        else:
            if not isinstance(value, (int, float, bool)):
                raise ApiError(f"{key} is invalid")
            params.append((key, value))
    return params


def _resource_id(value: str) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", value):
        raise ApiError("resource ID is invalid")
    return value


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ApiError("image API response integrity check failed")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _safe_api_error(response: httpx.Response) -> str:
    request_id = response.headers.get("X-Request-ID")
    suffix = f" (request {request_id})" if request_id else ""
    reason = ""
    try:
        body = response.json()
        code = body.get("code") if isinstance(body, dict) else None
        if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,64}", code):
            reason = f" [{code}]"
    except ValueError:
        pass
    return f"image API returned HTTP {response.status_code}{reason}{suffix}"


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


def _resolve_seed(seed: int | None) -> int:
    return secrets.randbelow(2**63 - 1) + 1 if seed is None else seed
