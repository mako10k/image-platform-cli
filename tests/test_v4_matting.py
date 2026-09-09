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
def sample(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    wire = json.loads(
        (Path(__file__).parent / "fixtures/native-v4-portrait-matting.r8.json").read_text()
    )
    paths = [tmp_path / name for name in ("source.png", "person.png")]
    for path, key in zip(paths, ("image", "person_mask"), strict=True):
        path.write_bytes(base64.b64decode(wire["request"][key]["data_base64"]))
    return paths[0], paths[1], wire


class MattingAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes == frozenset({"images:edit"})
        return "dummy"


@pytest.mark.parametrize("radius", [0, 16, 64])
def test_matting_cli_saves_verified_output(
    sample: tuple[Path, Path, dict[str, Any]], radius: int
) -> None:
    source, mask, wire = sample
    output = source.with_name("matte.png")
    wire["body"]["data"]["receipt"]["uncertainty_radius"] = radius
    args = parser().parse_args(
        [
            "edit",
            "matte-portrait",
            "--input",
            str(source),
            "--person-mask",
            str(mask),
            "-o",
            str(output),
            *([] if radius == 16 else ["--uncertainty-radius", str(radius)]),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v4/portrait-mattings"
        assert json.loads(request.content) == {**wire["request"], "uncertainty_radius": radius}
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_edit(args, MattingAuth(), V4ApiClient(http, "https://api.invalid"))
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["output"]["data_base64"])
    with Image.open(output) as image:
        assert image.size == (8, 8) and image.mode == "RGBA"


@pytest.mark.parametrize(
    "bad",
    [
        "input",
        "mask",
        "output",
        "radius",
        "model",
        "bytes",
        "hash_header",
        "model_header",
        "cost_header",
        "revision",
        "unknown_field",
    ],
)
def test_matting_rejects_inconsistent_evidence_before_save(
    sample: tuple[Path, Path, dict[str, Any]], bad: str
) -> None:
    source, mask, wire = sample
    data = wire["body"]["data"]
    receipt = data["receipt"]
    if bad in {"input", "mask", "output"}:
        key = {"input": "input_image", "mask": "person_mask", "output": "output_image"}[bad]
        receipt[key]["width"] = 9
    elif bad == "radius":
        receipt["uncertainty_radius"] = 17
    elif bad == "model":
        receipt["model_revision"] = "wrong"
    elif bad == "bytes":
        data["output"]["data_base64"] = "not-base64"
    elif bad == "hash_header":
        wire["headers"]["x-image-sha256"] = "0" * 64
    elif bad == "model_header":
        wire["headers"]["x-image-model"] = "wrong"
    elif bad == "cost_header":
        wire["headers"]["x-image-compute-cost-usd"] = "99"
    elif bad == "revision":
        wire["headers"]["x-image-contract-revision"] = "old"
    else:
        receipt["unknown"] = True
    output = source.with_name("matte.png")
    args = parser().parse_args(
        [
            "edit",
            "matte-portrait",
            "--input",
            str(source),
            "--person-mask",
            str(mask),
            "-o",
            str(output),
        ]
    )
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
            )
        ) as http,
        pytest.raises(ApiError),
    ):
        run_edit(args, MattingAuth(), V4ApiClient(http, "https://api.invalid"))
    assert not output.exists()


@pytest.mark.parametrize("bad", ["negative", "over_limit", "bool", "dimensions"])
def test_matting_invalid_inputs_never_reach_http(
    sample: tuple[Path, Path, dict[str, Any]], bad: str
) -> None:
    source, mask, _ = sample
    radius = {"negative": -1, "over_limit": 65, "bool": True, "dimensions": 16}[bad]
    if bad == "dimensions":
        Image.new("L", (7, 8)).save(mask)

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid matting input reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.invalid").portrait_matting(
            "dummy", input_path=source, person_mask_path=mask, uncertainty_radius=radius
        )
