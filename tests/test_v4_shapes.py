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
from image_platform_cli.v4.shapes import ShapeOptions


class ShapeAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


def shape_case(tmp_path: Path, name: str) -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads((Path(__file__).parent / f"fixtures/shape/cli-shape-{name}.json").read_text())
    source, output = tmp_path / "source.png", tmp_path / "shape.png"
    source.write_bytes(base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"]))
    command = wire["request"]["program"]["commands"][0]
    args = [
        "edit",
        "raster",
        "shape",
        "--input",
        str(source),
        "--kind",
        command["shape"],
        "--rect",
        "1,1,6,5",
        "--stroke-width",
        "2",
        "-o",
        str(output),
    ]
    for key in ("fill", "stroke"):
        if command[key] is not None:
            args.extend(
                [
                    f"--{key}",
                    ",".join(str(command[key][channel]) for channel in ("r", "g", "b", "a")),
                ]
            )
    return wire, args, output


@pytest.mark.parametrize(
    "name",
    [
        "rectangle-fill",
        "rectangle-stroke",
        "rectangle-both",
        "ellipse-fill",
        "ellipse-stroke",
        "ellipse-both",
    ],
)
def test_shapes_and_paint_variants(tmp_path: Path, name: str) -> None:
    wire, args, output = shape_case(tmp_path, name)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parser().parse_args(args), ShapeAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image:
        assert image.size == (8, 8) and image.mode == "RGBA"
        assert image.getpixel((7, 7)) == (20, 40, 80, 128)
        assert image.getpixel((3, 1)) != (20, 40, 80, 128)


@pytest.mark.parametrize(
    "options",
    [
        ShapeOptions("rectangle", (0, 0, 3, 3)),
        ShapeOptions("line", (0, 0, 3, 3), fill=(0, 0, 0, 255)),
        ShapeOptions("ellipse", (0, 0, 0, 3), fill=(0, 0, 0, 255)),
        ShapeOptions("ellipse", (-1000001, 0, 3, 3), fill=(0, 0, 0, 255)),
        ShapeOptions("ellipse", (0, 0, 8193, 3), fill=(0, 0, 0, 255)),
        ShapeOptions("ellipse", (0, 0, 3, 3), fill=(256, 0, 0, 255)),
        ShapeOptions("ellipse", (0, 0, 3, 3), stroke=(0, 0, 0, 255), stroke_width=0),
        ShapeOptions("ellipse", (0, 0, 3, 3), stroke=(0, 0, 0, 255), stroke_width=1025),
    ],
)
def test_invalid_shapes_are_local(tmp_path: Path, options: ShapeOptions) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid shape reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").draw_shape(
            "dummy", input_path=tmp_path / "absent.png", options=options
        )


@pytest.mark.parametrize("bad", ["command", "program", "dimensions"])
def test_shape_receipt_mismatch_prevents_save(tmp_path: Path, bad: str) -> None:
    wire, args, output = shape_case(tmp_path, "ellipse-both")
    receipt = wire["body"]["data"]["receipt"]
    if bad == "command":
        receipt["commands"][0]["normalized_command_sha256"] = "0" * 64
    elif bad == "program":
        receipt["program_sha256"] = "0" * 64
    else:
        receipt["output_width"] = 3
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(parser().parse_args(args), ShapeAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


def test_shape_offline_preview_and_default_stroke(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("preview attempted config or network")

    monkeypatch.setattr("image_platform_cli.v4.cli.Config.staging", forbidden)
    monkeypatch.setattr("image_platform_cli.v4.cli.httpx.Client", forbidden)
    args = [
        "edit",
        "raster",
        "shape",
        "--input",
        "absent.png",
        "--kind",
        "rectangle",
        "--rect=-1,0,2,3",
        "--stroke",
        "0,0,0,0",
        "--dry-run",
    ]
    assert main(args) == 0
    command = json.loads(capsys.readouterr().out)["commands"][0]
    assert (
        command["stroke_width"] == 1 and command["stroke"]["a"] == 0 and command["rect"]["x"] == -1
    )
    assert main([*args, "--stroke-width", "1024"]) == 0
