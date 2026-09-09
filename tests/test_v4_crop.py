import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import main, parser
from image_platform_cli.v4.crop import crop_program
from image_platform_cli.v4.edit_cli import run_edit


def crop_case(tmp_path: Path, name: str = "inside") -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads((Path(__file__).parent / f"fixtures/crop/cli-crop-{name}.json").read_text())
    source = tmp_path / "source.png"
    source.write_bytes(base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"]))
    output = tmp_path / "crop.png"
    rect = wire["request"]["program"]["commands"][0]["rect"]
    coordinates = ",".join(str(rect[key]) for key in ("x", "y", "width", "height"))
    argv = [
        "edit",
        "raster",
        "crop",
        "--input",
        str(source),
        f"--rect={coordinates}",
        "-o",
        str(output),
    ]
    return wire, argv, output


class CropAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


@pytest.mark.parametrize("name", ["inside", "padding", "outside"])
def test_crop_real_cpu_geometry_and_pixels(tmp_path: Path, name: str) -> None:
    wire, argv, output = crop_case(tmp_path, name)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parser().parse_args(argv), CropAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    source = base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"])
    rect = wire["request"]["program"]["commands"][0]["rect"]
    with Image.open(BytesIO(source)) as original, Image.open(output) as cropped:
        x, y, width, height = (rect[key] for key in ("x", "y", "width", "height"))
        expected = original.crop((x, y, x + width, y + height))
        assert cropped.size == (width, height)
        assert cropped.tobytes() == expected.tobytes()


@pytest.mark.parametrize("bad", ["geometry", "command", "planner_input", "program", "header"])
def test_crop_rejects_wrong_evidence_before_output(tmp_path: Path, bad: str) -> None:
    wire, argv, output = crop_case(tmp_path)
    data = wire["body"]["data"]
    if bad == "geometry":
        data["receipt"]["output_width"] = 8
    elif bad == "command":
        data["receipt"]["commands"][0]["id"] = "convert"
    elif bad == "planner_input":
        data["planner_receipt"]["nodes"][0]["width"] = 3
    elif bad == "program":
        data["receipt"]["program_sha256"] = "0" * 64
    else:
        wire["headers"]["x-image-width"] = "8"
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(parser().parse_args(argv), CropAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


@pytest.mark.parametrize(
    "rect",
    [
        (0, 0, 0, 2),
        (0, 0, -1, 2),
        (0, 0, 8193, 1),
        (0, 0, 4096, 4096),
        (-1000001, 0, 1, 1),
        (0, True, 1, 1),
    ],
)
def test_crop_invalid_rectangle_rejected(rect: tuple[int, int, int, int]) -> None:
    with pytest.raises(ApiError):
        crop_program(rect)


def test_crop_dry_run_has_no_configuration_network_or_input_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("offline dry-run attempted configuration or HTTP")

    monkeypatch.setattr("image_platform_cli.v4.cli.Config.staging", forbidden)
    monkeypatch.setattr("image_platform_cli.v4.cli.httpx.Client", forbidden)
    assert (
        main(["edit", "raster", "crop", "--input", "absent.png", "--rect=-1,2,3,4", "--dry-run"])
        == 0
    )
    program = json.loads(capsys.readouterr().out)
    assert program["commands"][0]["rect"] == {"x": -1, "y": 2, "width": 3, "height": 4}
    assert program["encoding"]["format"] == "png"
    assert main(["edit", "raster", "crop", "--input", "absent.png", "--rect=0,0,3,4"]) == 2
    assert "--output is required" in capsys.readouterr().err
