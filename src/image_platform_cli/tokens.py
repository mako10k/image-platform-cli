from typing import Any

import httpx
import jwt

from .errors import AuthenticationError
from .models import VerifiedToken


class TokenValidator:
    def __init__(self, http: httpx.Client, issuer: str, audience: str) -> None:
        self._http = http
        self._issuer = issuer.rstrip("/")
        self._audience = audience

    def validate(
        self,
        token: str,
        *,
        organization_id: str,
        required_scopes: frozenset[str],
    ) -> VerifiedToken:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise AuthenticationError("access token has no signing key identifier")
            response = self._http.get(f"{self._issuer}/oauth2/jwks")
            response.raise_for_status()
            jwks: Any = response.json()
            keys = jwks.get("keys") if isinstance(jwks, dict) else None
            if not isinstance(keys, list):
                raise AuthenticationError("JWKS response was malformed")
            matching = [key for key in keys if isinstance(key, dict) and key.get("kid") == kid]
            if len(matching) != 1:
                raise AuthenticationError("access token signing key was not found")
            signing_key = jwt.PyJWK.from_dict(matching[0]).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["iss", "aud", "sub", "org_id", "exp", "iat"]},
            )
        except AuthenticationError:
            raise
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, TypeError) as error:
            raise AuthenticationError("access token validation failed") from error

        subject = claims.get("sub")
        token_org = claims.get("org_id")
        if not isinstance(subject, str) or not subject.startswith("user_"):
            raise AuthenticationError("access token does not represent a user")
        if token_org != organization_id:
            raise AuthenticationError("access token organization mismatch")
        scopes = _scopes(claims.get("scope"))
        if not required_scopes.issubset(scopes):
            raise AuthenticationError("access token scope mismatch")
        expires_at = claims.get("exp")
        if not isinstance(expires_at, int):
            raise AuthenticationError("access token expiry was malformed")
        session_id = claims.get("sid")
        if session_id is not None and not isinstance(session_id, str):
            raise AuthenticationError("access token session was malformed")
        return VerifiedToken(subject, token_org, scopes, expires_at, session_id)


def _scopes(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(value.split())
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return frozenset(value)
    return frozenset()
