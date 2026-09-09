import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import ApiError, CliError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.segment_cli import run_segment, validate_segment_outputs
from image_platform_cli.v4.segmentation import SegmentSelector


@pytest.fixture
def sample(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    wire = json.loads(
        (Path(__file__).parent / "fixtures/native-v4-segmentation.r8.json").read_text()
    )
    source = tmp_path / "source.png"
    source.write_bytes(base64.b64decode(wire["request"]["input"]["data_base64"]))
    return source, wire


class SegmentAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:understand"})
        return "dummy"


@pytest.mark.parametrize(
    "selector",
    [
        ["--text", "cup"],
        ["--box", "0,0,512,512"],
        ["--point", "20,30", "--negative-point", "50,60"],
    ],
)
def test_segment_selectors_and_all_output_types(
    sample: tuple[Path, dict[str, Any]], selector: list[str]
) -> None:
    source, wire = sample
    targets = {
        name: source.with_name(f"{name}.png") for name in ("mask", "foreground", "background")
    }
    args = parser().parse_args(
        [
            "edit",
            "segment",
            "--input",
            str(source),
            *selector,
            *[part for name, path in targets.items() for part in (f"--{name}-output", str(path))],
        ]
    )

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/segmentations"
        payload = json.loads(request.content)
        key = {"--text": "text", "--box": "box", "--point": "points"}[selector[0]]
        assert set(payload) == {"input", key}
        if key == "points":
            assert payload[key] == [
                {"x": 20, "y": 30, "positive": True},
                {"x": 50, "y": 60, "positive": False},
            ]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        run_segment(args, SegmentAuth(), V4ApiClient(http, "https://api.invalid"))
    assert targets["mask"].read_bytes() == base64.b64decode(
        wire["body"]["data"]["output"]["data_base64"]
    )
    for name, alpha in (("foreground", 255), ("background", 0)):
        with Image.open(targets[name]) as image:
            assert image.size == (512, 512)
            assert image.getpixel((0, 0)) == (0, 0, 128, alpha)


@pytest.mark.parametrize(
    "bad", ["input_hash", "mask_shape", "profile", "model", "header", "cost", "bytes"]
)
def test_segment_rejects_bad_result_before_any_output(
    sample: tuple[Path, dict[str, Any]], bad: str
) -> None:
    source, wire = sample
    receipt = wire["body"]["data"]["receipt"]
    if bad == "input_hash":
        receipt["input_image"]["sha256"] = "0" * 64
    elif bad == "mask_shape":
        receipt["mask_image"]["width"] = 10
    elif bad == "profile":
        receipt["profile"] = "wrong"
    elif bad == "model":
        receipt["grounding_model_revision"] = "wrong"
    elif bad == "header":
        wire["headers"]["x-image-sha256"] = "0" * 64
    elif bad == "cost":
        wire["headers"]["x-image-compute-cost-usd"] = "99"
    else:
        wire["body"]["data"]["output"]["data_base64"] = "not-base64"
    output = source.with_name("mask.png")
    args = parser().parse_args(
        ["edit", "segment", "--input", str(source), "--text", "cup", "--mask-output", str(output)]
    )
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_segment(args, SegmentAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


@pytest.mark.parametrize(
    "selector",
    [
        SegmentSelector(),
        SegmentSelector(text=" "),
        SegmentSelector(box=(0, 0, 513, 512)),
        SegmentSelector(points=[(-1, 0, True)]),
        SegmentSelector(points=[(0, 0, False)]),
        SegmentSelector(points=[(0, 0, True)] * 33),
    ],
)
def test_invalid_segment_selector_is_local(
    sample: tuple[Path, dict[str, Any]], selector: SegmentSelector
) -> None:
    source, _ = sample

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid selector reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").segment(
            "dummy", input_path=source, selector=selector
        )


def test_segment_requires_distinct_available_outputs(sample: tuple[Path, dict[str, Any]]) -> None:
    source, _ = sample
    base = ["edit", "segment", "--input", str(source), "--text", "cup"]
    for extra in (
        [],
        ["--mask-output", str(source)],
        ["--mask-output", "out.png", "--foreground-output", "./out.png"],
    ):
        with pytest.raises(CliError):
            validate_segment_outputs(parser().parse_args(base + extra))
