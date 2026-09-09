import base64
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import main, parser
from image_platform_cli.v4.edit_cli import run_edit
from image_platform_cli.v4.filtering import filter_program

FIXTURES = Path(__file__).parent / "fixtures/filter"


class FilterAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


def setup_case(tmp_path: Path, name: str) -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads((FIXTURES / f"cli-filter-{name}.json").read_text())
    source, output = tmp_path / "source.png", tmp_path / "filtered.png"
    source.write_bytes(base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"]))
    command = wire["request"]["program"]["commands"][0]
    argv = [
        "edit",
        "raster",
        "filter",
        "--input",
        str(source),
        "-o",
        str(output),
        "--kind",
        command["filter"],
        "--radius",
        command["radius"],
    ]
    if command["amount"] != "1":
        argv.extend(["--amount", command["amount"]])
    return wire, argv, output


@pytest.mark.parametrize(
    "name",
    [
        "gaussian_blur-1.5-1",
        "box_blur-1.5-1",
        "unsharp_mask-1.5-1",
        "unsharp_mask-64-16",
        "unsharp_mask-0.5-0",
    ],
)
def test_filter_variants_and_bounds_from_real_cpu(tmp_path: Path, name: str) -> None:
    wire, argv, output = setup_case(tmp_path, name)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/image-operations" and request.method == "POST"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parser().parse_args(argv), FilterAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image:
        assert image.size == (8, 8) and image.mode == "RGBA"


@pytest.mark.parametrize(
    "radius,amount",
    [
        ("0", "1"),
        ("65", "1"),
        ("NaN", "1"),
        ("Infinity", "1"),
        ("1", "-1"),
        ("1", "17"),
        ("1", "NaN"),
        ("1", "Infinity"),
    ],
)
def test_filter_invalid_controls_never_reach_http(tmp_path: Path, radius: str, amount: str) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid filter controls reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").filter_image(
            "dummy",
            input_path=tmp_path / "absent.png",
            kind="box_blur",
            radius=Decimal(radius),
            amount=Decimal(amount),
        )


@pytest.mark.parametrize("bad", ["command", "program", "geometry", "header"])
def test_filter_bad_evidence_prevents_save(tmp_path: Path, bad: str) -> None:
    wire, argv, output = setup_case(tmp_path, "box_blur-1.5-1")
    receipt = wire["body"]["data"]["receipt"]
    if bad == "command":
        receipt["commands"][0]["normalized_command_sha256"] = "0" * 64
    elif bad == "program":
        receipt["program_sha256"] = "0" * 64
    elif bad == "geometry":
        receipt["output_height"] = 3
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
        run_edit(parser().parse_args(argv), FilterAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


def test_filter_offline_preview(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("preview attempted configuration or HTTP")

    monkeypatch.setattr("image_platform_cli.v4.cli.Config.staging", forbidden)
    monkeypatch.setattr("image_platform_cli.v4.cli.httpx.Client", forbidden)
    args = [
        "edit",
        "raster",
        "filter",
        "--input",
        "absent.png",
        "--kind",
        "box_blur",
        "--radius",
        "1.25",
        "--dry-run",
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["commands"][0] == {
        "id": "filter",
        "op": "filter",
        "filter": "box_blur",
        "radius": "1.25",
        "amount": "1",
        "border": "reflect",
        "coverage": None,
    }
    assert main([*args, "--amount", "NaN"]) == 2
    with pytest.raises(ApiError):
        filter_program("unknown", Decimal(1))
