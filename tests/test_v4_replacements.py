import base64
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import CliError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import main, parser
from image_platform_cli.v4.edit_cli import run_edit
from image_platform_cli.v4.program_cli import prepare_cli_program


@pytest.mark.parametrize("index", range(8))
def test_replacement_cpu_execution(tmp_path: Path, index: int) -> None:
    wire = json.loads(
        (Path(__file__).parent / f"fixtures/replacements/cli-replacement-{index}.json").read_text()
    )
    for key, value in wire["request"]["inputs"].items():
        (tmp_path / f"{key}.png").write_bytes(base64.b64decode(value["data_base64"]))
    options = list(wire["args"])
    if "--mask" in options:
        options[options.index("--mask") + 1] = str(tmp_path / "mask0.png")
    output = tmp_path / "result.png"
    args = parser().parse_args(
        [
            "edit",
            *options,
            "--base",
            str(tmp_path / "base.png"),
            "--replacement",
            str(tmp_path / "replacement.png"),
            "--mask",
            str(tmp_path / ("mask1.png" if "--mask" in options else "mask0.png")),
            "-o",
            str(output),
        ]
    )
    assert not prepare_cli_program(args)
    assert args.prepared_program == wire["request"]["program"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    auth = Mock()
    auth.access_token.return_value = "dummy"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(args, auth, V4ApiClient(http, "https://api.invalid"))
    auth.access_token.assert_called_once_with(frozenset({"images:edit"}))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    if index in {0, 1}:
        with Image.open(output) as image, Image.open(tmp_path / "base.png") as base:
            assert image.getpixel((0, 0)) == (
                base.getpixel((0, 0)) if index == 0 else (220, 20, 40, 255)
            )
            assert image.getpixel((3, 3)) == (
                (220, 20, 40, 255) if index == 0 else base.getpixel((3, 3))
            )


@pytest.mark.parametrize(
    "options",
    [
        ["replace-background", "--invert"],
        ["replace-background", "--mask", "other.png"],
        ["replace-object", "--threshold", "NaN"],
        ["replace-object", "--threshold", "1.1"],
        ["replace-object", "--feather", "NaN"],
        ["replace-object", "--padding", "1", "--dilate", "1"],
        ["replace-object", "--erode", "0"],
    ],
)
def test_invalid_replacement_is_local(options: list[str]) -> None:
    args = parser().parse_args(
        [
            "edit",
            *options,
            "--base",
            "absent.png",
            "--replacement",
            "absent.png",
            "--mask",
            "absent.png",
            "--dry-run",
        ]
    )
    with pytest.raises(CliError):
        prepare_cli_program(args)


def test_replacement_dry_run_without_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "image_platform_cli.v4.cli.Config.staging", lambda: pytest.fail("configuration accessed")
    )
    assert (
        main(
            [
                "edit",
                "replace-background",
                "--base",
                "absent.png",
                "--replacement",
                "absent.png",
                "--mask",
                "absent.png",
                "--dry-run",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["commands"][0]["coverage"]["base"]["transforms"] == [
        {"op": "invert"}
    ]
