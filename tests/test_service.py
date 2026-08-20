from dataclasses import dataclass

import pytest

from image_platform_cli.config import Config
from image_platform_cli.errors import AuthenticationError
from image_platform_cli.models import (
    DeviceAuthorization,
    StoredCredential,
    TokenSet,
    VerifiedToken,
)
from image_platform_cli.service import AuthService


@dataclass
class FakeFlow:
    token_set: TokenSet

    def authorize(self, scopes: tuple[str, ...]) -> DeviceAuthorization:
        assert "offline_access" in scopes
        return DeviceAuthorization("device", "CODE", "https://verify", "https://complete", 60, 5)

    def poll(self, authorization: DeviceAuthorization) -> TokenSet:
        assert authorization.device_code == "device"
        return self.token_set

    def refresh(self, refresh_token: str, scopes: tuple[str, ...]) -> TokenSet:
        assert refresh_token
        assert scopes
        return self.token_set


@dataclass
class FakeValidator:
    result: VerifiedToken | None

    def validate(
        self,
        token: str,
        *,
        organization_id: str,
        required_scopes: frozenset[str],
    ) -> VerifiedToken:
        assert token == "access-secret"
        if self.result is None:
            raise AuthenticationError("access token validation failed")
        return self.result


class MemoryStore:
    def __init__(self) -> None:
        self.value: StoredCredential | None = None

    def load(self, account: str) -> StoredCredential | None:
        return self.value

    def save(self, account: str, credential: StoredCredential) -> None:
        self.value = credential

    def delete(self, account: str) -> bool:
        existed = self.value is not None
        self.value = None
        return existed


def config() -> Config:
    return Config("https://issuer", "audience", "client", "org_1", "https://api")


def test_login_saves_refresh_only_after_access_token_validation() -> None:
    store = MemoryStore()
    verified = VerifiedToken(
        "user_1", "org_1", frozenset({"images:generate"}), 2_000_000_000, "session_1"
    )
    service = AuthService(
        config(),
        FakeFlow(TokenSet("access-secret", "refresh-secret")),
        FakeValidator(verified),
        store,
    )
    announced: list[tuple[str, str]] = []
    credential = service.login(
        ("images:generate",), lambda code, uri: announced.append((code, uri))
    )

    assert store.value == credential
    assert credential.refresh_token == "refresh-secret"
    assert "access-secret" not in repr(credential)
    assert "refresh-secret" not in repr(credential)
    assert announced == [("CODE", "https://complete")]


def test_login_does_not_replace_existing_credential_on_validation_failure() -> None:
    old = StoredCredential("old-refresh", "user_old", "org_1", ("openid",))
    store = MemoryStore()
    store.value = old
    service = AuthService(
        config(), FakeFlow(TokenSet("access-secret", "new-refresh")), FakeValidator(None), store
    )

    with pytest.raises(AuthenticationError):
        service.login((), lambda _code, _uri: None)
    assert store.value == old


def test_logout_removes_local_credential() -> None:
    store = MemoryStore()
    store.value = StoredCredential("refresh", "user_1", "org_1", ())
    service = AuthService(
        config(), FakeFlow(TokenSet("access-secret", "refresh")), FakeValidator(None), store
    )
    assert service.logout() is True
    assert service.logout() is False


def test_refresh_rotation_occurs_only_after_new_access_token_validation() -> None:
    old = StoredCredential("old-refresh", "user_1", "org_1", ("images:generate",))
    store = MemoryStore()
    store.value = old
    verified = VerifiedToken(
        "user_1", "org_1", frozenset({"images:generate"}), 2_000_000_000, "session_1"
    )
    service = AuthService(
        config(), FakeFlow(TokenSet("access-secret", "new-refresh")), FakeValidator(verified), store
    )

    assert service.access_token(frozenset({"images:generate"})) == "access-secret"
    assert store.value is not None
    assert store.value.refresh_token == "new-refresh"


def test_failed_refreshed_token_validation_preserves_old_refresh_token() -> None:
    old = StoredCredential("old-refresh", "user_1", "org_1", ("images:generate",))
    store = MemoryStore()
    store.value = old
    service = AuthService(
        config(), FakeFlow(TokenSet("access-secret", "new-refresh")), FakeValidator(None), store
    )

    with pytest.raises(AuthenticationError):
        service.access_token(frozenset({"images:generate"}))
    assert store.value == old
