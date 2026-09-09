import base64
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import CliError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.edit_cli import raster_program, run_edit


@pytest.mark.parametrize("index", range(7))
def test_remaining_raster_cpu_execution(tmp_path: Path, index: int) -> None:
    wire = json.loads(
        (
            Path(__file__).parent / f"fixtures/remaining-raster/cli-remaining-{index}.json"
        ).read_text()
    )
    for key, value in wire["request"]["inputs"].items():
        (tmp_path / f"{key}.png").write_bytes(base64.b64decode(value["data_base64"]))
    args = list(wire["args"])
    if args[0] == "auto-crop":
        args[args.index("--mask") + 1] = str(tmp_path / "selection.png")
    if args[0] == "mesh":
        mesh = tmp_path / "mesh.json"
        mesh.write_text(json.dumps(wire["mesh_spec"]))
        args[args.index("--texture") + 1] = str(tmp_path / "texture.png")
        args[args.index("--mesh-spec") + 1] = str(mesh)
    output = tmp_path / "result.png"
    parsed = parser().parse_args(
        ["edit", "raster", *args, "--input", str(tmp_path / "source.png"), "-o", str(output)]
    )
    assert raster_program(parsed) == wire["request"]["program"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == wire["request"]
        assert request.url.path == "/v4/image-operations"
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    auth = Mock()
    auth.access_token.return_value = "dummy"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parsed, auth, V4ApiClient(http, "https://api.invalid"))
    auth.access_token.assert_called_once_with(frozenset({"images:edit"}))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image:
        assert image.size == ((4, 3) if index == 4 else (6, 5) if index == 5 else (8, 8))


@pytest.mark.parametrize(
    "args",
    [
        ["adjust"],
        ["adjust", "--hue", "181"],
        ["adjust", "--exposure", "NaN"],
        ["auto-crop", "--mask", "absent.png", "--threshold", "1.1"],
        ["auto-crop", "--mask", "absent.png", "--padding", "-1"],
    ],
)
def test_remaining_invalid_controls_are_local(args: list[str]) -> None:
    parsed = parser().parse_args(["edit", "raster", *args, "--input", "absent.png", "--dry-run"])
    with pytest.raises(CliError):
        raster_program(parsed)


def test_mesh_cannot_override_operation(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text('{"op":"convert"}')
    parsed = parser().parse_args(
        [
            "edit",
            "raster",
            "mesh",
            "--texture",
            "absent.png",
            "--mesh-spec",
            str(spec),
            "--input",
            "absent.png",
            "--dry-run",
        ]
    )
    with pytest.raises(CliError, match="override"):
        raster_program(parsed)
