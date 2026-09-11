import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from test_v4_api import png_bytes

from image_platform_cli.common.errors import ApiError, CliError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import parser
from image_platform_cli.v4.edit_cli import load_json_object, run_edit


@pytest.mark.parametrize(
    ("command", "method"),
    [("plan", "plan_image_operations"), ("batch", "run_image_operation_batch")],
)
def test_operation_contract_command_forwards_complete_json_object(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str, method: str
) -> None:
    request = {"program": {"revision": "deterministic-edit-v1"}, "inputs": {}}
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    args = parser().parse_args(["edit", command, "--request", str(request_path)])
    auth, api = Mock(), Mock()
    auth.access_token.return_value = "token"
    getattr(api, method).return_value = {"kind": command}

    run_edit(args, auth, api)

    getattr(api, method).assert_called_once_with("token", request=request)
    auth.access_token.assert_called_once_with(frozenset({"images:edit"}))
    assert json.loads(capsys.readouterr().out) == {"kind": command}


@pytest.mark.parametrize("value", ["[]", "null", '"text"', "invalid"])
def test_operation_contract_request_requires_one_json_object(tmp_path: Path, value: str) -> None:
    path = tmp_path / "request.json"
    path.write_text(value, encoding="utf-8")
    with pytest.raises(CliError):
        load_json_object(path)


def test_operation_plan_verifies_receipt_headers() -> None:
    logical, physical = "a" * 64, "b" * 64
    response = httpx.Response(
        200,
        headers={
            "X-Image-Logical-Program-SHA256": logical,
            "X-Image-Physical-Graph-SHA256": physical,
        },
    )
    data = {
        "pipeline": {},
        "receipt": {
            "logical_program_sha256": logical,
            "physical_graph_sha256": physical,
        },
    }
    api = V4ApiClient(Mock(), "https://api.invalid")
    api._exchange = Mock(return_value=(response, {"data": data}))  # type: ignore[method-assign]

    assert api.plan_image_operations("token", request={"input": 1}) == data
    api._exchange.assert_called_once_with(  # type: ignore[attr-defined]
        "POST", "/v4/image-operation-plans", "token", json={"input": 1}
    )


def test_operation_batch_verifies_header_and_inline_image() -> None:
    raw = png_bytes(2, 2)
    digest = hashlib.sha256(raw).hexdigest()
    data = {
        "status": "completed",
        "items": [
            {
                "id": "first",
                "status": "succeeded",
                "image": {
                    "mime_type": "image/png",
                    "sha256": digest,
                    "size_bytes": len(raw),
                    "width": 2,
                    "height": 2,
                },
                "data_base64": base64.b64encode(raw).decode("ascii"),
                "receipt": {},
            }
        ],
        "receipt": {"batch_sha256": "c" * 64},
        "estimated_cost_usd": "0",
        "actual_cost_usd": "0",
    }
    api = V4ApiClient(Mock(), "https://api.invalid")
    api._exchange = Mock(  # type: ignore[method-assign]
        return_value=(
            httpx.Response(200, headers={"X-Image-Batch-SHA256": "c" * 64}),
            {"data": data},
        )
    )

    assert api.run_image_operation_batch("token", request={"items": []}) == data

    data["items"][0]["data_base64"] = "invalid"
    with pytest.raises(ApiError):
        api.run_image_operation_batch("token", request={"items": []})
