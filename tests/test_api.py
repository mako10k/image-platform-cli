import hashlib
from pathlib import Path

import httpx
import pytest

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
                    "status_url": "https://api.example/v1/jobs/job_generation01",
                    "cancel_url": "https://api.example/v1/jobs/job_generation01/cancel",
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
        image = ImageApiClient(http, "https://api.example", sleeper=lambda _delay: None).generate(
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
