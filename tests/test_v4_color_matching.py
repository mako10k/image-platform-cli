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
from image_platform_cli.v4.color_matching import ColorMatchOptions
from image_platform_cli.v4.edit_cli import run_edit


class ColorAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


def color_case(
    tmp_path: Path, name: str = "lab_mean_std_v1-1"
) -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads(
        (Path(__file__).parent / f"fixtures/color-match/cli-colormatch-{name}.json").read_text()
    )
    for key in ("source", "reference"):
        (tmp_path / f"{key}.png").write_bytes(
            base64.b64decode(wire["request"]["inputs"][key]["data_base64"])
        )
    command = wire["request"]["program"]["commands"][0]
    output = tmp_path / "matched.png"
    args = [
        "edit",
        "raster",
        "color-match",
        "--input",
        str(tmp_path / "source.png"),
        "--reference",
        str(tmp_path / "reference.png"),
        "-o",
        str(output),
    ]
    if command["algorithm"] != "lab_mean_std_v1":
        args.extend(["--algorithm", command["algorithm"]])
    if command["strength"] != "1":
        args.extend(["--strength", command["strength"]])
    if command["preserve_luminance"]:
        args.append("--preserve-luminance")
    return wire, args, output


@pytest.mark.parametrize(
    "name",
    [
        "lab_mean_std_v1-1",
        "lab_histogram_256_v1-1",
        "lab_mean_std_v1-0.5",
        "lab_histogram_256_v1-0.5",
        "lab_mean_std_v1-0",
    ],
)
def test_color_matching_algorithms_controls_and_reference(tmp_path: Path, name: str) -> None:
    wire, args, output = color_case(tmp_path, name)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/image-operations" and request.method == "POST"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(parser().parse_args(args), ColorAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image, Image.open(tmp_path / "source.png") as source:
        assert image.size == source.size == (8, 8)
        assert image.getchannel("A").tobytes() == source.getchannel("A").tobytes()
        if name.endswith("-0"):
            assert image.tobytes() == source.tobytes()


@pytest.mark.parametrize(
    "bad",
    [
        "reference_hash",
        "source_hash",
        "missing_reference",
        "swapped_inputs",
        "program",
        "dimensions",
    ],
)
def test_color_matching_evidence_binds_both_inputs(tmp_path: Path, bad: str) -> None:
    wire, args, output = color_case(tmp_path)
    receipt = wire["body"]["data"]["receipt"]
    hashes = receipt["input_sha256s"]
    if bad == "reference_hash":
        hashes["reference"] = "0" * 64
    elif bad == "source_hash":
        hashes["source"] = "0" * 64
    elif bad == "missing_reference":
        del hashes["reference"]
    elif bad == "swapped_inputs":
        hashes["source"], hashes["reference"] = hashes["reference"], hashes["source"]
    elif bad == "program":
        receipt["program_sha256"] = "0" * 64
    else:
        receipt["output_width"] = 4
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(parser().parse_args(args), ColorAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


@pytest.mark.parametrize("strength", ["-0.1", "1.1", "NaN", "Infinity"])
def test_color_match_invalid_strength_is_local(tmp_path: Path, strength: str) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid controls reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").color_match(
            "dummy",
            input_path=tmp_path / "absent.png",
            reference_path=tmp_path / "absent-ref.png",
            options=ColorMatchOptions(strength=Decimal(strength)),
        )


def test_color_match_offline_preview(
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
                "color-match",
                "--input",
                "absent.png",
                "--reference",
                "absent-ref.png",
                "--preserve-luminance",
                "--dry-run",
            ]
        )
        == 0
    )
    program = json.loads(capsys.readouterr().out)
    assert program["inputs"] == {"source": "image", "reference": "image"}
    assert program["commands"][0]["preserve_luminance"] is True
    with pytest.raises(ApiError):
        ColorMatchOptions(algorithm="unknown").program()
