from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from image_platform_cli.errors import AuthenticationError
from image_platform_cli.tokens import TokenValidator

ISSUER = "https://issuer.example"
AUDIENCE = "api-audience"
ORGANIZATION = "org_expected"


def fixture() -> tuple[TokenValidator, httpx.Client, rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = "key-1"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{ISSUER}/oauth2/jwks"
        return httpx.Response(200, json={"keys": [jwk]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user_123",
        "org_id": ORGANIZATION,
        "scope": "openid images:generate",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "sid": "session_123",
    }
    return TokenValidator(http, ISSUER, AUDIENCE), http, private_key, claims


def encode(private_key: rsa.RSAPrivateKey, claims: dict[str, Any]) -> str:
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "key-1"})


def test_valid_user_token_is_accepted() -> None:
    validator, http, key, claims = fixture()
    try:
        result = validator.validate(
            encode(key, claims),
            organization_id=ORGANIZATION,
            required_scopes=frozenset({"images:generate"}),
        )
    finally:
        http.close()
    assert result.subject == "user_123"
    assert result.organization_id == ORGANIZATION
    assert result.session_id == "session_123"


@pytest.mark.parametrize(
    ("claim", "value", "message"),
    [
        ("aud", "wrong", "validation failed"),
        ("iss", "https://wrong.example", "validation failed"),
        ("sub", "client_m2m", "does not represent a user"),
        ("org_id", "org_wrong", "organization mismatch"),
        ("scope", "openid", "scope mismatch"),
    ],
)
def test_token_claim_mismatches_fail_closed(claim: str, value: str, message: str) -> None:
    validator, http, key, claims = fixture()
    claims[claim] = value
    try:
        with pytest.raises(AuthenticationError, match=message):
            validator.validate(
                encode(key, claims),
                organization_id=ORGANIZATION,
                required_scopes=frozenset({"images:generate"}),
            )
    finally:
        http.close()
