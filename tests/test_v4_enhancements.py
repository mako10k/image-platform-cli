import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from test_v4_api import png_bytes, response

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.edit_cli import run_edit


def enhancement_response(input_data: bytes, output_data: bytes) -> httpx.Response:
    input_digest = hashlib.sha256(input_data).hexdigest()
    output_digest = hashlib.sha256(output_data).hexdigest()
    return response(
        {
            "output": {
                "image": {
                    "mime_type": "image/png",
                    "sha256": output_digest,
                    "size_bytes": len(output_data),
                    "width": 64,
                    "height": 64,
                },
                "data_base64": base64.b64encode(output_data).decode("ascii"),
            },
            "receipt": {
                "operation": "upscale",
                "quality_tier": "deterministic",
                "profile": "cpu-lanczos-v1",
                "model_id": None,
                "model_revision": None,
                "model_sha256": None,
                "input_image": {"sha256": input_digest, "width": 32, "height": 32},
                "output_image": {"sha256": output_digest, "width": 64, "height": 64},
                "cold_start": False,
                "model_load_seconds": "0",
                "inference_seconds": "0",
                "measured_compute_cost_usd": "0",
            },
        },
        extra_headers={
            "X-Image-SHA256": output_digest,
            "X-Image-Operation": "upscale",
            "X-Image-Enhancement-Profile": "cpu-lanczos-v1",
            "X-Image-Compute-Cost-Usd": "0",
        },
    )


def test_upscale_command_uses_enhancement_route_and_saves_verified_output(tmp_path: Path) -> None:
    input_data, output_data = png_bytes(32, 32), png_bytes(64, 64)
    source, output = tmp_path / "source.png", tmp_path / "result.png"
    source.write_bytes(input_data)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert json.loads(request.content) == {
            "input": {
                "mime_type": "image/png",
                "data_base64": base64.b64encode(input_data).decode("ascii"),
            },
            "operation": "upscale",
            "quality_tier": "deterministic",
            "width": 64,
            "height": 64,
        }
        return enhancement_response(input_data, output_data)

    auth = Mock()
    auth.access_token.return_value = "token"
    args = parser().parse_args(
        [
            "edit",
            "upscale",
            "--input",
            str(source),
            "--width",
            "64",
            "--height",
            "64",
            "-o",
            str(output),
        ]
    )
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        run_edit(args, auth, V4ApiClient(http, "https://api.invalid"))

    assert [request.url.path for request in requests] == ["/v4/enhancements"]
    assert output.read_bytes() == output_data
    auth.access_token.assert_called_once_with(frozenset({"images:edit"}))


def test_inconsistent_enhancement_receipt_does_not_save_output(tmp_path: Path) -> None:
    input_data, output_data = png_bytes(32, 32), png_bytes(64, 64)
    source, output = tmp_path / "source.png", tmp_path / "result.png"
    source.write_bytes(input_data)
    reply = enhancement_response(input_data, output_data)
    body = reply.json()
    body["data"]["receipt"]["output_image"]["width"] = 32
    args = parser().parse_args(
        [
            "edit",
            "upscale",
            "--input",
            str(source),
            "--width",
            "64",
            "--height",
            "64",
            "-o",
            str(output),
        ]
    )
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=body, headers=reply.headers)
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(
            args,
            Mock(access_token=Mock(return_value="token")),
            V4ApiClient(http, "https://api.invalid"),
        )
    assert not output.exists()


def test_restore_uses_input_dimensions() -> None:
    args = parser().parse_args(["edit", "restore", "--input", "in.png", "-o", "out.png"])
    assert args.command == "restore"
    assert not hasattr(args, "width")
