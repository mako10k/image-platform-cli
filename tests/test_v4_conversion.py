import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.edit_cli import run_edit

FIXTURES = Path(__file__).parent / "fixtures/conversion"


class ConversionAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


def conversion_case(tmp_path: Path, name: str = "png-90") -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads((FIXTURES / f"cli-convert-{name}.json").read_text())
    source = tmp_path / "input.png"
    source.write_bytes(base64.b64decode(wire["request"]["inputs"]["source"]["data_base64"]))
    output = tmp_path / "output.image"
    fmt, quality = name.split("-")
    argv = ["edit", "convert", "--input", str(source), "-o", str(output), "--format", fmt]
    if quality != "90":
        argv.extend(["--quality", quality])
    return wire, argv, output


@pytest.mark.parametrize(
    "name", ["png-90", "jpeg-1", "jpeg-90", "jpeg-100", "webp-1", "webp-90", "webp-100"]
)
def test_conversion_formats_and_quality_from_local_cpu_api(tmp_path: Path, name: str) -> None:
    wire, argv, output = conversion_case(tmp_path, name)

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        run_edit(
            parser().parse_args(argv), ConversionAuth(), V4ApiClient(http, "https://api.invalid")
        )
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image:
        assert image.format == name.split("-")[0].upper() and image.size == (8, 8)
        if name == "png-90":
            assert image.getpixel((1, 1)) == (20, 40, 80, 128)
        if name.startswith("jpeg"):
            assert image.mode == "RGB"


@pytest.mark.parametrize(
    "case",
    [
        "input",
        "program",
        "command",
        "output",
        "bytes",
        "format",
        "header",
        "node",
        "logical",
        "physical_header",
        "missing_planner",
        "cost",
        "estimated_cost",
        "nonfinite_cost",
        "unknown",
    ],
)
def test_conversion_rejects_inconsistent_execution_evidence(tmp_path: Path, case: str) -> None:
    wire, argv, output = conversion_case(tmp_path)
    data, headers = wire["body"]["data"], wire["headers"]
    receipt = data["receipt"]
    if case == "input":
        receipt["input_sha256s"]["source"] = "0" * 64
    elif case == "program":
        receipt["program_sha256"] = "0" * 64
    elif case == "command":
        receipt["commands"][0]["normalized_command_sha256"] = "0" * 64
    elif case == "output":
        receipt["output_width"] = 10
    elif case == "bytes":
        data["data_base64"] = "bad!"
    elif case == "format":
        data["image"]["mime_type"] = "image/jpeg"
    elif case == "header":
        headers["x-image-width"] = "10"
    elif case == "node":
        data["planner_receipt"]["nodes"][0]["program_sha256"] = "0" * 64
    elif case == "logical":
        data["planner_receipt"]["logical_program_sha256"] = "0" * 64
    elif case == "physical_header":
        headers["x-image-physical-graph-sha256"] = "0" * 64
    elif case == "missing_planner":
        data["planner_receipt"] = None
    elif case in {"cost", "estimated_cost", "nonfinite_cost"}:
        key = "estimated_cost_usd" if case == "estimated_cost" else "actual_cost_usd"
        data[key] = "NaN" if case == "nonfinite_cost" else "-1"
    else:
        receipt["unknown"] = True
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=headers)
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(
            parser().parse_args(argv), ConversionAuth(), V4ApiClient(http, "https://api.invalid")
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "fmt,quality", [("png", 1), ("jpeg", 0), ("webp", 101), ("gif", 90), ("jpeg", True)]
)
def test_invalid_conversion_options_rejected_before_http(
    tmp_path: Path, fmt: str, quality: int
) -> None:
    conversion_case(tmp_path)

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid conversion reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").convert_image(
            "dummy", input_path=tmp_path / "input.png", format_name=fmt, quality=quality
        )
