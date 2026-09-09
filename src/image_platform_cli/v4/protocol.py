"""Pinned r8 route status, header and error contracts (see route-contract provenance)."""

import json
import re
from importlib.resources import files
from typing import Any

import httpx
from jsonschema import Draft202012Validator, ValidationError

from ..common.errors import ApiError

ROUTES: list[dict[str, Any]] = json.loads(
    files("image_platform_cli.v4").joinpath("route_contracts.json").read_text(encoding="utf-8")
)
MANAGED_HEADERS = frozenset(
    {"location", "retry-after", "www-authenticate", "allow", "idempotent-replay"}
)


def route_contract(method: str, path: str) -> dict[str, Any]:
    for route in ROUTES:
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(route["path"]))
        if route["method"] == method and re.fullmatch(pattern, path):
            return route
    raise ApiError("request does not match an accepted Native API V4 route")


def verify_response(response: httpx.Response, body: dict[str, Any], route: dict[str, Any]) -> None:
    expected = {"data", "meta"} if response.is_success else {"error", "meta"}
    if set(body) != expected:
        raise ApiError("image API returned a malformed closed V4 envelope")
    if response.is_success:
        selected = route["statuses"].get(str(response.status_code))
        if selected is None:
            raise ApiError("image API returned an unexpected success status")
        try:
            Draft202012Validator(selected["schema"]).validate(body["data"])
        except ValidationError as error:
            raise ApiError(
                "image API returned data outside the accepted response schema"
            ) from error
        required, optional = set(selected["required"]), set(selected["optional"])
    else:
        required = _verify_error(response, body["error"], route)
        optional = set()
    actual = {
        key for key in response.headers if key in MANAGED_HEADERS or key.startswith("x-image-")
    }
    if not required <= actual or actual - required - optional:
        raise ApiError("image API returned unexpected or missing contract headers")
    for key in required | (optional & actual):
        if len(response.headers.get_list(key)) != 1 or not response.headers[key]:
            raise ApiError("image API returned invalid contract headers")
    if "idempotent-replay" in required and response.headers["idempotent-replay"] not in {
        "true",
        "false",
    }:
        raise ApiError("image API returned invalid idempotency receipt")


def _verify_error(response: httpx.Response, error: object, route: dict[str, Any]) -> set[str]:
    if not isinstance(error, dict) or set(error) not in (
        {"code", "message", "retryable"},
        {"code", "message", "retryable", "param"},
    ):
        raise ApiError("image API returned a malformed public error")
    code = error.get("code")
    outcome = route["outcomes"].get(code) if isinstance(code, str) else None
    if outcome is None or (
        response.status_code != outcome["status_code"]
        or error["message"] != outcome["message"]
        or not isinstance(error["retryable"], bool)
        or error["retryable"] != outcome["retryable"]
    ):
        raise ApiError("image API returned an unrecognized public error")
    if "param" in error and (
        not outcome["param_allowed"]
        or not isinstance(error["param"], str)
        or re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", error["param"]) is None
    ):
        raise ApiError("image API returned an invalid public error location")
    if code in {"invalid_token", "insufficient_scope"}:
        challenge = f'Bearer error="{code}"'
        if code == "insufficient_scope":
            challenge += ', scope="' + " ".join(route["scopes"]) + '"'
        if response.headers.get("www-authenticate") != challenge:
            raise ApiError("image API returned an invalid authentication challenge")
    if code == "job_dispatch_unavailable" and response.headers.get("retry-after") != "1":
        raise ApiError("image API returned an invalid dispatcher retry receipt")
    return set(outcome["header_names"])
