import base64
import hashlib
import re
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx

from ..common.errors import ApiError
from ..common.files import (
    read_image,
    require_available_output,
    save_bytes_exclusive,
    verify_artifact,
)
from ..common.inputs import (
    generation_execution,
    inline_image,
    require_one_image_source,
    validate_caption_controls,
)
from ..common.models import (
    DeterministicEditResult,
    GeneratedImage,
    PortraitMattingResult,
    SegmentationResult,
)
from .campaigns import IDENTITY_KEYS, TERMINAL, integer, number, rubric, validate_campaign
from .color_matching import ColorMatchOptions
from .compositing import CompositeOptions
from .conversion import prepare_conversion
from .crop import crop_program
from .filtering import filter_program
from .grayscale import grayscale_program
from .image_edits import ImageToImageOptions, verified_image
from .inpaint import prepare_inpaint, verify_inpaint
from .matting import prepare_matting, verify_matting
from .project_quad import QuadOptions
from .protocol import route_contract, verify_response
from .segmentation import SegmentSelector, prepare_segment, verify_segment
from .shapes import ShapeOptions
from .single_edits import prepare_single_edit, verify_single_edit
from .text_drawing import TextOptions

API_VERSION = "4"
CONTRACT_REVISION = "2026-09-09-r8"
CATALOG_REVISION = "2026-09-07-v4-r7"
REQUEST_ID = re.compile(r"req_[0-9a-f]{32}")
ARTIFACT_ID = re.compile(r"art_[A-Za-z0-9_-]{8,64}")
JOB_ID = re.compile(r"job_[A-Za-z0-9_-]{8,64}")
CONTRACT_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MIME_TYPE = re.compile(r"[a-z0-9.+-]+/[a-z0-9.+-]+")
MAX_ARTIFACT_DOWNLOAD_BYTES = 100 * 1024 * 1024
JOB_STATUSES = frozenset(
    {"accepted", "queued", "running", "completed", "partial", "failed", "cancelled"}
)
STEP_STATUSES = frozenset(
    {"pending", "ready", "running", "completed", "failed", "cancelled", "skipped"}
)
PREVIEW_STATUSES = frozenset({"pending", "processing", "ready", "failed", "unavailable", "expired"})
OPERATIONS = frozenset(
    {
        "optimize_prompt",
        "generate",
        "describe",
        "edit",
        "segment",
        "inpaint",
        "transform",
        "image_ops",
        "draw",
        "compose",
        "upscale",
        "restore",
        "embed",
        "index",
    }
)
QueryScalar = str | int | float | bool | None
QueryValue = QueryScalar | Sequence[QueryScalar]
QueryParams = (
    Mapping[str, QueryValue] | list[tuple[str, QueryScalar]] | tuple[tuple[str, QueryScalar], ...]
)


class V4ApiClient:
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
        self._sleep = sleeper
        self._clock = clock
        self._polling_timeout_seconds = polling_timeout_seconds

    def composite_image(
        self,
        access_token: str,
        *,
        background_path: Path,
        overlay_path: Path,
        mask_path: Path | None,
        options: CompositeOptions,
    ) -> DeterministicEditResult:
        extras = {"overlay": overlay_path}
        if mask_path is not None:
            extras["mask"] = mask_path
        payload, source = prepare_single_edit(
            background_path, options.program(masked=mask_path is not None), extra_inputs=extras
        )
        output_size = (
            (source["width"], source["height"]) if options.crop is None else options.crop[2:]
        )
        return self._single_image_operation(access_token, payload, source, output_size)

    def project_quad(
        self, access_token: str, *, input_path: Path, texture_path: Path, options: QuadOptions
    ) -> DeterministicEditResult:
        payload, source = prepare_single_edit(
            input_path, options.program(), extra_inputs={"texture": texture_path}
        )
        return self._single_image_operation(
            access_token, payload, source, (source["width"], source["height"])
        )

    def color_match(
        self,
        access_token: str,
        *,
        input_path: Path,
        reference_path: Path,
        options: ColorMatchOptions,
    ) -> DeterministicEditResult:
        payload, source = prepare_single_edit(
            input_path, options.program(), extra_inputs={"reference": reference_path}
        )
        return self._single_image_operation(
            access_token, payload, source, (source["width"], source["height"])
        )

    def draw_text(
        self, access_token: str, *, input_path: Path, options: TextOptions
    ) -> DeterministicEditResult:
        payload, source = prepare_single_edit(input_path, options.program())
        return self._single_image_operation(
            access_token, payload, source, (source["width"], source["height"])
        )

    def draw_shape(
        self, access_token: str, *, input_path: Path, options: ShapeOptions
    ) -> DeterministicEditResult:
        payload, source = prepare_single_edit(input_path, options.program())
        return self._single_image_operation(
            access_token, payload, source, (source["width"], source["height"])
        )

    def filter_image(
        self,
        access_token: str,
        *,
        input_path: Path,
        kind: str,
        radius: Decimal,
        amount: Decimal = Decimal(1),
    ) -> DeterministicEditResult:
        payload, source = prepare_single_edit(input_path, filter_program(kind, radius, amount))
        return self._single_image_operation(
            access_token, payload, source, (source["width"], source["height"])
        )

    def grayscale_image(self, access_token: str, *, input_path: Path) -> DeterministicEditResult:
        payload, source = prepare_single_edit(input_path, grayscale_program())
        return self._single_image_operation(
            access_token, payload, source, (source["width"], source["height"])
        )

    def crop_image(
        self, access_token: str, *, input_path: Path, rect: tuple[int, int, int, int]
    ) -> DeterministicEditResult:
        payload, source = prepare_single_edit(input_path, crop_program(rect))
        return self._single_image_operation(access_token, payload, source, (rect[2], rect[3]))

    def convert_image(
        self, access_token: str, *, input_path: Path, format_name: str, quality: int = 90
    ) -> DeterministicEditResult:
        payload, source = prepare_conversion(input_path, format_name, quality)
        return self._single_image_operation(
            access_token, payload, source, (source["width"], source["height"])
        )

    def _single_image_operation(
        self,
        access_token: str,
        payload: dict[str, Any],
        source: dict[str, Any],
        output_size: tuple[int, int],
    ) -> DeterministicEditResult:
        response, envelope = self._exchange(
            "POST", "/v4/image-operations", access_token, json=payload
        )
        if not response.is_success:
            raise ApiError(_safe_error(envelope))
        return verify_single_edit(
            response, self._object(envelope["data"]), payload["program"], source, output_size
        )

    def portrait_matting(
        self,
        access_token: str,
        *,
        input_path: Path,
        person_mask_path: Path,
        uncertainty_radius: int = 16,
    ) -> PortraitMattingResult:
        payload, inputs = prepare_matting(input_path, person_mask_path, uncertainty_radius)
        response, envelope = self._exchange(
            "POST", "/v4/portrait-mattings", access_token, json=payload
        )
        if not response.is_success:
            raise ApiError(_safe_error(envelope))
        return verify_matting(response, self._object(envelope["data"]), inputs, uncertainty_radius)

    def segment(
        self,
        access_token: str,
        *,
        input_path: Path,
        selector: SegmentSelector,
    ) -> SegmentationResult:
        payload, source, metadata = prepare_segment(input_path, selector)
        response, envelope = self._exchange("POST", "/v4/segmentations", access_token, json=payload)
        if not response.is_success:
            raise ApiError(_safe_error(envelope))
        return verify_segment(response, self._object(envelope["data"]), source, metadata)

    def inpaint(
        self,
        access_token: str,
        *,
        input_path: Path,
        mask_path: Path,
        prompt: str,
        seed: int,
        profile: str = "inpaint-stable-diffusion-v1-5",
        safety_filter: str = "default",
    ) -> GeneratedImage:
        payload, source, mask = prepare_inpaint(
            input_path, mask_path, prompt, seed, profile, safety_filter
        )
        response, envelope = self._exchange("POST", "/v4/inpaints", access_token, json=payload)
        if not response.is_success:
            raise ApiError(_safe_error(envelope))
        return verify_inpaint(response, self._object(envelope["data"]), payload, source, mask)

    def image_to_image(
        self,
        access_token: str,
        *,
        options: ImageToImageOptions,
        input_path: Path | None = None,
        artifact_id: str | None = None,
    ) -> GeneratedImage:
        require_one_image_source(input_path, artifact_id, operation="image-to-image")
        image_input: dict[str, Any]
        if input_path is not None:
            raw, mime, width, height = read_image(input_path)
            source = {"sha256": hashlib.sha256(raw).hexdigest(), "width": width, "height": height}
            image_input = {
                "input": {"mime_type": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
            }
        else:
            assert artifact_id is not None
            artifact = self.get_artifact(access_token, artifact_id)
            content = artifact["content"]
            if artifact["state"] != "ready" or not isinstance(content, dict):
                raise ApiError("image-to-image Artifact is not ready")
            source = {key: content[key] for key in ("sha256", "width", "height")}
            image_input = {"artifact_id": artifact_id}
        payload = {**options.payload(source), **image_input}
        response, envelope = self._exchange("POST", "/v4/image-edits", access_token, json=payload)
        if not response.is_success:
            raise ApiError(_safe_error(envelope))
        return verified_image(response, self._object(envelope["data"]), payload, source)

    def capabilities(self, access_token: str) -> dict[str, Any]:
        data = self._object(self._request("GET", "/v4/capabilities", access_token))
        _validate_capability_list(data)
        return data

    def model_profiles(self, access_token: str) -> dict[str, Any]:
        return self._object(self._request("GET", "/v4/model-profiles", access_token))

    def optimize_prompt(
        self,
        access_token: str,
        *,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        if not prompt.strip():
            raise ApiError("prompt must contain non-whitespace text")
        for name, value in (("width", width), ("height", height)):
            if value is not None and not 256 <= value <= 1024:
                raise ApiError(f"{name} must be from 256 through 1024")
        effective_seed = secrets.randbelow(2**63) if seed is None else seed
        if isinstance(effective_seed, bool) or not 0 <= effective_seed <= 2**63 - 1:
            raise ApiError("seed is outside the supported range")
        payload: dict[str, object] = {
            "query": prompt,
            "profile": "generation-standard",
            "seed": effective_seed,
        }
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        result = self._object(self._request("POST", "/v4/prompt-plans", access_token, json=payload))
        _validate_prompt_plan(result, effective_seed)
        return result

    def generate(
        self,
        access_token: str,
        *,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
        optimize: bool = False,
        wait_seconds: int = 30,
        allow_long_wait: bool = False,
    ) -> GeneratedImage:
        if not prompt.strip():
            raise ApiError("prompt must contain non-whitespace text")
        if not 256 <= width <= 1024 or not 256 <= height <= 1024:
            raise ApiError("image dimensions must be from 256 through 1024")
        effective_seed = secrets.randbelow(2**63) if seed is None else seed
        if isinstance(effective_seed, bool) or not 0 <= effective_seed <= 2**63 - 1:
            raise ApiError("seed is outside the supported range")
        if (
            isinstance(wait_seconds, bool)
            or not 0 <= wait_seconds <= 120
            or (wait_seconds > 60 and not allow_long_wait)
        ):
            raise ApiError("wait must satisfy the Native API V4 execution policy")
        response, envelope = self._exchange(
            "POST",
            "/v4/generations",
            access_token,
            headers={"Idempotency-Key": secrets.token_hex(16)},
            json={
                "query": prompt,
                "profile": "generation-standard",
                "width": width,
                "height": height,
                "seed": effective_seed,
                "optimizer_enabled": optimize,
                "execution": generation_execution(wait_seconds, allow_long_wait),
            },
        )
        if not response.is_success:
            raise ApiError(_safe_error(envelope))
        data = self._object(envelope.get("data"))
        if response.headers.get("idempotent-replay") not in {"true", "false"}:
            raise ApiError("image API returned malformed generation headers")
        if response.status_code == 200:
            metadata = _validate_generation_completed(data, effective_seed)
            sha256 = cast(dict[str, Any], metadata["content"])["sha256"]
            if response.headers.get("x-image-sha256") != sha256:
                raise ApiError("image API returned inconsistent generation headers")
        elif response.status_code == 202:
            job_id = _validate_accepted_generation(response, data, self._api_base_url)
            metadata, effective_seed = self._poll_generation(access_token, job_id, effective_seed)
        else:
            raise ApiError("image API returned an unexpected generation status")
        image = self._download_generated_image(access_token, metadata, effective_seed)
        if (image.width, image.height) != (width, height):
            raise ApiError("image API returned unexpected dimensions")
        return image

    def list_jobs(
        self,
        access_token: str,
        *,
        params: list[tuple[str, QueryScalar]] | tuple[tuple[str, QueryScalar], ...] = (),
    ) -> dict[str, Any]:
        data = self._object(self._request("GET", "/v4/jobs", access_token, params=params))
        _validate_job_list(data)
        return data

    def search(
        self,
        access_token: str,
        *,
        query: str | None = None,
        image_path: Path | None = None,
        artifact_id: str | None = None,
        namespace: str = "default",
        mime_types: Sequence[str] = (),
        created_after: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if sum(value is not None for value in (query, image_path, artifact_id)) != 1:
            raise ApiError("exactly one search source is required")
        if query is not None and (not query.strip() or len(query) > 2048):
            raise ApiError("search query must contain 1 to 2048 non-whitespace characters")
        if not 1 <= limit <= 100:
            raise ApiError("limit must be from 1 through 100")
        payload: dict[str, object] = {
            "namespace": namespace,
            "filters": {
                "mime_type": list(mime_types),
                **({"created_after": created_after} if created_after is not None else {}),
            },
            "limit": limit,
        }
        if query is not None:
            payload["query"] = query
        elif image_path is not None:
            data, mime_type, _, _ = read_image(image_path)
            payload["image"] = {
                "mime_type": mime_type,
                "data_base64": base64.b64encode(data).decode("ascii"),
            }
        else:
            payload["artifact_id"] = artifact_id
        result = self._object(
            self._request("POST", "/v4/artifacts/search", access_token, json=payload)
        )
        _validate_search_response(result)
        return result

    def caption(
        self,
        access_token: str,
        *,
        input_path: Path | None = None,
        artifact_id: str | None = None,
        instruction: str = "Describe this image concisely.",
        max_output_tokens: int = 128,
    ) -> dict[str, Any]:
        require_one_image_source(input_path, artifact_id, operation="caption")
        validate_caption_controls(instruction, max_output_tokens)
        payload: dict[str, object] = {
            "instruction": instruction,
            "max_output_tokens": max_output_tokens,
        }
        if input_path is not None:
            payload["input"] = inline_image(input_path)
        else:
            payload["artifact_id"] = artifact_id
        result = self._object(self._request("POST", "/v4/captions", access_token, json=payload))
        _validate_caption(result)
        return result

    def create_batch_plan(
        self,
        access_token: str,
        *,
        intent: str,
        width: int = 1024,
        height: int = 1024,
        candidate_count: int = 1,
        root_seed: int | None = None,
        optimize: bool = True,
    ) -> dict[str, Any]:
        seed = secrets.randbelow(2**63) if root_seed is None else root_seed
        if (
            not intent.strip()
            or any(value < 256 or value > 1024 or value % 64 for value in (width, height))
            or not 1 <= candidate_count <= 16
            or isinstance(seed, bool)
            or not 0 <= seed <= 2**63 - 1
        ):
            raise ApiError("BatchPlan inputs are outside the accepted bounds")
        result = self._object(
            self._request(
                "POST",
                "/v4/batch-plans",
                access_token,
                headers={"Idempotency-Key": secrets.token_hex(16)},
                json={
                    "intent": intent,
                    "profile": "generation-standard",
                    "width": width,
                    "height": height,
                    "candidate_count": candidate_count,
                    "root_seed": seed,
                    "optimize": optimize,
                },
            )
        )
        _validate_batch_plan(result, seed, candidate_count)
        return result

    def get_job(self, access_token: str, job_id: str) -> dict[str, Any]:
        data = self._object(self._request("GET", f"/v4/jobs/{_path_id(job_id)}", access_token))
        _validate_job(data)
        if data["job_id"] != job_id:
            raise ApiError("image API returned an unexpected Job")
        return data

    def cancel_job(self, access_token: str, job_id: str) -> dict[str, Any]:
        data = self._object(
            self._request("POST", f"/v4/jobs/{_path_id(job_id)}/cancel", access_token)
        )
        _validate_job(data)
        if data["job_id"] != job_id:
            raise ApiError("image API returned an unexpected Job")
        return data

    def job_previews(self, access_token: str, job_id: str) -> dict[str, Any]:
        data = self._object(
            self._request("GET", f"/v4/jobs/{_path_id(job_id)}/previews", access_token)
        )
        _validate_job_previews(data)
        return data

    def job_preview_access(
        self, access_token: str, job_id: str, step_id: str, output: str
    ) -> dict[str, Any]:
        path = f"/v4/jobs/{_path_id(job_id)}/previews/{_path_id(step_id)}/{_path_id(output)}/access"
        data = self._object(self._request("POST", path, access_token))
        _validate_preview_access(data)
        return data

    def list_artifacts(
        self,
        access_token: str,
        *,
        params: list[tuple[str, QueryScalar]] | tuple[tuple[str, QueryScalar], ...] = (),
    ) -> dict[str, Any]:
        data = self._object(self._request("GET", "/v4/artifacts", access_token, params=params))
        _validate_artifact_list(data)
        return data

    def get_artifact(self, access_token: str, artifact_id: str) -> dict[str, Any]:
        data = self._object(
            self._request("GET", f"/v4/artifacts/{_path_id(artifact_id)}", access_token)
        )
        _validate_artifact_metadata(data)
        if data["artifact_id"] != artifact_id:
            raise ApiError("image API returned an unexpected Artifact")
        return data

    def access_artifact(self, access_token: str, artifact_id: str) -> dict[str, Any]:
        data = self._object(
            self._request("POST", f"/v4/artifacts/{_path_id(artifact_id)}/access", access_token)
        )
        _validate_artifact_access(data)
        return data

    def delete_artifact(self, access_token: str, artifact_id: str) -> dict[str, Any]:
        data = self._object(
            self._request("DELETE", f"/v4/artifacts/{_path_id(artifact_id)}", access_token)
        )
        if (
            set(data) != {"artifact_id", "deleted_at"}
            or data.get("artifact_id") != artifact_id
            or not _timestamp(data.get("deleted_at"))
        ):
            raise ApiError("image API returned an inconsistent Artifact deletion receipt")
        return data

    def upload_artifact(
        self,
        access_token: str,
        input_path: Path,
        *,
        namespace: str = "default",
        kind: str = "image",
    ) -> dict[str, Any]:
        data, mime_type, width, height = read_image(input_path)
        reserved = self._object(
            self._request(
                "POST",
                "/v4/artifacts/uploads",
                access_token,
                json={"namespace": namespace, "kind": kind, "mime_type": mime_type},
            )
        )
        artifact_id, upload_url, upload_headers = _validate_upload_reservation(reserved)
        try:
            response = self._http.put(upload_url, content=data, headers=upload_headers)
        except httpx.HTTPError as error:
            raise ApiError("Artifact upload failed") from error
        if not response.is_success:
            raise ApiError("Artifact upload failed")
        digest = hashlib.sha256(data).hexdigest()
        completed = self._object(
            self._request(
                "POST",
                f"/v4/artifacts/{artifact_id}/upload-completion",
                access_token,
                json={
                    "sha256": digest,
                    "mime_type": mime_type,
                    "size_bytes": len(data),
                    "width": width,
                    "height": height,
                },
            )
        )
        _validate_artifact_metadata(completed)
        content = completed.get("content")
        if (
            completed.get("artifact_id") != artifact_id
            or completed.get("state") != "ready"
            or not isinstance(content, dict)
            or content.get("sha256") != digest
            or content.get("mime_type") != mime_type
            or content.get("size_bytes") != len(data)
            or content.get("width") != width
            or content.get("height") != height
        ):
            raise ApiError("image API returned an inconsistent Artifact completion receipt")
        return completed

    def download_artifact(
        self, access_token: str, artifact_id: str, output: Path
    ) -> dict[str, Any]:
        require_available_output(output)
        metadata = self.get_artifact(access_token, artifact_id)
        access = self.access_artifact(access_token, artifact_id)
        descriptor = self._object(access["artifact"])
        if metadata.get("state") != "ready" or metadata.get("content") != descriptor:
            raise ApiError("image API returned inconsistent Artifact access metadata")
        size_bytes = descriptor.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes > MAX_ARTIFACT_DOWNLOAD_BYTES:
            raise ApiError("Artifact exceeds the download size limit")
        url = access["url"]
        if not isinstance(url, str) or urlsplit(url).scheme != "https":
            raise ApiError("image API returned an unsafe Artifact URL")
        data, content_type = self._download_bytes(url, size_bytes)
        verify_artifact(data, content_type, descriptor)
        save_bytes_exclusive(data, output)
        return metadata

    def _poll_generation(
        self, access_token: str, job_id: str, requested_seed: int
    ) -> tuple[dict[str, Any], int]:
        deadline = self._clock() + self._polling_timeout_seconds
        while True:
            if self._clock() >= deadline:
                raise ApiError("image generation polling timed out; the Job may still be running")
            self._sleep(1.0)
            job = self.get_job(access_token, job_id)
            status = job["status"]
            if status == "completed":
                outputs = job["outputs"]
                if not isinstance(outputs, list) or len(outputs) != 1:
                    raise ApiError("image API returned a malformed generation Job")
                output = self._object(outputs[0])
                artifact_id = output.get("artifact_id")
                if not isinstance(artifact_id, str):
                    raise ApiError("image API returned a malformed generation Job")
                seed = _job_seed(job)
                if seed != requested_seed:
                    raise ApiError("image API returned an unexpected effective seed")
                return self.get_artifact(access_token, artifact_id), seed
            if status in {"failed", "partial", "cancelled"}:
                raise ApiError(f"image generation ended with status {status}")

    def _download_generated_image(
        self, access_token: str, metadata: dict[str, Any], seed: int
    ) -> GeneratedImage:
        artifact_id = metadata.get("artifact_id")
        content = metadata.get("content")
        if (
            metadata.get("state") != "ready"
            or not isinstance(artifact_id, str)
            or not isinstance(content, dict)
        ):
            raise ApiError("image API returned incomplete generation Artifact metadata")
        access = self.access_artifact(access_token, artifact_id)
        descriptor = self._object(access["artifact"])
        if descriptor != content:
            raise ApiError("image API returned inconsistent generation Artifact metadata")
        url = access["url"]
        if not isinstance(url, str):
            raise ApiError("image API returned an unsafe Artifact URL")
        data, content_type = self._download_bytes(url, descriptor["size_bytes"])
        verify_artifact(data, content_type, descriptor)
        return GeneratedImage(
            data,
            str(descriptor["mime_type"]),
            str(descriptor["sha256"]),
            int(descriptor["width"]),
            int(descriptor["height"]),
            seed,
        )

    def _download_bytes(self, url: str, expected_size: int) -> tuple[bytes, str | None]:
        if not integer(expected_size, 1, MAX_ARTIFACT_DOWNLOAD_BYTES):
            raise ApiError("Artifact exceeds the download size limit")
        try:
            with self._http.stream("GET", url, auth=None) as response:
                if response.status_code != 200:
                    raise ApiError("Artifact download failed")
                chunks = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(chunks) + len(chunk) > expected_size:
                        raise ApiError("Artifact download exceeds its declared size")
                    chunks.extend(chunk)
                return bytes(chunks), response.headers.get("Content-Type")
        except httpx.HTTPError as error:
            raise ApiError("Artifact download failed") from error

    def get_batch_plan(self, access_token: str, plan_id: str) -> dict[str, Any]:
        result = self._object(
            self._request("GET", f"/v4/batch-plans/{_path_id(plan_id)}", access_token)
        )
        items = result.get("items")
        if not isinstance(items, list) or not integer(result.get("root_seed"), 0, 2**63 - 1):
            raise ApiError("image API returned malformed BatchPlan")
        _validate_batch_plan(result, result["root_seed"], len(items))
        if result["plan_id"] != plan_id:
            raise ApiError("image API returned an unexpected BatchPlan")
        return result

    def evaluation_rubrics(self, access_token: str) -> list[dict[str, Any]]:
        data = self._request("GET", "/v4/evaluation-rubrics", access_token)
        if not isinstance(data, list):
            raise ApiError("image API returned malformed evaluation rubrics")
        return [rubric(item) for item in data]

    def create_campaign(
        self,
        access_token: str,
        *,
        plan_id: str,
        max_cost_usd: Decimal,
        allow_partial: bool = False,
        wait_seconds: int = 0,
        allow_long_wait: bool = False,
        score_threshold: Decimal | None = None,
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        maximum = number(max_cost_usd)
        if maximum == 0:
            raise ApiError("max-cost must be positive")
        if not integer(wait_seconds, 0, 1500) or (wait_seconds > 60 and not allow_long_wait):
            raise ApiError("wait above 60 seconds requires --allow-long-wait; maximum is 1500")
        payload: dict[str, Any] = {
            "plan_id": _path_id(plan_id),
            "max_cost_usd": str(maximum),
            "allow_partial": allow_partial,
        }
        if score_threshold is not None:
            number(score_threshold, maximum=Decimal(1))
            if not integer(max_rounds, 1, 3):
                raise ApiError("max-rounds must be from 1 through 3")
            plan = self.get_batch_plan(access_token, plan_id)
            available = self.evaluation_rubrics(access_token)
            if len(available) != 1:
                raise ApiError("expected exactly one default evaluation rubric")
            selected = available[0]
            count = len(plan["items"])
            if (
                not 1 <= count <= selected["max_candidates_per_round"]
                or max_rounds > selected["max_rounds"]
            ):
                raise ApiError("iteration exceeds the discovered rubric limits")
            payload["iteration_policy"] = {
                **{key: selected[key] for key in IDENTITY_KEYS},
                "score_threshold": str(score_threshold),
                "max_rounds": max_rounds,
                "candidates_per_round": count,
            }
        response, envelope = self._exchange(
            "POST",
            "/v4/campaigns",
            access_token,
            json=payload,
            headers={"Idempotency-Key": secrets.token_hex(16)},
        )
        if not response.is_success:
            raise ApiError(_safe_error(envelope))
        if response.status_code != 202 or response.headers.get("idempotent-replay") not in {
            "true",
            "false",
        }:
            raise ApiError("image API returned invalid Campaign acceptance headers")
        result = self._object(envelope.get("data"))
        validate_campaign(result)
        if (
            result["plan_id"] != plan_id
            or number(result["max_cost_usd"]) != maximum
            or result["allow_partial"] != allow_partial
            or result["iteration_policy"] != payload.get("iteration_policy")
        ):
            raise ApiError("image API returned an inconsistent Campaign acceptance")
        deadline = self._clock() + wait_seconds
        while result["status"] not in TERMINAL and self._clock() < deadline:
            self._sleep(min(1.0, max(0.0, deadline - self._clock())))
            result = self.get_campaign(access_token, result["campaign_id"])
        return result

    def get_campaign(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        return self._campaign_request("GET", access_token, campaign_id)

    def cancel_campaign(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        return self._campaign_request("POST", access_token, campaign_id, suffix="/cancel")

    def _campaign_request(
        self, method: str, access_token: str, campaign_id: str, *, suffix: str = ""
    ) -> dict[str, Any]:
        data = self._object(
            self._request(method, f"/v4/campaigns/{_path_id(campaign_id)}{suffix}", access_token)
        )
        validate_campaign(data)
        if data["campaign_id"] != campaign_id:
            raise ApiError("image API returned an unexpected Campaign")
        return data

    def campaign_evaluation(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        campaign = self.get_campaign(access_token, campaign_id)
        if campaign["iteration_policy"] is None:
            raise ApiError("Campaign has no iteration evaluation policy")
        return {
            key: campaign[key]
            for key in (
                "campaign_id",
                "status",
                "iteration_policy",
                "rounds",
                "stop_reason",
                "actual_cost_usd",
                "max_cost_usd",
            )
        }

    def campaign_results(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        campaign = self.get_campaign(access_token, campaign_id)
        jobs = [self.get_job(access_token, job_id) for job_id in campaign["child_job_ids"]]
        artifacts = [
            {"job_id": job["job_id"], "artifact_id": output["artifact_id"]}
            for job in jobs
            for output in job["outputs"]
        ]
        return {"campaign": campaign, "jobs": jobs, "artifacts": artifacts}

    def _request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        params: QueryParams | None = None,
    ) -> object:
        response, body = self._exchange(
            method, path, access_token, headers=headers, json=json, params=params
        )
        if not response.is_success:
            raise ApiError(_safe_error(body))
        if "data" not in body:
            raise ApiError("image API returned a malformed success envelope")
        return body["data"]

    def _exchange(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        params: QueryParams | None = None,
    ) -> tuple[httpx.Response, dict[str, Any]]:
        contract = route_contract(method, path)
        request_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            **(headers or {}),
        }
        try:
            response = self._http.request(
                method,
                f"{self._api_base_url}{path}",
                headers=request_headers,
                json=json,
                params=httpx.QueryParams(params) if params is not None else None,
            )
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        body = _response_object(response)
        _validate_common_response(response, body)
        verify_response(response, body, contract)
        return response, body

    @staticmethod
    def _object(data: object) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ApiError("image API returned malformed response data")
        return data


def _response_object(response: httpx.Response) -> dict[str, Any]:
    if response.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise ApiError("image API returned a non-JSON response")
    try:
        body = response.json()
    except ValueError as error:
        raise ApiError("image API returned invalid JSON") from error
    if not isinstance(body, dict):
        raise ApiError("image API returned a malformed envelope")
    return body


def _validate_common_response(response: httpx.Response, body: dict[str, Any]) -> None:
    if response.headers.get("cache-control") != "no-store":
        raise ApiError("image API response is missing the no-store policy")
    request_id = response.headers.get("x-request-id")
    meta = body.get("meta")
    if (
        not isinstance(meta, dict)
        or set(meta) != {"request_id", "api_version", "contract_revision"}
        or not isinstance(request_id, str)
        or REQUEST_ID.fullmatch(request_id) is None
        or meta.get("request_id") != request_id
        or meta.get("api_version") != API_VERSION
        or meta.get("contract_revision") != CONTRACT_REVISION
    ):
        raise ApiError("image API returned inconsistent V4 response metadata")


def _safe_error(body: dict[str, Any]) -> str:
    error = body.get("error")
    if not isinstance(error, dict):
        return "image API request failed"
    code = error.get("code")
    message = error.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        return "image API request failed"
    return f"{code}: {message}"


def _path_id(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ApiError("resource ID is invalid")
    return value


def _validate_capability_list(data: dict[str, Any]) -> None:
    if (
        set(data) != {"catalog_revision", "items"}
        or data.get("catalog_revision") != CATALOG_REVISION
    ):
        raise ApiError("image API returned malformed capability data")
    items = data.get("items")
    if not isinstance(items, list):
        raise ApiError("image API returned malformed capability data")
    identifiers: list[str] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "id",
            "kind",
            "family",
            "availability_domain",
            "semantic_authorization_scopes",
            "bindings",
        }:
            raise ApiError("image API returned malformed capability data")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ApiError("image API returned malformed capability data")
        identifiers.append(identifier)
        if item.get("kind") not in {
            "user_capability",
            "application_template",
            "service_contract",
            "resource_protocol",
        } or item.get("availability_domain") not in {"v4_callable", "platform_only"}:
            raise ApiError("image API returned malformed capability data")
        _string_list(item.get("semantic_authorization_scopes"), "capability data")
        bindings = item.get("bindings")
        if not isinstance(bindings, list):
            raise ApiError("image API returned malformed capability data")
        for binding in bindings:
            _validate_capability_binding(binding)
    if identifiers != sorted(identifiers) or len(identifiers) != len(set(identifiers)):
        raise ApiError("image API returned unsorted or duplicate capability data")


def _validate_capability_binding(binding: object) -> None:
    if not isinstance(binding, dict) or set(binding) != {
        "route_id",
        "method",
        "path_template",
        "required_oauth_scopes",
        "configured",
        "authorized",
        "reason",
    }:
        raise ApiError("image API returned malformed capability binding")
    for name in ("route_id", "path_template"):
        if not isinstance(binding.get(name), str) or not binding[name]:
            raise ApiError("image API returned malformed capability binding")
    if binding.get("method") not in {"GET", "POST", "DELETE"}:
        raise ApiError("image API returned malformed capability binding")
    _string_list(binding.get("required_oauth_scopes"), "capability binding")
    configured = binding.get("configured")
    authorized = binding.get("authorized")
    reason = binding.get("reason")
    if not isinstance(configured, bool) or not isinstance(authorized, bool):
        raise ApiError("image API returned malformed capability binding")
    expected_reason = (
        None if authorized else ("insufficient_scope" if configured else "service_not_configured")
    )
    if reason != expected_reason:
        raise ApiError("image API returned inconsistent capability binding")


def _string_list(value: object, name: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ApiError(f"image API returned malformed {name}")


def _validate_artifact_metadata(data: dict[str, Any]) -> None:
    if set(data) != {
        "artifact_id",
        "namespace",
        "kind",
        "state",
        "created_at",
        "upload_expires_at",
        "ready_at",
        "content",
    }:
        raise ApiError("image API returned malformed Artifact metadata")
    if (
        not _matches(data.get("artifact_id"), ARTIFACT_ID)
        or not _matches(data.get("namespace"), CONTRACT_ID)
        or data.get("kind") not in {"image", "mask", "file"}
        or data.get("state") not in {"reserved", "ready"}
        or not _timestamp(data.get("created_at"))
        or not _timestamp(data.get("upload_expires_at"))
    ):
        raise ApiError("image API returned malformed Artifact metadata")
    if data["state"] == "reserved":
        if data["ready_at"] is not None or data["content"] is not None:
            raise ApiError("image API returned inconsistent Artifact metadata")
    elif not _timestamp(data["ready_at"]) or not isinstance(data["content"], dict):
        raise ApiError("image API returned inconsistent Artifact metadata")
    else:
        _validate_artifact_descriptor(data["content"])


def _validate_job_list(data: dict[str, Any]) -> None:
    if (
        set(data) != {"data", "next_cursor", "has_more"}
        or not isinstance(data.get("data"), list)
        or (data.get("next_cursor") is not None and not isinstance(data["next_cursor"], str))
        or not isinstance(data.get("has_more"), bool)
        or data["has_more"] != (data["next_cursor"] is not None)
    ):
        raise ApiError("image API returned malformed Job collection")
    for item in data["data"]:
        if not isinstance(item, dict) or set(item) != {
            "job_id",
            "status",
            "source_api",
            "submitted_at",
            "operations",
            "estimated_cost_usd",
            "actual_cost_usd",
            "outputs",
        }:
            raise ApiError("image API returned malformed Job collection")
        if (
            not _matches(item.get("job_id"), JOB_ID)
            or item.get("status") not in JOB_STATUSES
            or not isinstance(item.get("source_api"), str)
            or not item["source_api"]
            or not _timestamp(item.get("submitted_at"))
            or not _operation_list(item.get("operations"))
            or not _nonnegative_decimal(item.get("estimated_cost_usd"))
            or not _nonnegative_decimal(item.get("actual_cost_usd"))
            or not isinstance(item.get("outputs"), list)
        ):
            raise ApiError("image API returned malformed Job collection")
        for output in item["outputs"]:
            if not isinstance(output, dict):
                raise ApiError("image API returned malformed Job collection")
            _validate_artifact_descriptor(output)


def _validate_job(data: dict[str, Any]) -> None:
    if set(data) != {
        "job_id",
        "status",
        "graph_sha256",
        "steps",
        "outputs",
        "result_manifest",
        "cost",
    }:
        raise ApiError("image API returned malformed Job")
    if (
        not _matches(data.get("job_id"), JOB_ID)
        or data.get("status") not in JOB_STATUSES
        or (data.get("graph_sha256") is not None and not _matches(data["graph_sha256"], SHA256))
        or not isinstance(data.get("steps"), list)
        or not isinstance(data.get("outputs"), list)
        or not isinstance(data.get("result_manifest"), dict)
        or not isinstance(data.get("cost"), dict)
    ):
        raise ApiError("image API returned malformed Job")
    for step in data["steps"]:
        if not isinstance(step, dict) or set(step) != {
            "id",
            "status",
            "attempt",
            "value_outputs",
            "error_code",
            "error_detail",
        }:
            raise ApiError("image API returned malformed Job step")
        if (
            not _matches(step.get("id"), CONTRACT_ID)
            or step.get("status") not in STEP_STATUSES
            or not _positive_int(step.get("attempt"))
            or not isinstance(step.get("value_outputs"), dict)
            or (
                step.get("error_code") is not None and not _matches(step["error_code"], CONTRACT_ID)
            )
            or (step.get("error_detail") is not None and not isinstance(step["error_detail"], dict))
        ):
            raise ApiError("image API returned malformed Job step")
    for output in data["outputs"]:
        if not isinstance(output, dict):
            raise ApiError("image API returned malformed Job output")
        _validate_artifact_descriptor(output)
    for name, output in data["result_manifest"].items():
        if not _matches(name, CONTRACT_ID) or not isinstance(output, dict):
            raise ApiError("image API returned malformed Job manifest")
        _validate_artifact_descriptor(output)
    cost = data["cost"]
    if set(cost) != {"estimated_usd", "actual_usd"} or not all(
        _nonnegative_decimal(cost.get(name)) for name in ("estimated_usd", "actual_usd")
    ):
        raise ApiError("image API returned malformed Job cost")


def _validate_job_previews(data: dict[str, Any]) -> None:
    if (
        set(data) != {"job_id", "previews"}
        or not _matches(data.get("job_id"), JOB_ID)
        or not isinstance(data.get("previews"), list)
    ):
        raise ApiError("image API returned malformed Job previews")
    for preview in data["previews"]:
        if not isinstance(preview, dict) or set(preview) != {
            "step_id",
            "output",
            "status",
            "renderer_revision",
            "artifact",
            "expires_at",
            "error_code",
        }:
            raise ApiError("image API returned malformed Job preview")
        artifact = preview.get("artifact")
        if (
            not _matches(preview.get("step_id"), CONTRACT_ID)
            or not _matches(preview.get("output"), CONTRACT_ID)
            or preview.get("status") not in PREVIEW_STATUSES
            or (
                preview.get("renderer_revision") is not None
                and not _matches(preview["renderer_revision"], CONTRACT_ID)
            )
            or (artifact is not None and not isinstance(artifact, dict))
            or (preview.get("expires_at") is not None and not _timestamp(preview["expires_at"]))
            or (
                preview.get("error_code") is not None
                and not _matches(preview["error_code"], CONTRACT_ID)
            )
        ):
            raise ApiError("image API returned malformed Job preview")
        if isinstance(artifact, dict):
            _validate_artifact_descriptor(artifact)


def _validate_preview_access(data: dict[str, Any]) -> None:
    if set(data) != {
        "step_id",
        "output",
        "renderer_revision",
        "artifact",
        "url",
        "url_expires_at",
        "preview_expires_at",
    }:
        raise ApiError("image API returned malformed preview access")
    artifact = data.get("artifact")
    if (
        not _matches(data.get("step_id"), CONTRACT_ID)
        or not _matches(data.get("output"), CONTRACT_ID)
        or not _matches(data.get("renderer_revision"), CONTRACT_ID)
        or not isinstance(artifact, dict)
        or not isinstance(data.get("url"), str)
        or urlsplit(data["url"]).scheme != "https"
        or not _timestamp(data.get("url_expires_at"))
        or not _timestamp(data.get("preview_expires_at"))
    ):
        raise ApiError("image API returned malformed preview access")
    _validate_artifact_descriptor(artifact)


def _validate_artifact_list(data: dict[str, Any]) -> None:
    if (
        set(data) != {"data", "next_cursor", "has_more"}
        or not isinstance(data.get("data"), list)
        or (data.get("next_cursor") is not None and not isinstance(data["next_cursor"], str))
        or not isinstance(data.get("has_more"), bool)
        or data["has_more"] != (data["next_cursor"] is not None)
    ):
        raise ApiError("image API returned malformed Artifact collection")
    for item in data["data"]:
        if not isinstance(item, dict) or set(item) != {
            "artifact_id",
            "namespace",
            "kind",
            "state",
            "created_at",
            "ready_at",
            "sha256",
            "mime_type",
            "size_bytes",
            "width",
            "height",
        }:
            raise ApiError("image API returned malformed Artifact collection")
        ready = item.get("state") == "ready"
        content = (item.get("sha256"), item.get("mime_type"), item.get("size_bytes"))
        if (
            not _matches(item.get("artifact_id"), ARTIFACT_ID)
            or not _matches(item.get("namespace"), CONTRACT_ID)
            or item.get("kind") not in {"image", "mask", "file"}
            or item.get("state") not in {"reserved", "ready"}
            or not _timestamp(item.get("created_at"))
            or ready != _timestamp(item.get("ready_at"))
            or ready != all(value is not None for value in content)
            or (item.get("width") is None) != (item.get("height") is None)
        ):
            raise ApiError("image API returned inconsistent Artifact collection")
        if ready and (
            not _matches(item.get("sha256"), SHA256)
            or not _matches(item.get("mime_type"), MIME_TYPE)
            or not _positive_int(item.get("size_bytes"))
            or (
                item.get("width") is not None
                and (not _positive_int(item.get("width")) or not _positive_int(item.get("height")))
            )
        ):
            raise ApiError("image API returned malformed Artifact collection")


def _validate_prompt_plan(data: dict[str, Any], seed: int) -> None:
    if set(data) != {
        "profile",
        "optimizer_version",
        "intent",
        "prompt",
        "negative_prompt",
        "width",
        "height",
        "cache_hit",
        "seed",
    }:
        raise ApiError("image API returned malformed prompt plan")
    if (
        data.get("profile") != "generation-standard"
        or not isinstance(data.get("optimizer_version"), str)
        or not data["optimizer_version"]
        or not _valid_image_intent(data.get("intent"))
        or not isinstance(data.get("prompt"), str)
        or not data["prompt"]
        or (
            data.get("negative_prompt") is not None and not isinstance(data["negative_prompt"], str)
        )
        or not _positive_int(data.get("width"))
        or not _positive_int(data.get("height"))
        or not isinstance(data.get("cache_hit"), bool)
        or data.get("seed") != seed
    ):
        raise ApiError("image API returned malformed prompt plan")


def _validate_generation_completed(data: dict[str, Any], seed: int) -> dict[str, Any]:
    if set(data) != {"job_id", "status", "result", "prompt_plan", "seed"}:
        raise ApiError("image API returned malformed generation completion")
    metadata = data.get("result")
    if (
        not _matches(data.get("job_id"), JOB_ID)
        or data.get("status") != "completed"
        or not isinstance(metadata, dict)
        or data.get("seed") != seed
        or (data.get("prompt_plan") is not None and not isinstance(data["prompt_plan"], dict))
    ):
        raise ApiError("image API returned malformed generation completion")
    _validate_artifact_metadata(metadata)
    return metadata


def _validate_accepted_generation(
    response: httpx.Response, data: dict[str, Any], api_base_url: str
) -> str:
    if set(data) != {
        "job_id",
        "status",
        "status_url",
        "cancel_url",
        "submitted_at",
        "execution",
    }:
        raise ApiError("image API returned malformed accepted generation")
    execution = data.get("execution")
    status_url = data.get("status_url")
    cancel_url = data.get("cancel_url")
    if (
        not _matches(data.get("job_id"), JOB_ID)
        or data.get("status") not in {"accepted", "queued", "running"}
        or not isinstance(status_url, str)
        or not isinstance(cancel_url, str)
        or not _timestamp(data.get("submitted_at"))
        or not isinstance(execution, dict)
        or set(execution) != {"wait_seconds", "allow_long_wait", "accept_async"}
        or not isinstance(execution.get("wait_seconds"), int)
        or isinstance(execution.get("wait_seconds"), bool)
        or not isinstance(execution.get("allow_long_wait"), bool)
        or not isinstance(execution.get("accept_async"), bool)
    ):
        raise ApiError("image API returned malformed accepted generation")
    parsed_status = urlsplit(status_url)
    parsed_cancel = urlsplit(cancel_url)
    parsed_base = urlsplit(api_base_url)
    job_id = str(data["job_id"])
    if (
        parsed_status.scheme != "https"
        or parsed_cancel.scheme != "https"
        or parsed_status.netloc != parsed_base.netloc
        or parsed_cancel.netloc != parsed_base.netloc
        or parsed_status.path != f"/v4/jobs/{job_id}"
        or parsed_cancel.path != f"/v4/jobs/{job_id}/cancel"
        or parsed_status.query
        or parsed_cancel.query
        or response.headers.get("location") != status_url
        or not response.headers.get("retry-after", "").isdigit()
    ):
        raise ApiError("image API returned unsafe generation lifecycle links")
    return job_id


def _job_seed(job: dict[str, Any]) -> int:
    seeds = [
        values["seed"]
        for step in job["steps"]
        if isinstance(step, dict)
        and isinstance((values := step.get("value_outputs")), dict)
        and isinstance(values.get("seed"), int)
        and not isinstance(values["seed"], bool)
    ]
    if len(seeds) != 1:
        raise ApiError("image API returned a malformed generation seed receipt")
    return cast(int, seeds[0])


def _valid_image_intent(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "subject",
        "environment",
        "composition",
        "style",
        "lighting",
        "text_requirements",
        "preservation_constraints",
        "exclusions",
    }:
        return False
    optional_strings = (
        "environment",
        "composition",
        "style",
        "lighting",
        "text_requirements",
    )
    return (
        isinstance(value.get("subject"), str)
        and all(
            value.get(name) is None or isinstance(value[name], str) for name in optional_strings
        )
        and all(
            isinstance(value.get(name), list) and all(isinstance(item, str) for item in value[name])
            for name in ("preservation_constraints", "exclusions")
        )
    )


def _validate_artifact_access(data: dict[str, Any]) -> None:
    if set(data) != {"artifact", "url", "expires_at"} or not isinstance(data.get("artifact"), dict):
        raise ApiError("image API returned malformed Artifact access")
    _validate_artifact_descriptor(data["artifact"])
    if (
        not isinstance(data.get("url"), str)
        or urlsplit(data["url"]).scheme != "https"
        or not _timestamp(data.get("expires_at"))
    ):
        raise ApiError("image API returned malformed Artifact access")


def _validate_search_response(data: dict[str, Any]) -> None:
    if set(data) != {"embedding_profile", "model", "model_revision", "dimension", "results"}:
        raise ApiError("image API returned malformed search results")
    if (
        not isinstance(data.get("embedding_profile"), str)
        or not isinstance(data.get("model"), str)
        or not isinstance(data.get("model_revision"), str)
        or not _positive_int(data.get("dimension"))
        or not isinstance(data.get("results"), list)
    ):
        raise ApiError("image API returned malformed search results")
    for result in data["results"]:
        if not isinstance(result, dict) or set(result) != {
            "artifact",
            "namespace",
            "score",
            "created_at",
            "indexed_at",
        }:
            raise ApiError("image API returned malformed search result")
        artifact = result.get("artifact")
        score = result.get("score")
        if (
            not isinstance(artifact, dict)
            or not _matches(result.get("namespace"), CONTRACT_ID)
            or not isinstance(score, int | float)
            or isinstance(score, bool)
            or not -1.0 <= score <= 1.0
            or not _timestamp(result.get("created_at"))
            or not _timestamp(result.get("indexed_at"))
        ):
            raise ApiError("image API returned malformed search result")
        _validate_artifact_descriptor(artifact)


def _validate_caption(data: dict[str, Any]) -> None:
    if set(data) != {
        "caption",
        "model",
        "image",
        "cold_start",
        "model_load_seconds",
        "inference_seconds",
        "measured_compute_cost_usd",
    }:
        raise ApiError("image API returned malformed caption result")
    image = data.get("image")
    if (
        not isinstance(data.get("caption"), str)
        or not data["caption"]
        or not isinstance(data.get("model"), str)
        or not data["model"]
        or not isinstance(image, dict)
        or set(image) != {"sha256", "width", "height"}
        or not _matches(image.get("sha256"), SHA256)
        or not _positive_int(image.get("width"))
        or not _positive_int(image.get("height"))
        or not isinstance(data.get("cold_start"), bool)
        or not all(
            _nonnegative_decimal(data.get(name))
            for name in (
                "model_load_seconds",
                "inference_seconds",
                "measured_compute_cost_usd",
            )
        )
    ):
        raise ApiError("image API returned malformed caption result")


def _validate_batch_plan(data: dict[str, Any], seed: int, candidate_count: int) -> None:
    if set(data) != {
        "plan_id",
        "created_at",
        "profile",
        "model_revision",
        "width",
        "height",
        "root_seed",
        "items",
        "estimated_cost_usd",
    }:
        raise ApiError("image API returned malformed BatchPlan")
    items = data.get("items")
    identity_valid = isinstance(data.get("plan_id"), str) and bool(data["plan_id"])
    dimensions_valid = _positive_int(data.get("width")) and _positive_int(data.get("height"))
    model_valid = data.get("profile") == "generation-standard" and isinstance(
        data.get("model_revision"), str
    )
    if not (
        identity_valid
        and _timestamp(data.get("created_at"))
        and model_valid
        and dimensions_valid
        and data.get("root_seed") == seed
        and isinstance(items, list)
        and len(items) == candidate_count
        and _nonnegative_decimal(data.get("estimated_cost_usd"))
    ):
        raise ApiError("image API returned malformed BatchPlan")
    for index, item in enumerate(items):
        if not _valid_batch_plan_item(item, index):
            raise ApiError("image API returned malformed BatchPlan item")


def _valid_batch_plan_item(item: object, index: int) -> bool:
    if not isinstance(item, dict) or set(item) != {"index", "prompt", "seed"}:
        return False
    prompt = item.get("prompt")
    seed = item.get("seed")
    return (
        item.get("index") == index
        and isinstance(prompt, str)
        and bool(prompt)
        and isinstance(seed, int)
        and not isinstance(seed, bool)
        and 0 <= seed <= 2**63 - 1
    )


def _validate_artifact_descriptor(data: dict[str, Any]) -> None:
    if set(data) != {
        "artifact_id",
        "kind",
        "sha256",
        "mime_type",
        "size_bytes",
        "width",
        "height",
    }:
        raise ApiError("image API returned malformed Artifact descriptor")
    width = data.get("width")
    height = data.get("height")
    if (
        not _matches(data.get("artifact_id"), ARTIFACT_ID)
        or data.get("kind") not in {"image", "mask", "file"}
        or not _matches(data.get("sha256"), SHA256)
        or not _matches(data.get("mime_type"), MIME_TYPE)
        or not _positive_int(data.get("size_bytes"))
        or (width is None) != (height is None)
        or (width is not None and not _positive_int(width))
        or (height is not None and not _positive_int(height))
        or (data.get("kind") in {"image", "mask"} and width is None)
    ):
        raise ApiError("image API returned malformed Artifact descriptor")


def _validate_upload_reservation(
    data: dict[str, Any],
) -> tuple[str, str, dict[str, str]]:
    upload = data.get("upload")
    if (
        set(data) != {"artifact_id", "state", "upload"}
        or not _matches(data.get("artifact_id"), ARTIFACT_ID)
        or data.get("state") != "reserved"
        or not isinstance(upload, dict)
        or set(upload) != {"method", "url", "headers", "expires_at"}
        or upload.get("method") != "PUT"
        or not isinstance(upload.get("url"), str)
        or urlsplit(upload["url"]).scheme != "https"
        or not _timestamp(upload.get("expires_at"))
    ):
        raise ApiError("image API returned malformed upload instructions")
    headers = upload.get("headers")
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
    ):
        raise ApiError("image API returned malformed upload instructions")
    return str(data["artifact_id"]), str(upload["url"]), cast(dict[str, str], headers)


def _matches(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _operation_list(value: object) -> bool:
    return isinstance(value, list) and all(item in OPERATIONS for item in value)


def _nonnegative_decimal(value: object) -> bool:
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return False
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return parsed.is_finite() and parsed >= 0


def _timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None
