import base64
import hashlib
from pathlib import Path

import httpx
import pytest

from image_platform_cli.api import ImageApiClient, save_image
from image_platform_cli.errors import ApiError


def png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def response_for(request: httpx.Request, data: bytes) -> httpx.Response:
    digest = hashlib.sha256(data).hexdigest()
    return httpx.Response(
        200,
        headers={"X-Image-SHA256": digest, "Cache-Control": "no-store"},
        json={
            "output": {
                "image": {
                    "mime_type": "image/png",
                    "sha256": digest,
                    "size_bytes": len(data),
                    "width": 256,
                    "height": 256,
                },
                "data_base64": base64.b64encode(data).decode(),
            },
            "receipt": {"model_id": "model", "model_revision": "revision"},
            "prompt_plan": {},
        },
        request=request,
    )


def test_generate_validates_response_and_saves_without_overwrite(tmp_path: Path) -> None:
    data = png_header(256, 256)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.example/v1/generations"
        assert request.headers["Authorization"] == "Bearer access-secret"
        return response_for(request, data)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        image = ImageApiClient(http, "https://api.example").generate(
            "access-secret", prompt="blue cup", width=256, height=256, seed=1, optimize=True
        )
    finally:
        http.close()
    output = tmp_path / "result.png"
    save_image(image, output)
    assert output.read_bytes() == data
    with pytest.raises(ApiError, match="already exists"):
        save_image(image, output)


def test_generate_rejects_digest_mismatch() -> None:
    data = png_header(256, 256)

    def handler(request: httpx.Request) -> httpx.Response:
        response = response_for(request, data)
        response.headers["X-Image-SHA256"] = "0" * 64
        return response

    http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ApiError, match="integrity"):
            ImageApiClient(http, "https://api.example").generate(
                "access-secret", prompt="blue cup", width=256, height=256, seed=1, optimize=False
            )
    finally:
        http.close()


def test_generate_reports_only_safe_status_and_request_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"X-Request-ID": "request-safe"},
            json={"error": "secret upstream detail"},
            request=request,
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ApiError) as captured:
            ImageApiClient(http, "https://api.example").generate(
                "access-secret", prompt="blue cup", width=256, height=256, seed=1, optimize=False
            )
    finally:
        http.close()
    assert str(captured.value) == "image API returned HTTP 403 (request request-safe)"
    assert "secret upstream detail" not in str(captured.value)
