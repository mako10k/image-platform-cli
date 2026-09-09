import base64
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.edit_cli import raster_program, run_edit


class GeometryAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


@pytest.mark.parametrize("index", range(8))
def test_geometry_cpu_fixture_and_shared_builder(tmp_path: Path, index: int) -> None:
    wire = json.loads(
        (Path(__file__).parent / f"fixtures/geometry/cli-geometry-{index}.json").read_text()
    )
    source, output = tmp_path / "source.png", tmp_path / "output.png"
    source.write_bytes(base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"]))
    args = parser().parse_args(
        ["edit", "raster", *wire["args"], "--input", str(source), "-o", str(output)]
    )
    assert raster_program(args) == wire["request"]["program"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(args, GeometryAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    command = wire["request"]["program"]["commands"][0]
    with Image.open(output) as image:
        assert image.size == (command["output_width"], command["output_height"])
