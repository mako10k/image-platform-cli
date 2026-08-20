from collections.abc import Iterator

import httpx
import pytest

from image_platform_cli.errors import AuthenticationError
from image_platform_cli.oauth import DeviceFlowClient


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def client(responses: Iterator[httpx.Response]) -> tuple[DeviceFlowClient, httpx.Client]:
    def handler(request: httpx.Request) -> httpx.Response:
        response = next(responses)
        response.request = request
        return response

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return DeviceFlowClient(http, "https://issuer.example", "public-client"), http


def authorization_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "device_code": "device-secret",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://issuer.example/device",
            "verification_uri_complete": "https://issuer.example/device?user_code=ABCD-EFGH",
            "expires_in": 60,
            "interval": 2,
        },
    )


def test_device_flow_handles_pending_and_slow_down_without_disclosing_codes() -> None:
    flow, http = client(
        iter(
            [
                authorization_response(),
                httpx.Response(400, json={"error": "authorization_pending"}),
                httpx.Response(400, json={"error": "slow_down"}),
                httpx.Response(
                    200,
                    json={"access_token": "access-secret", "refresh_token": "refresh-secret"},
                ),
            ]
        )
    )
    clock = Clock()
    try:
        authorization = flow.authorize(("openid", "images:generate"))
        tokens = flow.poll(
            authorization,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
    finally:
        http.close()

    assert tokens.access_token == "access-secret"
    assert tokens.refresh_token == "refresh-secret"
    assert clock.now == 11


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(400, json={"error": "access_denied"}), "authorization was denied"),
        (httpx.Response(400, json={"error": "expired_token"}), "device authorization expired"),
        (httpx.Response(500, json={"error": "server_error"}), "token endpoint rejected"),
    ],
)
def test_device_flow_fails_closed_for_terminal_errors(
    response: httpx.Response, message: str
) -> None:
    flow, http = client(iter([authorization_response(), response]))
    clock = Clock()
    try:
        authorization = flow.authorize(("openid",))
        with pytest.raises(AuthenticationError, match=message):
            flow.poll(authorization, monotonic=clock.monotonic, sleep=clock.sleep)
    finally:
        http.close()


def test_device_authorization_rejects_non_https_verification_uri() -> None:
    response = authorization_response()
    body = response.json()
    body["verification_uri"] = "http://issuer.example/device"
    flow, http = client(iter([httpx.Response(200, json=body)]))
    try:
        with pytest.raises(AuthenticationError, match="device authorization failed"):
            flow.authorize(("openid",))
    finally:
        http.close()
