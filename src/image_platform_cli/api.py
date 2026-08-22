import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from PIL import Image, UnidentifiedImageError

from .errors import ApiError
from .models import DeterministicEditResult, GeneratedImage, SegmentationResult

TERMINAL_FAILURES = frozenset({"failed", "partial", "cancelled"})
TERMINAL_CAMPAIGN_STATUSES = frozenset({"completed", "partial", "failed", "cancelled"})
MAX_PAGE_SIZE = 100
MAX_ARTIFACT_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_EDIT_IMAGE_BYTES = 10 * 1024 * 1024
MAX_EDIT_PIXELS = 4_194_304
MAX_STABILITY_SEED = 4_294_967_294
INPAINT_PROFILE = "inpaint-stable-diffusion-v1-5"
INPAINT_MODEL = "stable-diffusion-v1-5/stable-diffusion-inpainting"
INPAINT_MODEL_REVISION = "8a4288a76071f7280aedbdb3253bdb9e9d5d84bb"
_SENSITIVE_RESPONSE_KEYS = frozenset(
    {"url", "signed_url", "object_key", "staging_key", "query", "upload"}
)
QueryValue = str | int | float | bool | None
EDIT_CAPABILITY_ROUTES = (
    ("image_to_image", "edit", "/v1/image-to-image"),
    ("segmentation", "segment", "/v1/segmentations"),
    ("image_operations", "image_ops", "/v1/image-operations"),
    ("inpaint", "inpaint", "/v1/images/edits"),
)


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

    def capabilities(self, access_token: str) -> dict[str, Any]:
        body = self._request_json("GET", "/v1/capabilities", access_token)
        raw_states = body.get("operation_states")
        if not isinstance(raw_states, list):
            raise ApiError("image API returned malformed capabilities")
        states: dict[str, dict[str, Any]] = {}
        for raw_state in raw_states:
            state = _required_dict(raw_state)
            operation = _required_string(state, "operation")
            if operation in states:
                raise ApiError("image API returned duplicate capability state")
            states[operation] = state

        capabilities: list[dict[str, object]] = []
        for name, operation, endpoint in EDIT_CAPABILITY_ROUTES:
            selected_state = states.get(operation)
            if selected_state is None:
                raise ApiError("image API omitted an editing capability")
            reason = selected_state.get("reason")
            if reason is not None and not isinstance(reason, str):
                raise ApiError("image API returned malformed capabilities")
            declared = _required_bool(selected_state, "declared")
            configured = _required_bool(selected_state, "configured")
            authorized = _required_bool(selected_state, "authorized")
            if not declared or ((not configured or not authorized) and reason is None):
                raise ApiError("image API returned inconsistent capabilities")
            if configured and authorized and reason is not None:
                raise ApiError("image API returned inconsistent capabilities")
            capabilities.append(
                {
                    "name": name,
                    "operation": operation,
                    "endpoint": endpoint,
                    "declared": declared,
                    "configured": configured,
                    "authorized": authorized,
                    "reason": reason,
                }
            )
        return {
            "service": _required_string(body, "service"),
            "status": _required_string(body, "status"),
            "capabilities": capabilities,
        }

    def image_to_image(
        self,
        access_token: str,
        *,
        prompt: str,
        input_path: Path | None = None,
        artifact_id: str | None = None,
        profile: str,
        negative_prompt: str | None,
        strength: Decimal,
        guidance_scale: Decimal,
        inference_steps: int,
        seed: int | None,
        width: int | None,
        height: int | None,
    ) -> GeneratedImage:
        if (input_path is None) == (artifact_id is None):
            raise ApiError("exactly one image-to-image input or Artifact is required")
        effective_seed = _resolve_seed(seed)
        _validate_image_to_image_controls(
            prompt,
            negative_prompt,
            strength,
            guidance_scale,
            inference_steps,
            effective_seed,
            width,
            height,
        )
        payload: dict[str, object] = {
            "profile": profile,
            "prompt": prompt,
            "strength": str(strength),
            "guidance_scale": str(guidance_scale),
            "inference_steps": inference_steps,
            "seed": effective_seed,
        }
        if input_path is not None:
            source, mime_type, _, _ = _read_edit_input(input_path)
            payload["input"] = {
                "mime_type": mime_type,
                "data_base64": base64.b64encode(source).decode("ascii"),
            }
        else:
            if artifact_id is None:
                raise AssertionError("validated image-to-image input is missing")
            payload["artifact_id"] = _resource_id(artifact_id)
        if negative_prompt is not None:
            payload["negative_prompt"] = negative_prompt
        if width is not None and height is not None:
            payload["width"] = width
            payload["height"] = height
        body = self._request_json("POST", "/v1/image-to-image", access_token, json=payload)
        output = _required_dict(body.get("output"))
        metadata = _required_dict(output.get("image"))
        encoded = _required_string(output, "data_base64")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ApiError("image API returned invalid image Base64") from error
        image = _verified_generated_image(data, metadata, effective_seed)
        receipt = _required_dict(body.get("receipt"))
        controls = _required_dict(receipt.get("controls"))
        model_id = _required_string(receipt, "model_id")
        model_revision = _required_string(receipt, "model_revision")
        measured_compute_cost_usd = _required_decimal(receipt, "measured_compute_cost_usd")
        if (
            _required_string(receipt, "profile") != profile
            or _required_int(receipt, "seed") != effective_seed
            or _required_decimal(controls, "strength") != strength
            or _required_decimal(controls, "guidance_scale") != guidance_scale
            or _required_int(controls, "inference_steps") != inference_steps
            or _required_bool(controls, "negative_prompt_applied") != (negative_prompt is not None)
            or _required_int(controls, "width") != image.width
            or _required_int(controls, "height") != image.height
        ):
            raise ApiError("image API returned inconsistent image-to-image receipt")
        return GeneratedImage(
            image.data,
            image.mime_type,
            image.sha256,
            image.width,
            image.height,
            image.seed,
            measured_compute_cost_usd,
            model_id,
            model_revision,
        )

    def caption(
        self,
        access_token: str,
        *,
        input_path: Path | None = None,
        artifact_id: str | None = None,
        instruction: str = "Describe this image concisely.",
        max_output_tokens: int = 128,
    ) -> dict[str, Any]:
        if (input_path is None) == (artifact_id is None):
            raise ApiError("exactly one caption input or Artifact is required")
        if not instruction.strip() or len(instruction) > 2048:
            raise ApiError("caption instruction must contain 1 to 2048 characters")
        if not 1 <= max_output_tokens <= 512:
            raise ApiError("max output tokens must be from 1 through 512")
        payload: dict[str, object] = {
            "instruction": instruction,
            "max_output_tokens": max_output_tokens,
        }
        if input_path is not None:
            source, mime_type, _, _ = _read_edit_input(input_path)
            payload["input"] = {
                "mime_type": mime_type,
                "data_base64": base64.b64encode(source).decode("ascii"),
            }
        else:
            if artifact_id is None:
                raise AssertionError("validated caption input is missing")
            payload["artifact_id"] = _resource_id(artifact_id)
        return self._safe_json("POST", "/v1/captions", access_token, json=payload)

    def segment(
        self,
        access_token: str,
        *,
        input_path: Path,
        text: str | None,
        points: Sequence[tuple[int, int, bool]],
        box: tuple[int, int, int, int] | None,
    ) -> SegmentationResult:
        source, mime_type, source_width, source_height = _read_edit_input(input_path)
        _validate_segment_selector(text, points, box, source_width, source_height)
        payload: dict[str, object] = {
            "input": {
                "mime_type": mime_type,
                "data_base64": base64.b64encode(source).decode("ascii"),
            }
        }
        if text is not None:
            payload["text"] = text
        if points:
            payload["points"] = [
                {"x": x, "y": y, "positive": positive} for x, y, positive in points
            ]
        if box is not None:
            payload["box"] = dict(zip(("x_min", "y_min", "x_max", "y_max"), box, strict=True))
        body = self._request_json("POST", "/v1/segmentations", access_token, json=payload)
        output = _required_dict(body.get("output"))
        metadata = _required_dict(output.get("image"))
        try:
            mask = base64.b64decode(_required_string(output, "data_base64"), validate=True)
        except (ValueError, binascii.Error) as error:
            raise ApiError("image API returned invalid mask Base64") from error
        digest, width, height = _verified_png(mask, metadata)
        receipt = _required_dict(body.get("receipt"))
        input_receipt = _required_dict(receipt.get("input_image"))
        mask_receipt = _required_dict(receipt.get("mask_image"))
        if (
            _required_string(receipt, "profile") != "segment-grounding-dino-sam2-tiny"
            or _required_string(input_receipt, "sha256") != hashlib.sha256(source).hexdigest()
            or _required_int(input_receipt, "width") != source_width
            or _required_int(input_receipt, "height") != source_height
            or _required_string(mask_receipt, "sha256") != digest
            or _required_int(mask_receipt, "width") != width
            or _required_int(mask_receipt, "height") != height
            or (width, height) != (source_width, source_height)
        ):
            raise ApiError("image API returned inconsistent segmentation receipt")
        return SegmentationResult(source, mask, digest, width, height)

    def composite(
        self,
        access_token: str,
        *,
        background_path: Path,
        overlay_path: Path,
        mask_path: Path | None,
        transform: tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal],
        opacity: Decimal,
        composite: str,
        crop: tuple[int, int, int, int] | None,
    ) -> DeterministicEditResult:
        background, background_mime, _, _ = _read_edit_input(background_path)
        overlay, overlay_mime, _, _ = _read_edit_input(overlay_path)
        mask_input = _read_edit_input(mask_path) if mask_path is not None else None
        _validate_composite_controls(transform, opacity, crop)
        if composite not in {"source_over", "replace", "multiply", "screen"}:
            raise ApiError("unsupported composite mode")
        inputs: dict[str, object] = {
            "background": _inline_image(background, background_mime),
            "overlay": _inline_image(overlay, overlay_mime),
        }
        input_kinds = {"background": "image", "overlay": "image"}
        input_hashes = {
            "background": hashlib.sha256(background).hexdigest(),
            "overlay": hashlib.sha256(overlay).hexdigest(),
        }
        coverage: dict[str, object] | None = None
        if mask_input is not None:
            mask, mask_mime, _, _ = mask_input
            inputs["mask"] = _inline_image(mask, mask_mime)
            input_kinds["mask"] = "mask"
            input_hashes["mask"] = hashlib.sha256(mask).hexdigest()
            coverage = {"base": {"source": {"kind": "mask_input", "input": "mask"}}}
        commands: list[dict[str, object]] = [
            {
                "id": "place-overlay",
                "op": "paste_image",
                "input": "overlay",
                "transform": dict(
                    zip(("a", "b", "c", "d", "e", "f"), map(str, transform), strict=True)
                ),
                "opacity": str(opacity),
                "composite": composite,
                **({"coverage": coverage} if coverage is not None else {}),
            }
        ]
        if crop is not None:
            x, y, width, height = crop
            commands.append(
                {
                    "id": "crop-result",
                    "op": "crop",
                    "rect": {"x": x, "y": y, "width": width, "height": height},
                }
            )
        body = self._request_json(
            "POST",
            "/v1/image-operations",
            access_token,
            json={
                "inputs": inputs,
                "program": {
                    "revision": "deterministic-edit-v1",
                    "inputs": input_kinds,
                    "source_input": "background",
                    "commands": commands,
                    "encoding": {"format": "png"},
                },
                "response_format": "base64",
            },
        )
        metadata = _required_dict(body.get("image"))
        try:
            data = base64.b64decode(_required_string(body, "data_base64"), validate=True)
        except (ValueError, binascii.Error) as error:
            raise ApiError("image API returned invalid composite Base64") from error
        mime_type = _required_string(metadata, "mime_type")
        _verify_artifact(data, mime_type, metadata)
        digest = hashlib.sha256(data).hexdigest()
        width = _required_int(metadata, "width")
        height = _required_int(metadata, "height")
        receipt = _required_dict(body.get("receipt"))
        receipt_inputs = _required_dict(receipt.get("input_sha256s"))
        receipt_commands = receipt.get("commands")
        expected_commands = [(command["id"], command["op"]) for command in commands]
        if not isinstance(receipt_commands, list):
            raise ApiError("image API returned malformed composite receipt")
        actual_commands = [
            (
                _required_string(_required_dict(item), "id"),
                _required_string(_required_dict(item), "op"),
            )
            for item in receipt_commands
        ]
        if (
            _required_string(receipt, "contract_revision") != "deterministic-edit-v1"
            or receipt_inputs != input_hashes
            or actual_commands != expected_commands
            or _required_string(receipt, "output_sha256") != digest
            or _required_int(receipt, "output_width") != width
            or _required_int(receipt, "output_height") != height
        ):
            raise ApiError("image API returned inconsistent composite receipt")
        return DeterministicEditResult(
            data,
            mime_type,
            digest,
            width,
            height,
            _required_string(receipt, "program_sha256"),
        )

    def load_deterministic_program(
        self,
        program_path: Path,
        *,
        input_bindings: Sequence[str],
        mask_bindings: Sequence[str],
    ) -> tuple[dict[str, Any], dict[str, Path], dict[str, Path]]:
        try:
            raw = json.loads(program_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ApiError("program must be a readable UTF-8 JSON file") from error
        program = _validate_deterministic_program(raw)
        inputs = _parse_named_paths(input_bindings, kind="input")
        masks = _parse_named_paths(mask_bindings, kind="mask")
        if set(inputs) & set(masks):
            raise ApiError("input and mask binding names must be distinct")
        declared = _required_dict(program.get("inputs"))
        actual_kinds = {**{name: "image" for name in inputs}, **{name: "mask" for name in masks}}
        if declared != actual_kinds:
            raise ApiError("named bindings must exactly match program inputs and kinds")
        return program, inputs, masks

    def run_deterministic_program(
        self,
        access_token: str,
        *,
        program: dict[str, Any],
        input_paths: Mapping[str, Path],
        mask_paths: Mapping[str, Path],
    ) -> DeterministicEditResult:
        inline_inputs: dict[str, object] = {}
        input_hashes: dict[str, str] = {}
        for name, path in sorted({**input_paths, **mask_paths}.items()):
            data, mime, _, _ = _read_edit_input(path)
            inline_inputs[name] = _inline_image(data, mime)
            input_hashes[name] = hashlib.sha256(data).hexdigest()
        body = self._request_json(
            "POST",
            "/v1/image-operations",
            access_token,
            json={"inputs": inline_inputs, "program": program, "response_format": "base64"},
        )
        metadata = _required_dict(body.get("image"))
        try:
            data = base64.b64decode(_required_string(body, "data_base64"), validate=True)
        except (ValueError, binascii.Error) as error:
            raise ApiError("image API returned invalid deterministic-edit Base64") from error
        mime_type = _required_string(metadata, "mime_type")
        _verify_artifact(data, mime_type, metadata)
        digest = hashlib.sha256(data).hexdigest()
        width = _required_int(metadata, "width")
        height = _required_int(metadata, "height")
        receipt = _required_dict(body.get("receipt"))
        raw_receipts = receipt.get("commands")
        if not isinstance(raw_receipts, list):
            raise ApiError("image API returned malformed deterministic-edit receipt")
        command_receipts = tuple(
            (
                _required_string(item := _required_dict(raw), "id"),
                _required_string(item, "op"),
                _required_string(item, "normalized_command_sha256"),
                _required_string(item, "output_pixel_sha256"),
            )
            for raw in raw_receipts
        )
        expected_commands = tuple(
            (_required_string(command, "id"), _required_string(command, "op"))
            for raw in _required_list(program.get("commands"))
            for command in (_required_dict(raw),)
        )
        if (
            _required_string(receipt, "contract_revision") != "deterministic-edit-v1"
            or _required_dict(receipt.get("input_sha256s")) != input_hashes
            or tuple((item[0], item[1]) for item in command_receipts) != expected_commands
            or _required_string(receipt, "output_sha256") != digest
            or _required_int(receipt, "output_width") != width
            or _required_int(receipt, "output_height") != height
        ):
            raise ApiError("image API returned inconsistent deterministic-edit receipt")
        return DeterministicEditResult(
            data,
            mime_type,
            digest,
            width,
            height,
            _required_string(receipt, "program_sha256"),
            command_receipts,
        )

    def inpaint(
        self,
        access_token: str,
        *,
        prompt: str,
        input_path: Path,
        mask_path: Path,
        profile: str,
        seed: int | None,
        safety_filter: str = "default",
    ) -> GeneratedImage:
        image, image_mime, width, height = _read_edit_input(input_path)
        mask, mask_mime, mask_width, mask_height = _read_edit_input(mask_path)
        if profile != INPAINT_PROFILE:
            raise ApiError("unknown inpaint profile")
        if safety_filter not in {"default", "enabled", "disabled"}:
            raise ApiError("safety_filter must be default, enabled, or disabled")
        if not prompt.strip() or len(prompt) > 2048:
            raise ApiError("prompt must contain 1 to 2048 non-whitespace characters")
        if (width, height) != (mask_width, mask_height):
            raise ApiError("inpaint image and mask dimensions must match")
        if len(image) + len(mask) > MAX_EDIT_IMAGE_BYTES:
            raise ApiError("combined inpaint image and mask must contain at most 10 MiB")
        if seed is None:
            effective_seed = secrets.randbelow(MAX_STABILITY_SEED) + 1
        elif isinstance(seed, bool) or seed < 0 or seed > MAX_STABILITY_SEED:
            raise ApiError(f"seed must be from 0 through {MAX_STABILITY_SEED}")
        else:
            effective_seed = seed
        try:
            response = self._http.post(
                f"{self._api_base_url}/v2beta/stable-image/edit/inpaint",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "image/*",
                },
                files={
                    "image": (input_path.name, image, image_mime),
                    "mask": (mask_path.name, mask, mask_mime),
                },
                data={
                    "prompt": prompt,
                    "grow_mask": "0",
                    "seed": str(effective_seed),
                    "output_format": "png",
                    "safety_filter": safety_filter,
                },
            )
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        returned_seed = _required_header_int(response, "Seed")
        if effective_seed != 0 and returned_seed != effective_seed:
            raise ApiError("image API returned an unexpected inpaint seed")
        digest = hashlib.sha256(response.content).hexdigest()
        try:
            output_width, output_height = _png_dimensions(response.content)
        except ApiError as error:
            raise ApiError("image API response integrity check failed") from error
        if (
            response.headers.get("Content-Type", "").split(";", 1)[0] != "image/png"
            or response.headers.get("X-Image-SHA256") != digest
            or response.headers.get("X-Image-Native-SHA256") != digest
            or response.headers.get("X-Image-Backend-Profile") != profile
            or response.headers.get("X-Image-Backend-Model") != INPAINT_MODEL
            or response.headers.get("X-Image-Backend-Revision") != INPAINT_MODEL_REVISION
            or _required_header_int(response, "X-Image-Width") != output_width
            or _required_header_int(response, "X-Image-Height") != output_height
            or (output_width, output_height) != (width, height)
        ):
            raise ApiError("image API response integrity check failed")
        measured_compute_cost_usd = _required_header_decimal(response, "X-Image-Compute-Cost-Usd")
        safety_filter_requested = _required_header(response, "X-Image-Safety-Filter-Requested")
        safety_filter_effective = _required_header(response, "X-Image-Safety-Filter-Effective")
        safety_filter_outcome = _required_header(response, "X-Image-Safety-Filter-Outcome")
        if (
            safety_filter_requested != safety_filter
            or safety_filter_effective not in {"enabled", "disabled"}
            or safety_filter_outcome
            != ("passed" if safety_filter_effective == "enabled" else "not_run")
        ):
            raise ApiError("image API returned inconsistent safety filter evidence")
        return GeneratedImage(
            response.content,
            "image/png",
            digest,
            output_width,
            output_height,
            returned_seed,
            measured_compute_cost_usd,
            INPAINT_MODEL,
            INPAINT_MODEL_REVISION,
            safety_filter_requested,
            safety_filter_effective,
            safety_filter_outcome,
        )

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

    def upload_artifact(
        self,
        access_token: str,
        input_path: Path,
        *,
        namespace: str = "default",
        kind: str = "image",
    ) -> dict[str, Any]:
        data, mime_type, width, height = _read_edit_input(input_path)
        reserved = self._request_json(
            "POST",
            "/v1/uploads",
            access_token,
            json={"namespace": namespace, "kind": kind, "mime_type": mime_type},
        )
        artifact_id = _required_string(reserved, "artifact_id")
        upload = _required_dict(reserved.get("upload"))
        if _required_string(upload, "method") != "PUT":
            raise ApiError("image API returned unsupported upload instructions")
        upload_url = _required_string(upload, "url")
        if urlsplit(upload_url).scheme != "https":
            raise ApiError("image API returned an unsafe Artifact upload URL")
        raw_headers = _required_dict(upload.get("headers"))
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in raw_headers.items()
        ):
            raise ApiError("image API returned malformed upload headers")
        try:
            response = self._http.put(
                upload_url, content=data, headers=cast(dict[str, str], raw_headers)
            )
        except httpx.HTTPError as error:
            raise ApiError("Artifact upload failed") from error
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        digest = hashlib.sha256(data).hexdigest()
        completed = self._request_json(
            "POST",
            f"/v1/uploads/{_resource_id(artifact_id)}/complete",
            access_token,
            json={
                "sha256": digest,
                "mime_type": mime_type,
                "size_bytes": len(data),
                "width": width,
                "height": height,
            },
        )
        if _required_string(completed, "artifact_id") != artifact_id:
            raise ApiError("image API returned an inconsistent Artifact ID")
        result = _required_dict(completed.get("result"))
        metadata = _required_dict(result.get("artifact"))
        _verify_artifact(data, mime_type, metadata)
        return cast(dict[str, Any], _safe_projection(completed))

    def download_artifact(
        self, access_token: str, artifact_id: str, output: Path
    ) -> dict[str, Any]:
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
        query: str | None = None,
        image_path: Path | None = None,
        artifact_id: str | None = None,
        namespace: str = "default",
        mime_types: Sequence[str] = (),
        created_after: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if sum(value is not None for value in (query, image_path, artifact_id)) != 1:
            raise ApiError("exactly one search query, --image, or --artifact is required")
        if query is not None and (not query.strip() or len(query) > 2048):
            raise ApiError("search query must contain 1 to 2048 non-whitespace characters")
        if limit < 1 or limit > 100:
            raise ApiError("limit must be from 1 through 100")
        filters: dict[str, object] = {"mime_type": list(mime_types)}
        if created_after is not None:
            filters["created_after"] = created_after
        payload: dict[str, object] = {
            "namespace": namespace,
            "filters": filters,
            "limit": limit,
        }
        if query is not None:
            payload["query"] = query
        elif image_path is not None:
            data, mime_type, _, _ = _read_edit_input(image_path)
            payload["image"] = {
                "mime_type": mime_type,
                "data_base64": base64.b64encode(data).decode("ascii"),
            }
        else:
            if artifact_id is None:
                raise AssertionError("validated search requires one query source")
            payload["artifact_id"] = _resource_id(artifact_id)
        return self._safe_json(
            "POST",
            "/v1/search",
            access_token,
            json=payload,
        )

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
        seed = _resolve_seed(root_seed)
        self._validate_batch_plan(intent, width, height, candidate_count, seed)
        body = self._request_json(
            "POST",
            "/v1/batch-plans",
            access_token,
            headers={"Idempotency-Key": str(uuid4())},
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
        return _batch_plan_projection(body, expected_seed=seed, expected_count=candidate_count)

    def create_campaign(
        self,
        access_token: str,
        *,
        plan_id: str,
        max_cost_usd: Decimal | str,
        allow_partial: bool = False,
        wait_seconds: int = 0,
        allow_long_wait: bool = False,
    ) -> dict[str, Any]:
        maximum = _positive_decimal(max_cost_usd, "max-cost")
        _validate_wait(wait_seconds, allow_long_wait)
        campaign = self._safe_json(
            "POST",
            "/v1/campaigns",
            access_token,
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "plan_id": _resource_id(plan_id),
                "max_cost_usd": str(maximum),
                "allow_partial": allow_partial,
            },
        )
        campaign_id = _required_string(campaign, "campaign_id")
        if wait_seconds == 0 or _required_string(campaign, "status") in TERMINAL_CAMPAIGN_STATUSES:
            return campaign
        deadline = self._clock() + wait_seconds
        while self._clock() < deadline:
            self._sleep(min(1.0, max(0.0, deadline - self._clock())))
            campaign = self.get_campaign(access_token, campaign_id)
            if _required_string(campaign, "status") in TERMINAL_CAMPAIGN_STATUSES:
                break
        return campaign

    def create_iterative_campaign(
        self,
        access_token: str,
        *,
        plan_id: str,
        max_cost_usd: Decimal | str,
        score_threshold: Decimal | str = Decimal("0.8"),
        max_rounds: int = 3,
        allow_partial: bool = False,
        wait_seconds: int = 0,
        allow_long_wait: bool = False,
    ) -> dict[str, Any]:
        maximum = _positive_decimal(max_cost_usd, "max-cost")
        threshold = _bounded_score(score_threshold)
        if isinstance(max_rounds, bool) or not 1 <= max_rounds <= 3:
            raise ApiError("max-rounds must be from 1 through 3")
        _validate_wait(wait_seconds, allow_long_wait)
        safe_plan_id = _resource_id(plan_id)
        plan = self._request_json("GET", f"/v1/batch-plans/{safe_plan_id}", access_token)
        items = plan.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 4:
            raise ApiError("iterative Campaign requires a BatchPlan with 1 through 4 candidates")
        rubric = self._default_iteration_rubric(access_token)
        campaign = self._safe_json(
            "POST",
            "/v1/campaigns",
            access_token,
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "plan_id": safe_plan_id,
                "max_cost_usd": str(maximum),
                "allow_partial": allow_partial,
                "iteration_policy": {
                    **rubric,
                    "score_threshold": str(threshold),
                    "max_rounds": max_rounds,
                    "candidates_per_round": len(items),
                },
            },
        )
        campaign_id = _required_string(campaign, "campaign_id")
        if wait_seconds == 0 or _required_string(campaign, "status") in TERMINAL_CAMPAIGN_STATUSES:
            return campaign
        deadline = self._clock() + wait_seconds
        while self._clock() < deadline:
            self._sleep(min(1.0, max(0.0, deadline - self._clock())))
            campaign = self.get_campaign(access_token, campaign_id)
            if _required_string(campaign, "status") in TERMINAL_CAMPAIGN_STATUSES:
                break
        return campaign

    def campaign_evaluation(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        campaign = self.get_campaign(access_token, campaign_id)
        policy = _required_dict(campaign.get("iteration_policy"))
        rounds = campaign.get("rounds")
        if not isinstance(rounds, list):
            raise ApiError("image API returned a malformed iterative Campaign")
        evidence: list[dict[str, object]] = []
        for raw_round in rounds:
            round_ = _required_dict(raw_round)
            evaluation = round_.get("evaluation")
            if evaluation is None:
                evidence.append(
                    {"round_index": _required_int(round_, "round_index"), "pending": True}
                )
                continue
            evaluated = _required_dict(evaluation)
            candidates = evaluated.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ApiError("image API returned malformed evaluation evidence")
            evidence.append(
                {
                    "round_index": _required_int(evaluated, "round_index"),
                    "candidates": [
                        {
                            "artifact_id": _required_string(_required_dict(item), "artifact_id"),
                            "score": _required_string(_required_dict(item), "score"),
                            "reason": _required_string(_required_dict(item), "reason"),
                        }
                        for item in candidates
                    ],
                }
            )
        return {
            "campaign_id": _required_string(campaign, "campaign_id"),
            "status": _required_string(campaign, "status"),
            "actual_cost_usd": _required_string(campaign, "actual_cost_usd"),
            "max_cost_usd": _required_string(campaign, "max_cost_usd"),
            "score_threshold": _required_string(policy, "score_threshold"),
            "stop_reason": campaign.get("stop_reason"),
            "rounds": evidence,
        }

    def _default_iteration_rubric(self, access_token: str) -> dict[str, str]:
        try:
            response = self._http.get(
                f"{self._api_base_url}/v1/iteration/rubrics",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as error:
            raise ApiError("image API request failed") from error
        if not response.is_success:
            raise ApiError(_safe_api_error(response))
        try:
            rubrics = response.json()
        except ValueError as error:
            raise ApiError("image API returned malformed iteration rubrics") from error
        if not isinstance(rubrics, list) or len(rubrics) != 1:
            raise ApiError("image API returned malformed iteration rubrics")
        rubric = _required_dict(rubrics[0])
        return {
            "rubric_id": _required_string(rubric, "rubric_id"),
            "rubric_revision": _required_string(rubric, "rubric_revision"),
            "evaluator_model_revision": _required_string(rubric, "evaluator_model_revision"),
        }

    def get_campaign(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        return self._safe_json("GET", f"/v1/campaigns/{_resource_id(campaign_id)}", access_token)

    def cancel_campaign(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        return self._safe_json(
            "POST", f"/v1/campaigns/{_resource_id(campaign_id)}/cancel", access_token
        )

    def campaign_results(self, access_token: str, campaign_id: str) -> dict[str, Any]:
        campaign = self.get_campaign(access_token, campaign_id)
        child_ids = campaign.get("child_job_ids")
        if not isinstance(child_ids, list) or not all(isinstance(item, str) for item in child_ids):
            raise ApiError("image API returned a malformed Campaign")
        jobs = [self.get_job(access_token, child_id) for child_id in child_ids]
        artifacts: list[dict[str, str]] = []
        for job in jobs:
            outputs = job.get("outputs", [])
            if not isinstance(outputs, list):
                raise ApiError("image API returned a malformed Campaign result")
            for output in outputs:
                artifact_id = _required_string(_required_dict(output), "artifact_id")
                artifacts.append(
                    {"job_id": _required_string(job, "job_id"), "artifact_id": artifact_id}
                )
        return {"campaign": campaign, "jobs": jobs, "artifacts": artifacts}

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
        headers: Mapping[str, str] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            _safe_projection(
                self._request_json(method, path, access_token, headers=headers, json=json)
            ),
        )

    def _request_json(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Sequence[tuple[str, str | int | float | bool | None]] = (),
        json: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(
                method,
                f"{self._api_base_url}{path}",
                headers={"Authorization": f"Bearer {access_token}", **(headers or {})},
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

    @staticmethod
    def _validate_batch_plan(
        intent: str, width: int, height: int, candidate_count: int, root_seed: int
    ) -> None:
        if not intent.strip() or len(intent) > 2048:
            raise ApiError("intent must contain 1 to 2048 non-whitespace characters")
        for name, value in (("width", width), ("height", height)):
            if value < 256 or value > 1024 or value % 64:
                raise ApiError(f"{name} must be a multiple of 64 from 256 through 1024")
        if isinstance(candidate_count, bool) or candidate_count < 1 or candidate_count > 16:
            raise ApiError("count must be from 1 through 16")
        if root_seed < 0 or root_seed > 2**63 - 1:
            raise ApiError("seed is outside the supported range")


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


def _read_edit_input(path: Path) -> tuple[bytes, str, int, int]:
    if not path.is_file():
        raise ApiError("input image does not exist or is not a regular file")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ApiError("input image could not be read") from error
    if not data or len(data) > MAX_EDIT_IMAGE_BYTES:
        raise ApiError("input image must contain at most 10 MiB")
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ApiError("input image is invalid") from error
    mime_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(
        image_format or ""
    )
    if mime_type is None:
        raise ApiError("input image must be PNG, JPEG, or WebP")
    if width <= 0 or height <= 0 or width * height > MAX_EDIT_PIXELS:
        raise ApiError("input image exceeds the supported pixel limit")
    return data, mime_type, width, height


def _validate_segment_selector(
    text: str | None,
    points: Sequence[tuple[int, int, bool]],
    box: tuple[int, int, int, int] | None,
    width: int,
    height: int,
) -> None:
    selector_count = int(text is not None) + int(bool(points)) + int(box is not None)
    if selector_count != 1:
        raise ApiError("exactly one of text, points, or box is required")
    if text is not None and (not text.strip() or len(text) > 2048):
        raise ApiError("text selector must contain 1 to 2048 non-whitespace characters")
    if len(points) > 32:
        raise ApiError("at most 32 segmentation points are supported")
    if any(x < 0 or y < 0 or x >= width or y >= height for x, y, _ in points):
        raise ApiError("segmentation point is outside input bounds")
    if box is not None:
        x_min, y_min, x_max, y_max = box
        if not (0 <= x_min < x_max <= width and 0 <= y_min < y_max <= height):
            raise ApiError("segmentation box is outside input bounds")


def _inline_image(data: bytes, mime_type: str) -> dict[str, str]:
    return {"mime_type": mime_type, "data_base64": base64.b64encode(data).decode("ascii")}


def _validate_composite_controls(
    transform: Sequence[Decimal], opacity: Decimal, crop: tuple[int, int, int, int] | None
) -> None:
    if len(transform) != 6 or any(
        not value.is_finite() or value < -65_536 or value > 65_536 for value in transform
    ):
        raise ApiError("matrix values must be finite decimals from -65536 through 65536")
    if not opacity.is_finite() or opacity < 0 or opacity > 1:
        raise ApiError("opacity must be from 0 through 1")
    if crop is not None:
        x, y, width, height = crop
        if any(value < -1_000_000 or value > 1_000_000 for value in (x, y)):
            raise ApiError("crop origin is outside the supported range")
        if width < 1 or height < 1 or width > 8_192 or height > 8_192:
            raise ApiError("crop dimensions must be from 1 through 8192")


def save_deterministic_edit(result: DeterministicEditResult, output: Path) -> None:
    require_available_output(output)
    _save_bytes_exclusive(result.data, output)


def _validate_image_to_image_controls(
    prompt: str,
    negative_prompt: str | None,
    strength: Decimal,
    guidance_scale: Decimal,
    inference_steps: int,
    seed: int,
    width: int | None,
    height: int | None,
) -> None:
    if not prompt.strip() or len(prompt) > 2048:
        raise ApiError("prompt must contain 1 to 2048 non-whitespace characters")
    if negative_prompt is not None and (not negative_prompt.strip() or len(negative_prompt) > 2048):
        raise ApiError("negative prompt must contain 1 to 2048 non-whitespace characters")
    if not strength.is_finite() or not Decimal("0.1") <= strength <= Decimal(1):
        raise ApiError("strength must be from 0.1 through 1")
    if not guidance_scale.is_finite() or not Decimal(1) <= guidance_scale <= Decimal(15):
        raise ApiError("guidance scale must be from 1 through 15")
    if negative_prompt is not None and guidance_scale <= 1:
        raise ApiError("negative prompt requires guidance scale greater than 1")
    if isinstance(inference_steps, bool) or not 10 <= inference_steps <= 50:
        raise ApiError("steps must be from 10 through 50")
    if seed < 0 or seed > 2**63 - 1:
        raise ApiError("seed is outside the supported range")
    if (width is None) != (height is None):
        raise ApiError("width and height must be supplied together")
    for name, value in (("width", width), ("height", height)):
        if value is not None and (value < 256 or value > 768 or value % 64):
            raise ApiError(f"{name} must be a multiple of 64 from 256 through 768")


def _verified_generated_image(data: bytes, metadata: dict[str, Any], seed: int) -> GeneratedImage:
    digest, width, height = _verified_png(data, metadata)
    return GeneratedImage(data, "image/png", digest, width, height, seed)


def _verified_png(data: bytes, metadata: dict[str, Any]) -> tuple[str, int, int]:
    mime_type = _required_string(metadata, "mime_type")
    sha256 = _required_string(metadata, "sha256")
    size_bytes = _required_int(metadata, "size_bytes")
    width = _required_int(metadata, "width")
    height = _required_int(metadata, "height")
    digest = hashlib.sha256(data).hexdigest()
    try:
        png_width, png_height = _png_dimensions(data)
    except ApiError as error:
        raise ApiError("image API response integrity check failed") from error
    if (
        not data
        or mime_type != "image/png"
        or size_bytes != len(data)
        or sha256 != digest
        or (width, height) != (png_width, png_height)
    ):
        raise ApiError("image API response integrity check failed")
    return digest, width, height


def save_segmentation_outputs(
    result: SegmentationResult,
    *,
    mask_output: Path | None,
    foreground_output: Path | None,
    background_output: Path | None,
) -> None:
    destinations = tuple(
        output
        for output in (mask_output, foreground_output, background_output)
        if output is not None
    )
    if not destinations:
        raise ApiError("at least one segmentation output is required")
    if len(set(destinations)) != len(destinations):
        raise ApiError("segmentation output paths must be distinct")
    for output in destinations:
        require_available_output(output)
    if mask_output is not None:
        _save_bytes_exclusive(result.mask_data, mask_output)
    if foreground_output is None and background_output is None:
        return
    try:
        with Image.open(BytesIO(result.source_data)) as source_image:
            source = source_image.convert("RGBA")
        with Image.open(BytesIO(result.mask_data)) as mask_image:
            mask = mask_image.convert("L")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ApiError("segmentation images could not be decoded") from error
    for rendered_output, alpha in (
        (foreground_output, mask),
        (background_output, mask.point(lambda value: 255 - value)),
    ):
        if rendered_output is None:
            continue
        rendered = source.copy()
        rendered.putalpha(alpha)
        buffer = BytesIO()
        rendered.save(buffer, format="PNG")
        _save_bytes_exclusive(buffer.getvalue(), rendered_output)


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
    actual_content_type = (
        response_content_type.split(";", 1)[0].strip() if response_content_type else None
    )
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


def _batch_plan_projection(
    body: dict[str, Any], *, expected_seed: int, expected_count: int
) -> dict[str, Any]:
    items = body.get("items")
    if not isinstance(items, list) or len(items) != expected_count:
        raise ApiError("image API returned a malformed BatchPlan")
    projected_items: list[dict[str, object]] = []
    for item in items:
        record = _required_dict(item)
        projected_items.append(
            {
                "index": _required_int(record, "index"),
                "prompt": _required_string(record, "prompt"),
                "seed": _required_int(record, "seed"),
            }
        )
    if _required_int(body, "root_seed") != expected_seed:
        raise ApiError("image API returned an unexpected root seed")
    return {
        "plan_id": _required_string(body, "plan_id"),
        "created_at": _required_string(body, "created_at"),
        "profile": _required_string(body, "profile"),
        "model_revision": _required_string(body, "model_revision"),
        "width": _required_int(body, "width"),
        "height": _required_int(body, "height"),
        "root_seed": expected_seed,
        "items": projected_items,
        "estimated_cost_usd": _required_string(body, "estimated_cost_usd"),
    }


def _positive_decimal(value: Decimal | str, name: str) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ApiError(f"{name} must be a positive decimal") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ApiError(f"{name} must be a positive decimal")
    return parsed


def _bounded_score(value: Decimal | str) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ApiError("threshold must be a decimal from 0 through 1") from error
    if not parsed.is_finite() or not Decimal(0) <= parsed <= Decimal(1):
        raise ApiError("threshold must be a decimal from 0 through 1")
    return parsed


def _validate_wait(wait_seconds: int, allow_long_wait: bool) -> None:
    if isinstance(wait_seconds, bool) or wait_seconds < 0 or wait_seconds > 120:
        raise ApiError("wait must be an integer from 0 through 120 seconds")
    if wait_seconds > 60 and not allow_long_wait:
        raise ApiError("wait above 60 seconds requires --allow-long-wait")


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


def _required_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ApiError("image API returned a malformed response")
    return value


def _parse_named_paths(bindings: Sequence[str], *, kind: str) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for binding in bindings:
        name, separator, raw_path = binding.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name) or not raw_path:
            raise ApiError(f"{kind} bindings must use NAME=PATH")
        if name in parsed:
            raise ApiError(f"duplicate {kind} binding: {name}")
        parsed[name] = Path(raw_path)
    return parsed


def _validate_deterministic_program(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError("program JSON must be an object")
    if value.get("revision") != "deterministic-edit-v1":
        raise ApiError("program revision must be deterministic-edit-v1")
    inputs = value.get("inputs")
    if (
        not isinstance(inputs, dict)
        or not inputs
        or len(inputs) > 16
        or any(
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name)
            or kind not in {"image", "mask"}
            for name, kind in inputs.items()
        )
    ):
        raise ApiError("program inputs must declare 1 to 16 named image or mask inputs")
    if value.get("source_input") not in inputs or inputs[value["source_input"]] != "image":
        raise ApiError("program source_input must name an image input")
    commands = value.get("commands")
    if not isinstance(commands, list) or not 1 <= len(commands) <= 64:
        raise ApiError("program commands must contain 1 to 64 commands")
    identities: list[str] = []
    for command in commands:
        if not isinstance(command, dict):
            raise ApiError("each program command must be an object")
        command_id = command.get("id")
        operation = command.get("op")
        if (
            not isinstance(command_id, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", command_id)
            or not isinstance(operation, str)
            or not operation
        ):
            raise ApiError("each program command requires valid id and op strings")
        identities.append(command_id)
    if len(set(identities)) != len(identities):
        raise ApiError("program command ids must be unique")
    encoding = value.get("encoding")
    if not isinstance(encoding, dict) or encoding.get("format") not in {"png", "jpeg", "webp"}:
        raise ApiError("program encoding format must be png, jpeg, or webp")
    quality = encoding.get("quality", 90)
    if not isinstance(quality, int) or isinstance(quality, bool) or not 1 <= quality <= 100:
        raise ApiError("program encoding quality must be from 1 through 100")
    if encoding.get("format") == "png" and quality != 90:
        raise ApiError("program encoding quality is not configurable for PNG")
    return value


def _required_string(body: dict[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value:
        raise ApiError("image API returned a malformed response")
    return value


def _required_bool(body: dict[str, Any], name: str) -> bool:
    value = body.get(name)
    if not isinstance(value, bool):
        raise ApiError(f"image API response is missing {name}")
    return value


def _required_int(body: dict[str, Any], name: str) -> int:
    value = body.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError("image API returned a malformed response")
    return value


def _required_decimal(body: dict[str, Any], name: str) -> Decimal:
    value = body.get(name)
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ApiError("image API returned a malformed response")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ApiError("image API returned a malformed response") from error
    if not parsed.is_finite():
        raise ApiError("image API returned a malformed response")
    return parsed


def _required_header_int(response: httpx.Response, name: str) -> int:
    value = response.headers.get(name)
    try:
        parsed = int(value) if value is not None else -1
    except ValueError as error:
        raise ApiError("image API returned malformed image headers") from error
    if parsed < 0:
        raise ApiError("image API returned malformed image headers")
    return parsed


def _required_header(response: httpx.Response, name: str) -> str:
    value = response.headers.get(name)
    if value is None or not value:
        raise ApiError("image API returned malformed image headers")
    return str(value)


def _required_header_decimal(response: httpx.Response, name: str) -> Decimal:
    value = response.headers.get(name)
    try:
        parsed = Decimal(value) if value is not None else Decimal(-1)
    except InvalidOperation as error:
        raise ApiError("image API returned malformed image headers") from error
    if not parsed.is_finite() or parsed < 0:
        raise ApiError("image API returned malformed image headers")
    return parsed


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
