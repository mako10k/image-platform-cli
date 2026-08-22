import base64
import hashlib
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from image_platform_cli.api import (
    ImageApiClient,
    _resolve_seed,
    require_available_output,
    save_image,
    save_segmentation_outputs,
)
from image_platform_cli.errors import ApiError
from image_platform_cli.models import SegmentationResult


def png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00" * 8
        + b"IEND\xaeB`\x82"
    )


def valid_png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "navy").save(output, format="PNG")
    return output.getvalue()


def artifact(data: bytes) -> dict[str, object]:
    return {
        "artifact_id": "art_generation01",
        "namespace": "default",
        "kind": "image",
        "state": "ready",
        "created_at": "2026-08-21T00:00:00Z",
        "upload_expires_at": "2026-08-21T00:15:00Z",
        "result": {
            "artifact": {
                "artifact_id": "art_generation01",
                "kind": "image",
                "sha256": hashlib.sha256(data).hexdigest(),
                "mime_type": "image/png",
                "size_bytes": len(data),
                "width": 256,
                "height": 256,
            },
            "url": "https://objects.example/signed-result",
            "expires_at": "2026-08-21T00:05:00Z",
        },
    }


def test_generate_polls_and_downloads_without_leaking_oauth_token(tmp_path: Path) -> None:
    data = png_header(256, 256)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/generations":
            assert request.headers["Authorization"] == "Bearer access-secret"
            assert request.headers["Idempotency-Key"]
            assert '"wait_seconds":0' in request.read().decode()
            return httpx.Response(
                202,
                headers={"Retry-After": "1"},
                json={
                    "job_id": "job_generation01",
                    "status": "queued",
                    "status_url": "https://api-staging.image.mk10.org/v1/jobs/job_generation01",
                    "cancel_url": (
                        "https://api-staging.image.mk10.org/v1/jobs/job_generation01/cancel"
                    ),
                    "submitted_at": "2026-08-21T00:00:00Z",
                    "execution": {"wait_seconds": 0},
                },
                request=request,
            )
        if request.url.path == "/v1/jobs/job_generation01":
            assert request.headers["Authorization"] == "Bearer access-secret"
            return httpx.Response(
                200,
                json={
                    "job_id": "job_generation01",
                    "status": "completed",
                    "steps": [
                        {
                            "id": "generate",
                            "status": "completed",
                            "value_outputs": {"seed": 1},
                        }
                    ],
                    "outputs": [{"artifact_id": "art_generation01"}],
                    "cost": {"estimated_usd": "0.04", "actual_usd": "0.03"},
                },
                request=request,
            )
        if request.url.path == "/v1/artifacts/art_generation01":
            assert request.headers["Authorization"] == "Bearer access-secret"
            return httpx.Response(200, json=artifact(data), request=request)
        assert request.url == "https://objects.example/signed-result"
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=data, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        image = ImageApiClient(
            http, "https://api-staging.image.mk10.org", sleeper=lambda _delay: None
        ).generate(
            "access-secret",
            prompt="blue cup",
            width=256,
            height=256,
            seed=1,
            optimize=True,
            wait_seconds=0,
        )
    output = tmp_path / "result.png"
    save_image(image, output)
    assert output.read_bytes() == data
    assert len(requests) == 4
    with pytest.raises(ApiError, match="already exists"):
        save_image(image, output)


def test_optimize_prompt_calls_native_planner_endpoint_only() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/v1/prompt-plans"
        assert request.headers["Authorization"] == "Bearer access-secret"
        return httpx.Response(
            200,
            json={"prompt": "a carefully composed blue cup", "seed": 42},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        optimized = ImageApiClient(http, "https://api.example").optimize_prompt(
            "access-secret", prompt="blue cup", width=512, seed=42
        )

    assert optimized == "a carefully composed blue cup"
    assert [request.url.path for request in requests] == ["/v1/prompt-plans"]
    assert b'"query":"blue cup"' in requests[0].read()
    assert b'"width":512' in requests[0].read()
    assert b'"seed":42' in requests[0].read()
    assert b'"height"' not in requests[0].read()


def test_image_to_image_uses_native_route_and_verifies_receipt(tmp_path: Path) -> None:
    source = valid_png(256, 256)
    result = valid_png(512, 640)
    input_path = tmp_path / "rough.png"
    input_path.write_bytes(source)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = request.read().decode()
        assert request.url.path == "/v1/image-to-image"
        assert request.headers["Authorization"] == "Bearer access-secret"
        assert '"profile":"i2i-stable-diffusion-v1-5"' in payload
        assert '"mime_type":"image/png"' in payload
        assert '"strength":"0.6"' in payload
        assert '"guidance_scale":"8"' in payload
        assert '"inference_steps":30' in payload
        assert '"seed":42' in payload
        assert '"width":512' in payload and '"height":640' in payload
        return httpx.Response(
            200,
            json={
                "output": {
                    "image": {
                        "sha256": hashlib.sha256(result).hexdigest(),
                        "mime_type": "image/png",
                        "size_bytes": len(result),
                        "width": 512,
                        "height": 640,
                    },
                    "data_base64": base64.b64encode(result).decode("ascii"),
                },
                "receipt": {
                    "profile": "i2i-stable-diffusion-v1-5",
                    "model_id": "stable-diffusion-v1-5/stable-diffusion-v1-5",
                    "model_revision": "451f4fe16113bff5a5d2269ed5ad43b0592e9a14",
                    "measured_compute_cost_usd": "0.001234",
                    "seed": 42,
                    "controls": {
                        "strength": "0.6",
                        "negative_prompt_applied": True,
                        "guidance_scale": "8",
                        "inference_steps": 30,
                        "width": 512,
                        "height": 640,
                    },
                },
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        image = ImageApiClient(http, "https://api.example").image_to_image(
            "access-secret",
            prompt="paint this as watercolor",
            input_path=input_path,
            profile="i2i-stable-diffusion-v1-5",
            negative_prompt="text",
            strength=Decimal("0.6"),
            guidance_scale=Decimal(8),
            inference_steps=30,
            seed=42,
            width=512,
            height=640,
        )

    assert image.data == result
    assert image.sha256 == hashlib.sha256(result).hexdigest()
    assert image.width == 512 and image.height == 640 and image.seed == 42
    assert image.measured_compute_cost_usd == Decimal("0.001234")
    assert image.model_id == "stable-diffusion-v1-5/stable-diffusion-v1-5"
    assert image.model_revision == "451f4fe16113bff5a5d2269ed5ad43b0592e9a14"
    assert len(requests) == 1


def test_image_to_image_rejects_invalid_input_before_request(tmp_path: Path) -> None:
    input_path = tmp_path / "rough.png"
    input_path.write_bytes(b"not an image")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="input image is invalid"),
    ):
        ImageApiClient(http, "https://api.example").image_to_image(
            "access-secret",
            prompt="watercolor",
            input_path=input_path,
            profile="i2i-stable-diffusion-v1-5",
            negative_prompt=None,
            strength=Decimal("0.75"),
            guidance_scale=Decimal("7.5"),
            inference_steps=25,
            seed=1,
            width=None,
            height=None,
        )

    assert requests == []


def test_segment_uses_point_selector_and_verifies_mask_receipt(tmp_path: Path) -> None:
    source = valid_png(256, 256)
    mask_output = BytesIO()
    Image.new("L", (256, 256), 255).save(mask_output, format="PNG")
    mask = mask_output.getvalue()
    input_path = tmp_path / "scene.png"
    input_path.write_bytes(source)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode()
        assert request.url.path == "/v1/segmentations"
        assert request.headers["Authorization"] == "Bearer access-secret"
        assert '"points":[{"x":12,"y":34,"positive":true}' in payload
        assert '{"x":56,"y":78,"positive":false}' in payload
        source_metadata = {
            "sha256": hashlib.sha256(source).hexdigest(),
            "width": 256,
            "height": 256,
        }
        mask_metadata = {
            "sha256": hashlib.sha256(mask).hexdigest(),
            "mime_type": "image/png",
            "size_bytes": len(mask),
            "width": 256,
            "height": 256,
        }
        return httpx.Response(
            200,
            json={
                "output": {
                    "image": mask_metadata,
                    "data_base64": base64.b64encode(mask).decode("ascii"),
                },
                "receipt": {
                    "profile": "segment-grounding-dino-sam2-tiny",
                    "input_image": source_metadata,
                    "mask_image": mask_metadata,
                },
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").segment(
            "access-secret",
            input_path=input_path,
            text=None,
            points=[(12, 34, True), (56, 78, False)],
            box=None,
        )

    assert result.mask_data == mask
    assert result.mask_sha256 == hashlib.sha256(mask).hexdigest()


def test_segmentation_outputs_are_all_preflighted_before_writing(tmp_path: Path) -> None:
    source = valid_png(256, 256)
    mask_buffer = BytesIO()
    Image.new("L", (256, 256), 255).save(mask_buffer, format="PNG")
    mask = mask_buffer.getvalue()
    result = SegmentationResult(source, mask, hashlib.sha256(mask).hexdigest(), 256, 256)
    mask_path = tmp_path / "mask.png"
    foreground_path = tmp_path / "foreground.png"
    foreground_path.write_bytes(b"existing")

    with pytest.raises(ApiError, match="already exists"):
        save_segmentation_outputs(
            result,
            mask_output=mask_path,
            foreground_output=foreground_path,
            background_output=None,
        )

    assert not mask_path.exists()
    assert foreground_path.read_bytes() == b"existing"


def test_segmentation_writes_mask_foreground_and_background(tmp_path: Path) -> None:
    source = valid_png(256, 256)
    mask_buffer = BytesIO()
    Image.new("L", (256, 256), 255).save(mask_buffer, format="PNG")
    mask = mask_buffer.getvalue()
    result = SegmentationResult(source, mask, hashlib.sha256(mask).hexdigest(), 256, 256)
    mask_path = tmp_path / "mask.png"
    foreground_path = tmp_path / "foreground.png"
    background_path = tmp_path / "background.png"

    save_segmentation_outputs(
        result,
        mask_output=mask_path,
        foreground_output=foreground_path,
        background_output=background_path,
    )

    assert mask_path.read_bytes() == mask
    with Image.open(foreground_path) as foreground:
        assert foreground.mode == "RGBA" and foreground.size == (256, 256)
        assert foreground.getchannel("A").getextrema() == (255, 255)
    with Image.open(background_path) as background:
        assert background.mode == "RGBA" and background.size == (256, 256)
        assert background.getchannel("A").getextrema() == (0, 0)


def test_composite_uses_native_image_operations_and_verifies_receipt(tmp_path: Path) -> None:
    background = valid_png(256, 256)
    overlay = valid_png(128, 128)
    mask_buffer = BytesIO()
    Image.new("L", (256, 256), 255).save(mask_buffer, format="PNG")
    mask = mask_buffer.getvalue()
    result = valid_png(200, 220)
    background_path = tmp_path / "background.png"
    overlay_path = tmp_path / "overlay.png"
    mask_path = tmp_path / "mask.png"
    background_path.write_bytes(background)
    overlay_path.write_bytes(overlay)
    mask_path.write_bytes(mask)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode()
        assert request.url.path == "/v1/image-operations"
        assert request.headers["Authorization"] == "Bearer access-secret"
        assert '"source_input":"background"' in payload
        assert '"op":"paste_image"' in payload
        assert '"kind":"mask_input","input":"mask"' in payload
        assert '"transform":{"a":"1","b":"0","c":"0","d":"1","e":"20","f":"30"}' in payload
        assert '"op":"crop"' in payload
        image_metadata = {
            "sha256": hashlib.sha256(result).hexdigest(),
            "mime_type": "image/png",
            "size_bytes": len(result),
            "width": 200,
            "height": 220,
        }
        return httpx.Response(
            200,
            json={
                "image": image_metadata,
                "data_base64": base64.b64encode(result).decode("ascii"),
                "receipt": {
                    "contract_revision": "deterministic-edit-v1",
                    "program_sha256": "a" * 64,
                    "input_sha256s": {
                        "background": hashlib.sha256(background).hexdigest(),
                        "overlay": hashlib.sha256(overlay).hexdigest(),
                        "mask": hashlib.sha256(mask).hexdigest(),
                    },
                    "commands": [
                        {"id": "place-overlay", "op": "paste_image"},
                        {"id": "crop-result", "op": "crop"},
                    ],
                    "output_sha256": hashlib.sha256(result).hexdigest(),
                    "output_width": 200,
                    "output_height": 220,
                },
                "estimated_cost_usd": "0",
                "actual_cost_usd": "0",
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        edited = ImageApiClient(http, "https://api.example").composite(
            "access-secret",
            background_path=background_path,
            overlay_path=overlay_path,
            mask_path=mask_path,
            transform=(Decimal(1), Decimal(0), Decimal(0), Decimal(1), Decimal(20), Decimal(30)),
            opacity=Decimal("0.8"),
            crop=(0, 0, 200, 220),
        )

    assert edited.data == result
    assert edited.sha256 == hashlib.sha256(result).hexdigest()
    assert edited.program_sha256 == "a" * 64


def test_generic_deterministic_program_binds_inputs_and_verifies_command_hashes(
    tmp_path: Path,
) -> None:
    source = valid_png(256, 256)
    source_path = tmp_path / "source.png"
    source_path.write_bytes(source)
    program_path = tmp_path / "program.json"
    program_path.write_text(
        '{"revision":"deterministic-edit-v1","inputs":{"source":"image"},'
        '"source_input":"source","commands":[{"id":"flip","op":"flip",'
        '"axis":"horizontal"}],"encoding":{"format":"png"}}',
        encoding="utf-8",
    )
    program_hash = "a" * 64
    normalized_hash = "b" * 64
    pixel_hash = "c" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/image-operations"
        assert request.headers["Authorization"] == "Bearer access-secret"
        assert '"source_input":"source"' in request.read().decode()
        metadata = {
            "sha256": hashlib.sha256(source).hexdigest(),
            "mime_type": "image/png",
            "size_bytes": len(source),
            "width": 256,
            "height": 256,
        }
        return httpx.Response(
            200,
            json={
                "image": metadata,
                "data_base64": base64.b64encode(source).decode("ascii"),
                "receipt": {
                    "contract_revision": "deterministic-edit-v1",
                    "program_sha256": program_hash,
                    "input_sha256s": {"source": hashlib.sha256(source).hexdigest()},
                    "commands": [
                        {
                            "id": "flip",
                            "op": "flip",
                            "normalized_command_sha256": normalized_hash,
                            "output_pixel_sha256": pixel_hash,
                        }
                    ],
                    "output_sha256": hashlib.sha256(source).hexdigest(),
                    "output_width": 256,
                    "output_height": 256,
                },
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = ImageApiClient(http, "https://api.example")
        program, inputs, masks = api.load_deterministic_program(
            program_path, input_bindings=[f"source={source_path}"], mask_bindings=[]
        )
        result = api.run_deterministic_program(
            "access-secret", program=program, input_paths=inputs, mask_paths=masks
        )

    assert result.program_sha256 == program_hash
    assert result.command_receipts == (("flip", "flip", normalized_hash, pixel_hash),)


def test_inpaint_uses_explicit_mask_route_and_verifies_model_headers(tmp_path: Path) -> None:
    source = valid_png(256, 256)
    mask_buffer = BytesIO()
    Image.new("L", (256, 256), 255).save(mask_buffer, format="PNG")
    mask = mask_buffer.getvalue()
    result = valid_png(256, 256)
    input_path = tmp_path / "scene.png"
    mask_path = tmp_path / "mask.png"
    input_path.write_bytes(source)
    mask_path.write_bytes(mask)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert request.url.path == "/v2beta/stable-image/edit/inpaint"
        assert request.headers["Authorization"] == "Bearer access-secret"
        assert b'name="image"' in payload and b'name="mask"' in payload
        assert b'name="grow_mask"' in payload and b"\r\n\r\n0\r\n" in payload
        assert b'name="seed"' in payload and b"\r\n\r\n42\r\n" in payload
        digest = hashlib.sha256(result).hexdigest()
        return httpx.Response(
            200,
            content=result,
            headers={
                "Content-Type": "image/png",
                "Seed": "42",
                "X-Image-SHA256": digest,
                "X-Image-Native-SHA256": digest,
                "X-Image-Backend-Profile": "inpaint-stable-diffusion-v1-5",
                "X-Image-Backend-Model": "stable-diffusion-v1-5/stable-diffusion-inpainting",
                "X-Image-Backend-Revision": "8a4288a76071f7280aedbdb3253bdb9e9d5d84bb",
                "X-Image-Width": "256",
                "X-Image-Height": "256",
                "X-Image-Compute-Cost-Usd": "0.000987",
                "X-Image-Safety-Filter-Requested": "default",
                "X-Image-Safety-Filter-Effective": "enabled",
                "X-Image-Safety-Filter-Outcome": "passed",
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        image = ImageApiClient(http, "https://api.example").inpaint(
            "access-secret",
            prompt="remove the object",
            input_path=input_path,
            mask_path=mask_path,
            profile="inpaint-stable-diffusion-v1-5",
            seed=42,
        )

    assert image.data == result and image.seed == 42
    assert image.sha256 == hashlib.sha256(result).hexdigest()
    assert image.measured_compute_cost_usd == Decimal("0.000987")
    assert image.model_id == "stable-diffusion-v1-5/stable-diffusion-inpainting"
    assert image.safety_filter_requested == "default"
    assert image.safety_filter_effective == "enabled"
    assert image.safety_filter_outcome == "passed"


def test_inpaint_rejects_mismatched_mask_before_request(tmp_path: Path) -> None:
    input_path = tmp_path / "scene.png"
    mask_path = tmp_path / "mask.png"
    input_path.write_bytes(valid_png(256, 256))
    mask_path.write_bytes(valid_png(512, 512))
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="dimensions must match"),
    ):
        ImageApiClient(http, "https://api.example").inpaint(
            "access-secret",
            prompt="remove the object",
            input_path=input_path,
            mask_path=mask_path,
            profile="inpaint-stable-diffusion-v1-5",
            seed=42,
        )

    assert requests == []


def test_capabilities_projects_only_safe_editing_states() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/capabilities"
        assert request.headers["Authorization"] == "Bearer access-secret"
        return httpx.Response(
            200,
            json={
                "service": "image-platform",
                "status": "phase2_durable_private",
                "operation_states": [
                    {
                        "operation": operation,
                        "declared": True,
                        "configured": operation != "inpaint",
                        "authorized": operation in {"edit", "image_ops"},
                        "reason": (
                            "service_not_configured"
                            if operation == "inpaint"
                            else "principal_not_permitted"
                            if operation == "segment"
                            else None
                        ),
                        "private_registry": "must not be exposed",
                    }
                    for operation in ("edit", "segment", "image_ops", "inpaint", "generate")
                ],
                "image_ops_contract": {"registered_fonts": ["private-font"]},
                "transport_secret": "must not be exposed",
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").capabilities("access-secret")

    assert result == {
        "service": "image-platform",
        "status": "phase2_durable_private",
        "capabilities": [
            {
                "name": "image_to_image",
                "operation": "edit",
                "endpoint": "/v1/image-to-image",
                "declared": True,
                "configured": True,
                "authorized": True,
                "reason": None,
            },
            {
                "name": "segmentation",
                "operation": "segment",
                "endpoint": "/v1/segmentations",
                "declared": True,
                "configured": True,
                "authorized": False,
                "reason": "principal_not_permitted",
            },
            {
                "name": "image_operations",
                "operation": "image_ops",
                "endpoint": "/v1/image-operations",
                "declared": True,
                "configured": True,
                "authorized": True,
                "reason": None,
            },
            {
                "name": "inpaint",
                "operation": "inpaint",
                "endpoint": "/v1/images/edits",
                "declared": True,
                "configured": False,
                "authorized": False,
                "reason": "service_not_configured",
            },
        ],
    }


def test_capabilities_fails_closed_when_an_editing_state_is_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "service": "image-platform",
                "status": "phase1_stateless",
                "operation_states": [],
            },
            request=request,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="omitted an editing capability"),
    ):
        ImageApiClient(http, "https://api.example").capabilities("access-secret")


def test_optimize_prompt_rejects_mismatched_effective_seed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"prompt": "optimized", "seed": 8}, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="unexpected effective seed"),
    ):
        ImageApiClient(http, "https://api.example").optimize_prompt(
            "access-secret", prompt="blue cup", seed=7
        )


def test_optimize_prompt_reports_safe_server_reason_code_without_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            headers={"X-Request-ID": "request-1"},
            json={
                "code": "prompt_word_count_invalid",
                "message": "must not be disclosed by the CLI",
            },
            request=request,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(
            ApiError,
            match=r"HTTP 502 \[prompt_word_count_invalid\] \(request request-1\)$",
        ) as raised,
    ):
        ImageApiClient(http, "https://api.example").optimize_prompt(
            "access-secret", prompt="blue cup", seed=7
        )

    assert "must not be disclosed" not in str(raised.value)


def test_generate_accepts_immediate_completed_artifact() -> None:
    data = png_header(256, 256)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/generations":
            return httpx.Response(
                200,
                json={
                    "job_id": "job_generation01",
                    "status": "completed",
                    "result": artifact(data),
                    "seed": 1,
                },
                request=request,
            )
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=data, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        image = ImageApiClient(http, "https://api.example").generate(
            "access-secret", prompt="blue cup", width=256, height=256, seed=1, optimize=False
        )
    assert image.sha256 == hashlib.sha256(data).hexdigest()


def test_generate_rejects_cross_origin_status_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            202,
            json={"status_url": "https://attacker.invalid/jobs/job_generation01"},
            request=request,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="unsafe status URL"),
    ):
        ImageApiClient(http, "https://api.example").generate(
            "access-secret", prompt="blue cup", width=256, height=256, seed=1, optimize=False
        )


@pytest.mark.parametrize("wait", [61, 120])
def test_long_wait_requires_explicit_opt_in(wait: int) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as http,
        pytest.raises(ApiError, match="allow-long-wait"),
    ):
        ImageApiClient(http, "https://api.example").generate(
            "access-secret",
            prompt="blue cup",
            width=256,
            height=256,
            seed=1,
            optimize=False,
            wait_seconds=wait,
        )


def test_generate_reports_only_safe_status_and_request_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"X-Request-ID": "request-safe"},
            json={"error": "secret upstream detail"},
            request=request,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError) as captured,
    ):
        ImageApiClient(http, "https://api.example").generate(
            "access-secret", prompt="blue cup", width=256, height=256, seed=1, optimize=False
        )
    assert str(captured.value) == "image API returned HTTP 403 (request request-safe)"
    assert "secret upstream detail" not in str(captured.value)


def test_unspecified_seed_resolves_to_random_nonzero_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("image_platform_cli.api.secrets.randbelow", lambda upper: upper - 2)

    assert _resolve_seed(None) == 2**63 - 2
    assert _resolve_seed(0) == 0
    assert _resolve_seed(42) == 42


def test_output_conflict_is_rejected_by_preflight_before_generation(tmp_path: Path) -> None:
    output = tmp_path / "existing.png"
    output.write_bytes(b"existing")

    with pytest.raises(ApiError, match="already exists"):
        require_available_output(output)

    assert output.read_bytes() == b"existing"


def test_job_inventory_follows_cursor_only_with_bounded_maximum() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer access-secret"
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "data": [{"job_id": "job_2", "prompt": "secret"}],
                    "next_cursor": "opaque-cursor",
                    "has_more": True,
                },
                request=request,
            )
        assert cursor == "opaque-cursor"
        return httpx.Response(
            200,
            json={"data": [{"job_id": "job_1"}], "next_cursor": None, "has_more": False},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").list_jobs(
            "access-secret", statuses=["completed"], page_size=1, max_items=2
        )

    assert result == {
        "data": [{"job_id": "job_2"}, {"job_id": "job_1"}],
        "next_cursor": None,
        "has_more": False,
    }
    assert len(requests) == 2
    assert requests[0].url.params.get_list("status") == ["completed"]


def test_artifact_show_removes_signed_url_and_private_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "artifact_id": "art_1",
                "object_key": "private/key",
                "result": {
                    "url": "https://objects.example/signed",
                    "artifact": {"sha256": "a" * 64, "prompt": "private prompt"},
                },
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").get_artifact("access-secret", "art_1")

    assert result == {"artifact_id": "art_1", "result": {"artifact": {"sha256": "a" * 64}}}


def test_job_show_removes_entire_nested_prompt_plan() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": "job_1",
                "status": "completed",
                "steps": [
                    {
                        "id": "generate",
                        "status": "completed",
                        "value_outputs": {
                            "seed": 42,
                            "prompt_plan": {
                                "intent": {"subject": "must remain secret"},
                                "negative_prompt": "also secret",
                            },
                        },
                    }
                ],
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").get_job("access-secret", "job_1")

    assert result["steps"][0]["value_outputs"] == {"seed": 42}
    assert "secret" not in str(result)


def test_artifact_download_preflights_and_does_not_forward_oauth(tmp_path: Path) -> None:
    data = valid_png(256, 256)
    output = tmp_path / "artifact.png"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "api.example":
            assert request.headers["Authorization"] == "Bearer access-secret"
            return httpx.Response(200, json=artifact(data), request=request)
        assert request.url == "https://objects.example/signed-result"
        assert "Authorization" not in request.headers
        return httpx.Response(
            200, content=data, headers={"Content-Type": "image/png"}, request=request
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").download_artifact(
            "access-secret", "art_generation01", output
        )

    assert output.read_bytes() == data
    assert "url" not in result["result"]
    assert len(requests) == 2

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="already exists"),
    ):
        ImageApiClient(http, "https://api.example").download_artifact(
            "access-secret", "art_generation01", output
        )
    assert len(requests) == 2


def test_artifact_download_rejects_integrity_mismatch_without_output(tmp_path: Path) -> None:
    data = valid_png(256, 256)
    output = tmp_path / "artifact.png"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.example":
            body = artifact(data)
            body["result"]["artifact"]["sha256"] = "0" * 64  # type: ignore[index]
            return httpx.Response(200, json=body, request=request)
        return httpx.Response(
            200, content=data, headers={"Content-Type": "image/png"}, request=request
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="integrity check failed"),
    ):
        ImageApiClient(http, "https://api.example").download_artifact(
            "access-secret", "art_generation01", output
        )
    assert not output.exists()


def test_batch_plan_uses_native_server_planner_and_preserves_resolved_prompts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.read().decode()
        assert request.url.path == "/v1/batch-plans"
        assert request.headers["Idempotency-Key"]
        assert '"intent":"blue cup"' in body
        return httpx.Response(
            201,
            json={
                "plan_id": "bplan_1",
                "created_at": "2026-08-21T00:00:00Z",
                "profile": "generation-standard",
                "model_revision": "model-revision",
                "width": 512,
                "height": 512,
                "root_seed": 42,
                "items": [
                    {"index": 0, "prompt": "resolved blue cup", "seed": 7},
                    {"index": 1, "prompt": "alternate blue cup", "seed": 8},
                ],
                "estimated_cost_usd": "0.080000000",
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").create_batch_plan(
            "access-secret",
            intent="blue cup",
            width=512,
            height=512,
            candidate_count=2,
            root_seed=42,
        )

    assert [item["prompt"] for item in result["items"]] == [
        "resolved blue cup",
        "alternate blue cup",
    ]
    assert len(requests) == 1


def test_campaign_run_waits_with_one_idempotent_write_and_bounded_reads() -> None:
    requests: list[httpx.Request] = []
    now = [0.0]

    def sleep(delay: float) -> None:
        now[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/v1/campaigns"
            assert request.headers["Idempotency-Key"]
            return httpx.Response(
                202,
                json={"campaign_id": "campaign_1", "status": "queued"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"campaign_id": "campaign_1", "status": "completed"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(
            http, "https://api.example", sleeper=sleep, clock=lambda: now[0]
        ).create_campaign(
            "access-secret",
            plan_id="bplan_1",
            max_cost_usd=Decimal("0.08"),
            wait_seconds=30,
        )

    assert result["status"] == "completed"
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/campaigns"),
        ("GET", "/v1/campaigns/campaign_1"),
    ]


def test_campaign_results_follow_only_canonical_child_jobs_and_artifacts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/campaigns/campaign_1":
            return httpx.Response(
                200,
                json={
                    "campaign_id": "campaign_1",
                    "status": "completed",
                    "child_job_ids": ["job_1"],
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "job_id": "job_1",
                "status": "completed",
                "outputs": [{"artifact_id": "art_1"}],
                "prompt": "must be removed",
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ImageApiClient(http, "https://api.example").campaign_results(
            "access-secret", "campaign_1"
        )

    assert result["artifacts"] == [{"job_id": "job_1", "artifact_id": "art_1"}]
    assert "prompt" not in result["jobs"][0]


@pytest.mark.parametrize("wait", [61, 120])
def test_campaign_long_wait_requires_explicit_opt_in(wait: int) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as http,
        pytest.raises(ApiError, match="allow-long-wait"),
    ):
        ImageApiClient(http, "https://api.example").create_campaign(
            "access-secret", plan_id="bplan_1", max_cost_usd="0.04", wait_seconds=wait
        )
