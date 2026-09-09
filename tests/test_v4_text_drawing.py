import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import main, parser
from image_platform_cli.v4.edit_cli import run_edit
from image_platform_cli.v4.text_drawing import TextOptions


class TextAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


def text_case(tmp_path: Path, style: str = "fill") -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads((Path(__file__).parent / f"fixtures/text/cli-text-{style}.json").read_text())
    source, output = tmp_path / "source.png", tmp_path / "text.png"
    source.write_bytes(base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"]))
    command = wire["request"]["program"]["commands"][0]
    args = [
        "edit",
        "raster",
        "text",
        command["text"],
        "--input",
        str(source),
        "-o",
        str(output),
        "--position",
        "4,4",
        "--font-id",
        "dejavu",
        "--font-sha256",
        command["font"]["sha256"],
        "--font-size",
        "16",
        "--fill",
        "255,0,0,128",
    ]
    if style == "stroke":
        args.extend(["--stroke", "0,255,0,255", "--stroke-width", "2"])
    return wire, args, output


@pytest.mark.parametrize("style", ["fill", "stroke"])
def test_registered_font_text_and_stroke(tmp_path: Path, style: str) -> None:
    wire, args, output = text_case(tmp_path, style)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/image-operations" and request.method == "POST"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parser().parse_args(args), TextAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image:
        assert image.size == (64, 32) and image.mode == "RGBA"
        assert image.getpixel((63, 31)) == (20, 40, 80, 128)
        assert len(set(image.getdata())) > 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", ""),
        ("text", "x" * 4097),
        ("font_id", "../font"),
        ("font_sha256", "A" * 64),
        ("font_size", 0),
        ("font_size", 2049),
        ("stroke_width", -1),
        ("stroke_width", 129),
        ("position", (1000001, 0)),
        ("fill", (0, 0, 0, 256)),
    ],
)
def test_invalid_text_controls_never_reach_http(tmp_path: Path, field: str, value: Any) -> None:
    options = replace(
        TextOptions("hello", (0, 0), "dejavu", "0" * 64, 16, (255, 0, 0, 128)), **{field: value}
    )

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid text controls reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").draw_text(
            "dummy", input_path=tmp_path / "absent.png", options=options
        )


@pytest.mark.parametrize("bad", ["command_hash", "program_hash", "dimensions"])
def test_text_bad_receipts_prevent_output(tmp_path: Path, bad: str) -> None:
    wire, args, output = text_case(tmp_path)
    receipt = wire["body"]["data"]["receipt"]
    if bad == "command_hash":
        receipt["commands"][0]["normalized_command_sha256"] = "0" * 64
    elif bad == "program_hash":
        receipt["program_sha256"] = "0" * 64
    else:
        receipt["output_width"] = 1
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(parser().parse_args(args), TextAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


def test_text_offline_unicode_preview(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("preview attempted configuration or HTTP")

    monkeypatch.setattr("image_platform_cli.v4.cli.Config.staging", forbidden)
    monkeypatch.setattr("image_platform_cli.v4.cli.httpx.Client", forbidden)
    args = [
        "edit",
        "raster",
        "text",
        "日本語\nABC",
        "--input",
        "absent.png",
        "--position=-1,0",
        "--font-id",
        "dejavu",
        "--font-sha256",
        "0" * 64,
        "--font-size",
        "2048",
        "--fill",
        "0,0,0,0",
        "--stroke-width",
        "128",
        "--dry-run",
    ]
    assert main(args) == 0
    command = json.loads(capsys.readouterr().out)["commands"][0]
    assert command["text"] == "日本語\nABC" and command["position"]["x"] == -1
    assert command["fill"]["a"] == 0 and command["stroke_width"] == 128
