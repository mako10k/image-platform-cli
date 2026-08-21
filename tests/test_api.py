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
)
from image_platform_cli.errors import ApiError


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
