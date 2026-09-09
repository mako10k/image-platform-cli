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
from image_platform_cli.v4.project_quad import QuadOptions


class QuadAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


def quad_case(tmp_path: Path, mode: str = "source_over") -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads(
        (Path(__file__).parent / f"fixtures/project-quad/cli-quad-{mode}.json").read_text()
    )
    for key in ("source", "texture"):
        (tmp_path / f"{key}.png").write_bytes(
            base64.b64decode(wire["request"]["inputs"][key]["data_base64"])
        )
    output = tmp_path / "projected.png"
    args = [
        "edit",
        "raster",
        "project-quad",
        "--input",
        str(tmp_path / "source.png"),
        "--texture",
        str(tmp_path / "texture.png"),
        "--destination",
        "1,1,7,2,6,7,2,6",
        "-o",
        str(output),
    ]
    if mode != "source_over":
        args.extend(["--composite", mode])
    return wire, args, output


@pytest.mark.parametrize("mode", ["source_over", "replace", "multiply", "screen"])
def test_projection_compositing_modes(tmp_path: Path, mode: str) -> None:
    wire, args, output = quad_case(tmp_path, mode)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parser().parse_args(args), QuadAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image:
        assert image.size == (8, 8) and image.mode == "RGBA"
        assert image.getpixel((7, 7)) == (20, 40, 80, 128)
        assert image.getpixel((4, 4)) != (20, 40, 80, 128)


@pytest.mark.parametrize(
    "points",
    [
        (0, 0, 2, 2, 0, 2, 2, 0),
        (0, 0, 1, 0, 2, 0, 3, 0),
        (0, 0, 2, 0, 1, 1, 2, 2),
        (0, 0, 0, 0, 2, 2, 0, 2),
        (0, 0, 2, 0, 2, 2),
        (0, 0, 1000001, 0, 2, 2, 0, 2),
    ],
)
def test_invalid_quad_is_local(tmp_path: Path, points: tuple[int, ...]) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid quad reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").project_quad(
            "dummy",
            input_path=tmp_path / "absent.png",
            texture_path=tmp_path / "absent-texture.png",
            options=QuadOptions(points),
        )


@pytest.mark.parametrize("bad", ["texture", "missing_texture", "command", "dimensions"])
def test_quad_bad_evidence_prevents_save(tmp_path: Path, bad: str) -> None:
    wire, args, output = quad_case(tmp_path)
    receipt = wire["body"]["data"]["receipt"]
    if bad == "texture":
        receipt["input_sha256s"]["texture"] = "0" * 64
    elif bad == "missing_texture":
        del receipt["input_sha256s"]["texture"]
    elif bad == "command":
        receipt["commands"][0]["normalized_command_sha256"] = "0" * 64
    else:
        receipt["output_height"] = 3
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(parser().parse_args(args), QuadAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


def test_quad_offline_reverse_winding_and_negative_coordinates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("offline preview attempted configuration or HTTP")

    monkeypatch.setattr("image_platform_cli.v4.cli.Config.staging", forbidden)
    monkeypatch.setattr("image_platform_cli.v4.cli.httpx.Client", forbidden)
    assert (
        main(
            [
                "edit",
                "raster",
                "project-quad",
                "--input",
                "absent.png",
                "--texture",
                "absent-texture.png",
                "--destination=-2,-2,-2,2,2,2,2,-2",
                "--dry-run",
            ]
        )
        == 0
    )
    command = json.loads(capsys.readouterr().out)["commands"][0]
    assert command["destination"][0] == {"x": -2, "y": -2} and command["composite"] == "source_over"
    with pytest.raises(ApiError):
        QuadOptions((0, 0, 2, 0, 2, 2, 0, 2), "wrong").program()
