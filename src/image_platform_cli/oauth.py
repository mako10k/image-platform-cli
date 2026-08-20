import time
from collections.abc import Callable
from typing import Any

import httpx

from .errors import AuthenticationError
from .models import DeviceAuthorization, TokenSet

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class DeviceFlowClient:
    def __init__(self, http: httpx.Client, issuer: str, client_id: str) -> None:
        self._http = http
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id

    def authorize(self, scopes: tuple[str, ...]) -> DeviceAuthorization:
        try:
            response = self._http.post(
                f"{self._issuer}/oauth2/device_authorization",
                data={"client_id": self._client_id, "scope": " ".join(scopes)},
            )
            response.raise_for_status()
            body: Any = response.json()
            authorization = DeviceAuthorization(
                device_code=_required_string(body, "device_code"),
                user_code=_required_string(body, "user_code"),
                verification_uri=_required_https_url(body, "verification_uri"),
                verification_uri_complete=_required_https_url(body, "verification_uri_complete"),
                expires_in=_positive_int(body, "expires_in"),
                interval=_positive_int(body, "interval"),
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            raise AuthenticationError("device authorization failed") from error
        return authorization

    def poll(
        self,
        authorization: DeviceAuthorization,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> TokenSet:
        deadline = monotonic() + authorization.expires_in
        interval = float(authorization.interval)
        while monotonic() < deadline:
            sleep(interval)
            try:
                response = self._http.post(
                    f"{self._issuer}/oauth2/token",
                    data={
                        "client_id": self._client_id,
                        "grant_type": DEVICE_GRANT,
                        "device_code": authorization.device_code,
                    },
                )
            except httpx.HTTPError as error:
                raise AuthenticationError("token polling failed") from error
            body = _json_object(response)
            if response.is_success:
                try:
                    return TokenSet(
                        access_token=_required_string(body, "access_token"),
                        refresh_token=_required_string(body, "refresh_token"),
                    )
                except (ValueError, TypeError, KeyError) as error:
                    raise AuthenticationError("token response was malformed") from error
            oauth_error = body.get("error")
            if oauth_error == "authorization_pending":
                continue
            if oauth_error == "slow_down":
                interval += 5.0
                continue
            if oauth_error == "access_denied":
                raise AuthenticationError("authorization was denied")
            if oauth_error == "expired_token":
                raise AuthenticationError("device authorization expired")
            raise AuthenticationError("token endpoint rejected the request")
        raise AuthenticationError("device authorization expired")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as error:
        raise AuthenticationError("OAuth endpoint returned malformed JSON") from error
    if not isinstance(body, dict):
        raise AuthenticationError("OAuth endpoint returned malformed JSON")
    return body


def _required_string(body: Any, name: str) -> str:
    value = body[name]
    if not isinstance(value, str) or not value:
        raise ValueError(name)
    return value


def _required_https_url(body: Any, name: str) -> str:
    value = _required_string(body, name)
    if not value.startswith("https://"):
        raise ValueError(name)
    return value


def _positive_int(body: Any, name: str) -> int:
    value = body[name]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(name)
    return value
