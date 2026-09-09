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


@pytest.fixture
def sample(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    wire = json.loads(
        (Path(__file__).parent / "fixtures/native-v4-image-receipts.r8.json").read_text()
    )
    source = tmp_path / "input.png"
    source.write_bytes(base64.b64decode(wire["request"]["input"]["data_base64"]))
    return source, wire["inpaint"]


class InpaintAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy-token"


@pytest.mark.parametrize("mode", ["default", "enabled", "disabled"])
def test_inpaint_command_saves_verified_mask_result(
    sample: tuple[Path, dict[str, Any]], mode: str
) -> None:
    source, wire = sample
    safety = wire["body"]["data"]["receipt"]["safety_filter"]
    safety.update(
        requested=mode,
        effective="disabled" if mode == "disabled" else "enabled",
        outcome="not_run" if mode == "disabled" else "passed",
    )
    for key, value in safety.items():
        wire["headers"][f"x-image-safety-filter-{key}"] = value
    output = source.with_name("out.png")
    args = parser().parse_args(
        [
            "edit",
            "inpaint",
            "watercolor",
            "--input",
            str(source),
            "--mask",
            str(source),
            "--output",
            str(output),
            "--seed",
            "123",
            "--safety-filter",
            mode,
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/inpaints"
        payload = json.loads(request.content)
        assert set(payload) == {"image", "mask", "prompt", "seed", "safety_filter"}
        assert payload["safety_filter"] == mode
        return httpx.Response(200, headers=wire["headers"], json=wire["body"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(args, InpaintAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["output"]["data_base64"])


@pytest.mark.parametrize(
    "bad", ["mask", "seed", "profile", "safety_outcome", "safety_request", "header", "geometry"]
)
def test_inpaint_rejects_contradictory_receipt(
    sample: tuple[Path, dict[str, Any]], bad: str
) -> None:
    source, wire = sample
    receipt = wire["body"]["data"]["receipt"]
    if bad == "mask":
        receipt["mask_image"]["sha256"] = "0" * 64
    elif bad == "seed":
        receipt["seed"] = 99
    elif bad == "profile":
        receipt["profile"] = "i2i-stable-diffusion-v1-5"
    elif bad == "safety_outcome":
        receipt["safety_filter"]["outcome"] = "not_run"
    elif bad == "safety_request":
        receipt["safety_filter"]["requested"] = "disabled"
    elif bad == "header":
        wire["headers"]["x-image-safety-filter-effective"] = "disabled"
    else:
        receipt["output_image"]["height"] = 256
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, headers=wire["headers"], json=wire["body"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        V4ApiClient(http, "https://api.invalid").inpaint(
            "dummy", input_path=source, mask_path=source, prompt="watercolor", seed=123
        )


def test_inpaint_dimension_mismatch_is_rejected_before_transport(
    sample: tuple[Path, dict[str, Any]],
) -> None:
    source, _ = sample
    mask = source.with_name("mask.png")
    Image.new("L", (256, 256)).save(mask)

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid dimensions must not reach transport")

    with (
        httpx.Client(transport=httpx.MockTransport(forbidden)) as http,
        pytest.raises(ApiError, match="dimensions"),
    ):
        V4ApiClient(http, "https://api.invalid").inpaint(
            "dummy", input_path=source, mask_path=mask, prompt="watercolor", seed=123
        )
