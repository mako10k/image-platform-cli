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
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.compositing import CompositeOptions
from image_platform_cli.v4.edit_cli import run_edit


class CompositeAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


def composite_case(
    tmp_path: Path, name: str = "masked-crop"
) -> tuple[dict[str, Any], list[str], Path]:
    wire = json.loads(
        (Path(__file__).parent / f"fixtures/composite/cli-composite-{name}.json").read_text()
    )
    for key, value in wire["request"]["inputs"].items():
        (tmp_path / f"{key}.png").write_bytes(base64.b64decode(value["data_base64"]))
    output = tmp_path / "composite.png"
    args = [
        "edit",
        "composite",
        "--background",
        str(tmp_path / "source.png"),
        "--overlay",
        str(tmp_path / "overlay.png"),
        "-o",
        str(output),
    ]
    if name == "masked-crop":
        args.extend(
            [
                "--mask",
                str(tmp_path / "mask.png"),
                "--matrix",
                "1,0,0,1,1.5,2",
                "--opacity",
                "0.5",
                "--crop",
                "1,1,5,4",
            ]
        )
    elif name != "source_over":
        args.extend(["--composite", name])
    return wire, args, output


@pytest.mark.parametrize("name", ["source_over", "replace", "multiply", "screen", "masked-crop"])
def test_composite_modes_mask_transform_and_crop(tmp_path: Path, name: str) -> None:
    wire, args, output = composite_case(tmp_path, name)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v4/image-operations"
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(
            parser().parse_args(args), CompositeAuth(), V4ApiClient(http, "https://api.invalid")
        )
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["data_base64"])
    with Image.open(output) as image:
        assert image.size == ((5, 4) if name == "masked-crop" else (8, 8)) and image.mode == "RGBA"


@pytest.mark.parametrize(
    "bad",
    [
        "missing_crop",
        "reordered",
        "crop_hash",
        "mask_hash",
        "overlay_hash",
        "planner_commands",
        "geometry",
    ],
)
def test_composite_all_operations_and_inputs_are_verified(tmp_path: Path, bad: str) -> None:
    wire, args, output = composite_case(tmp_path)
    data = wire["body"]["data"]
    receipt = data["receipt"]
    if bad == "missing_crop":
        receipt["commands"].pop()
    elif bad == "reordered":
        receipt["commands"].reverse()
    elif bad == "crop_hash":
        receipt["commands"][1]["normalized_command_sha256"] = "0" * 64
    elif bad == "mask_hash":
        receipt["input_sha256s"]["mask"] = "0" * 64
    elif bad == "overlay_hash":
        receipt["input_sha256s"]["overlay"] = "0" * 64
    elif bad == "planner_commands":
        data["planner_receipt"]["nodes"][0]["command_ids"].pop()
    else:
        receipt["output_width"] = 8
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(
            parser().parse_args(args), CompositeAuth(), V4ApiClient(http, "https://api.invalid")
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "options",
    [
        CompositeOptions(matrix=(Decimal(1),)),
        CompositeOptions(matrix=(Decimal("NaN"),) * 6),
        CompositeOptions(matrix=(Decimal(65537),) * 6),
        CompositeOptions(opacity=Decimal("NaN")),
        CompositeOptions(opacity=Decimal("-0.1")),
        CompositeOptions(opacity=Decimal("1.1")),
        CompositeOptions(mode="wrong"),
        CompositeOptions(crop=(0, 0, 0, 2)),
    ],
)
def test_invalid_composite_controls_are_local(tmp_path: Path, options: CompositeOptions) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid composite reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").composite_image(
            "dummy",
            background_path=tmp_path / "absent.png",
            overlay_path=tmp_path / "overlay.png",
            mask_path=None,
            options=options,
        )
