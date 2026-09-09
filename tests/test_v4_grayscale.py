import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import main, parser
from image_platform_cli.v4.edit_cli import run_edit


def sample(tmp_path: Path, mode: str = "RGBA") -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads(
        (Path(__file__).parent / f"fixtures/grayscale/cli-grayscale-{mode}.json").read_text()
    )
    source, output = tmp_path / "source.png", tmp_path / "gray.png"
    source.write_bytes(base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"]))
    return wire, ["edit", "raster", "grayscale", "--input", str(source), "-o", str(output)], output


class GrayAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_grayscale_rec709_pixels_and_alpha(tmp_path: Path, mode: str) -> None:
    wire, argv, output = sample(tmp_path, mode)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parser().parse_args(argv), GrayAuth(), V4ApiClient(http, "https://api.invalid"))
    with Image.open(output) as image:
        assert image.size == (4, 1) and image.format == "PNG"
        pixels = list(image.convert("RGBA").getdata())
        # Rec.709 linear luminance converted back to sRGB, not encoded-channel averaging.
        assert pixels[0] == (127, 127, 127, 255)
        assert pixels[1] == (220, 220, 220, 128 if mode == "RGBA" else 255)
        assert pixels[3] == (100, 100, 100, 64 if mode == "RGBA" else 255)
        assert pixels[2][3] == (0 if mode == "RGBA" else 255)


@pytest.mark.parametrize("bad", ["luminance", "geometry", "input", "header"])
def test_grayscale_rejects_wrong_receipt_before_saving(tmp_path: Path, bad: str) -> None:
    wire, argv, output = sample(tmp_path)
    receipt = wire["body"]["data"]["receipt"]
    if bad == "luminance":
        receipt["commands"][0]["normalized_command_sha256"] = "0" * 64
    elif bad == "geometry":
        receipt["output_width"] = 3
    elif bad == "input":
        receipt["input_sha256s"]["source"] = "0" * 64
    else:
        wire["headers"]["x-image-program-sha256"] = "0" * 64
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(parser().parse_args(argv), GrayAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


def test_grayscale_offline_preview_and_required_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("dry-run attempted configuration or transport")

    monkeypatch.setattr("image_platform_cli.v4.cli.Config.staging", forbidden)
    monkeypatch.setattr("image_platform_cli.v4.cli.httpx.Client", forbidden)
    argv = ["edit", "raster", "grayscale", "--input", "absent.png"]
    assert main([*argv, "--dry-run"]) == 0
    program = json.loads(capsys.readouterr().out)
    assert program["commands"] == [
        {
            "id": "grayscale",
            "op": "grayscale",
            "luminance": "rec709_linear_srgb_v1",
            "coverage": None,
        }
    ]
    assert main(argv) == 2
    assert "--output is required" in capsys.readouterr().err
