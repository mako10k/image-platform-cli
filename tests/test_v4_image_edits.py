import base64
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.edit_cli import run_edit
from image_platform_cli.v4.image_edits import ImageToImageOptions
from image_platform_cli.v4.protocol import route_contract, verify_response

FIXTURE = Path(__file__).parent / "fixtures/native-v4-image-receipts.r8.json"
OPTIONS = ImageToImageOptions(
    "watercolor",
    123,
    negative_prompt="blur",
    strength=Decimal("0.6"),
    guidance_scale=Decimal(6),
    inference_steps=20,
)


@pytest.fixture
def wire() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def input_file(tmp_path: Path, wire: dict[str, Any]) -> Path:
    path = tmp_path / "source.png"
    path.write_bytes(base64.b64decode(wire["request"]["input"]["data_base64"]))
    return path


def test_real_api_fixture_is_accepted_with_all_i2i_controls(
    tmp_path: Path, wire: dict[str, Any]
) -> None:
    source = input_file(tmp_path, wire)

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/image-edits"
        payload = json.loads(request.content)
        assert payload == {
            **wire["request"],
            "width": 512,
            "height": 512,
            "profile": OPTIONS.profile,
        }
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        result = V4ApiClient(http, "https://image.invalid").image_to_image(
            "token", input_path=source, options=OPTIONS
        )
    assert result.data == base64.b64decode(wire["body"]["data"]["output"]["data_base64"])
    assert result.seed == 123
    assert result.width == result.height == 512


@pytest.mark.parametrize(
    "change",
    [
        "r7",
        "receipt_type",
        "missing_controls",
        "strength",
        "seed",
        "source",
        "output",
        "implementation",
        "header",
        "bytes",
    ],
)
def test_invalid_reply_never_saves_an_image(
    tmp_path: Path, wire: dict[str, Any], change: str
) -> None:
    source = input_file(tmp_path, wire)
    receipt = wire["body"]["data"]["receipt"]
    if change == "r7":
        wire["body"]["meta"]["contract_revision"] = "2026-09-07-r7"
    elif change == "receipt_type":
        wire["body"]["data"]["receipt"] = wire["inpaint"]["body"]["data"]["receipt"]
    elif change == "missing_controls":
        receipt.pop("controls")
    elif change == "strength":
        receipt["controls"]["strength"] = "0.9"
    elif change == "seed":
        receipt["seed"] = 124
    elif change == "source":
        receipt["input_image"]["sha256"] = "a" * 64
    elif change == "output":
        receipt["output_image"]["width"] = 256
    elif change == "implementation":
        receipt["implementation_revision"] = ""
    elif change == "header":
        wire["headers"]["x-image-model"] = "wrong"
    else:
        wire["body"]["data"]["output"]["data_base64"] = "invalid!"
    args = parser().parse_args(
        [
            "edit",
            "i2i",
            "watercolor",
            "--input",
            str(source),
            "-o",
            str(tmp_path / "out.png"),
            "--seed",
            "123",
            "--negative-prompt",
            "blur",
            "--strength",
            "0.6",
            "--guidance-scale",
            "6",
            "--steps",
            "20",
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
        run_edit(args, LocalAuth(), V4ApiClient(http, "https://image.invalid"))
    assert not args.output.exists()


class LocalAuth:
    def access_token(self, scopes: frozenset[str]) -> str:
        assert scopes >= {"images:edit"}
        return "token"


def test_inpaint_schema_still_accepts_its_own_receipt(wire: dict[str, Any]) -> None:
    sample = wire["inpaint"]
    verify_response(
        httpx.Response(200, json=sample["body"], headers=sample["headers"]),
        sample["body"],
        route_contract("POST", "/v4/inpaints"),
    )


def test_artifact_source_uses_v4_metadata_then_image_edit(
    tmp_path: Path, wire: dict[str, Any]
) -> None:
    from test_v4_api import ARTIFACT_ID, artifact_descriptor, artifact_metadata, response

    source = input_file(tmp_path, wire)
    metadata = artifact_metadata(
        descriptor=artifact_descriptor(
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            size_bytes=source.stat().st_size,
            width=512,
            height=512,
        )
    )
    paths = []

    def handle(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.method == "GET":
            return response(metadata)
        assert json.loads(request.content)["artifact_id"] == ARTIFACT_ID
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        result = V4ApiClient(http, "https://image.invalid").image_to_image(
            "token", artifact_id=ARTIFACT_ID, options=OPTIONS
        )
    assert result.width == 512
    assert paths == [f"/v4/artifacts/{ARTIFACT_ID}", "/v4/image-edits"]


@pytest.mark.parametrize(
    "field,value",
    [("strength", Decimal("NaN")), ("width", 0), ("profile", "unknown"), ("inference_steps", 1)],
)
def test_invalid_controls_rejected_before_request(
    tmp_path: Path, wire: dict[str, Any], field: str, value: Any
) -> None:
    source = input_file(tmp_path, wire)

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid controls must not send a request")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://image.invalid").image_to_image(
            "token", input_path=source, options=replace(OPTIONS, **{field: value})
        )


@pytest.mark.parametrize("capture", [False, True])
def test_edit_command_saves_only_verified_output(
    tmp_path: Path, wire: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capture: bool
) -> None:
    from test_v4_api import ARTIFACT_ID, artifact_descriptor, artifact_metadata, response

    source = input_file(tmp_path, wire)
    output = tmp_path / "result.png"
    argv = [
        "edit",
        "image-to-image",
        "watercolor",
        "--input",
        str(source),
        "-o",
        str(output),
        "--seed",
        "123",
        "--negative-prompt",
        "blur",
        "--strength",
        "0.6",
        "--guidance-scale",
        "6",
        "--steps",
        "20",
    ]
    if capture:
        argv += ["--capture-input", "--capture-namespace", "capture"]
    events = []
    scopes_seen = []

    class Auth:
        def access_token(self, scopes: frozenset[str]) -> str:
            scopes_seen.append(scopes)
            return "token"

    def handle(request: httpx.Request) -> httpx.Response:
        events.append(request.method)
        if request.method == "GET":
            descriptor = artifact_descriptor(width=512, height=512)
            descriptor.update(wire["body"]["data"]["receipt"]["input_image"])
            return response(artifact_metadata(descriptor=descriptor))
        payload = json.loads(request.content)
        assert ("artifact_id" in payload) is capture
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    def upload(token: str, path: Path, *, namespace: str, kind: str) -> dict[str, str]:
        assert (path, namespace, kind) == (source, "capture", "image")
        events.append("upload")
        return {"artifact_id": ARTIFACT_ID}

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        api = V4ApiClient(http, "https://image.invalid")
        monkeypatch.setattr(api, "upload_artifact", upload)
        run_edit(parser().parse_args(argv), Auth(), api)
    assert events == (["upload", "GET", "POST"] if capture else ["POST"])
    assert scopes_seen == [
        frozenset(
            {"images:edit", "artifacts:read", "artifacts:write"} if capture else {"images:edit"}
        )
    ]
    assert output.read_bytes() == base64.b64decode(wire["body"]["data"]["output"]["data_base64"])
