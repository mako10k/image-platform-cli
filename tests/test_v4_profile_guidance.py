import copy
import json
from typing import Any

import httpx
import pytest

from image_platform_cli.common.errors import ApiError, CliError
from image_platform_cli.v4 import cli
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.profile_guidance import show_profiles

RID = "req_0123456789abcdef0123456789abcdef"
TEXT = "用途の説明\n\n自由な段落を追加。\n# この行もそのまま表示\n"


def usage() -> dict[str, Any]:
    return {
        "schema_id": "model-profile-usage.v1",
        "registry_revision": "models-r1",
        "guidance_revision": "text-r1",
        "items": [
            {
                "id": "example-profile",
                "operation": "edit",
                "model_semantics": "platform-profile",
                "availability_domain": "platform_only",
                "bindings": [],
                "guidance": {"language": "ja", "content": TEXT},
            }
        ],
    }


def response(data: object) -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "X-Request-ID": RID,
        },
        json={
            "data": data,
            "meta": {
                "request_id": RID,
                "api_version": "4",
                "contract_revision": "2026-09-09-r8",
            },
        },
    )


def test_usage_transport_accepts_new_prose_and_additive_metadata() -> None:
    data = usage()
    data["future_note"] = "new metadata"
    data["items"][0]["guidance"]["future_note"] = "new metadata"
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response(data)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = V4ApiClient(http, "https://example.test").model_profiles("token", details=True)
    assert result == data
    assert len(requests) == 1
    assert str(requests[0].url) == "https://example.test/v4/model-profiles?view=usage"


@pytest.mark.parametrize("as_json", [True, False])
def test_cli_fetches_filters_and_preserves_text(
    monkeypatch: Any, capsys: Any, as_json: bool
) -> None:
    data = usage()
    second = copy.deepcopy(data["items"][0])
    second["id"] = "other-profile"
    data["items"].append(second)
    calls = []

    class Service:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def access_token(self, scopes: frozenset[str]) -> str:
            assert scopes == frozenset()
            return "token"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response(data)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(cli, "AuthService", Service)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: http)
    args = ["model-profiles", "--profile", "example-profile", "--details"]
    assert cli.main(args + (["--json"] if as_json else [])) == 0
    out = capsys.readouterr().out
    if as_json:
        result = json.loads(out)
        assert len(result["items"]) == 1
        assert result["items"][0]["guidance"]["content"] == TEXT
    else:
        assert out == "example-profile (ja, text-r1)\n" + TEXT
    assert len(calls) == 1


@pytest.mark.parametrize("case", ["old", "future"])
def test_unsupported_guidance_is_explicit(case: str) -> None:
    data = usage()
    if case == "old":
        data = {"revision": "r1", "items": []}
    else:
        data["schema_id"] = "model-profile-usage.v9"
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response(data))) as http,
        pytest.raises(ApiError, match="support"),
    ):
        V4ApiClient(http, "https://example.test").model_profiles("token", details=True)


def test_summary_request_does_not_opt_in() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.url.query
        return response({"revision": "r1", "items": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert V4ApiClient(http, "https://example.test").model_profiles("token") == {
            "revision": "r1",
            "items": [],
        }


def test_missing_and_unknown_profiles_are_not_success() -> None:
    data = usage()
    with pytest.raises(CliError, match="unknown profile"):
        show_profiles(data, profile_id="typo", details=True, as_json=True)
    data["items"][0]["guidance"] = None
    with pytest.raises(CliError, match="unavailable"):
        show_profiles(data, profile_id=None, details=True, as_json=False)


def test_offline_help_reaches_usage_without_http(monkeypatch: Any, capsys: Any) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("offline help tried network access")

    monkeypatch.setattr(httpx, "Client", forbidden)
    for args, expected in [
        (["help", "model-profiles"], "image help model-profiles usage"),
        (["help", "model-profiles", "usage"], "--details"),
        (
            ["help", "job", "submit", "ip-adapter-plus"],
            "--profile i2i-ip-adapter-plus-sd15 --details",
        ),
        (["help", "edit", "image-to-image"], "--profile i2i-stable-diffusion-v1-5 --details"),
    ]:
        assert cli.main(args) == 0
        assert expected in capsys.readouterr().out
