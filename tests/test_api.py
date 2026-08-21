import hashlib
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
        result = ImageApiClient(http, "https://api.example").get_artifact(
            "access-secret", "art_1"
        )

    assert result == {"artifact_id": "art_1", "result": {"artifact": {"sha256": "a" * 64}}}


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
