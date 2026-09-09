import json
from dataclasses import asdict
from typing import Protocol

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, NoKeyringError

from .errors import CredentialStoreError
from .models import StoredCredential

SERVICE = "image-platform"
SELECTOR_SERVICE = "image-platform-selection"


class CredentialStore(Protocol):
    def load(self, account: str) -> StoredCredential | None: ...
    def save(self, account: str, credential: StoredCredential) -> None: ...
    def delete(self, account: str) -> bool: ...
    def selected_account(self, selector: str) -> str | None: ...
    def select_account(self, selector: str, account: str) -> None: ...
    def clear_selection(self, selector: str) -> None: ...


class KeyringCredentialStore:
    def __init__(self, backend: KeyringBackend | None = None) -> None:
        self._backend = backend or keyring.get_keyring()
        if self._backend.priority <= 0:
            raise CredentialStoreError("no usable OS credential store is available")

    def load(self, account: str) -> StoredCredential | None:
        try:
            payload = self._backend.get_password(SERVICE, account)
        except (KeyringError, NoKeyringError) as error:
            raise CredentialStoreError("OS credential store read failed") from error
        if payload is None:
            return None
        try:
            body = json.loads(payload)
            return StoredCredential(
                refresh_token=_required_string(body, "refresh_token"),
                subject=_required_string(body, "subject"),
                organization_id=_required_string(body, "organization_id"),
                scopes=tuple(_required_string_list(body, "scopes")),
            )
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
            raise CredentialStoreError("stored credential is malformed") from error

    def save(self, account: str, credential: StoredCredential) -> None:
        payload = json.dumps(asdict(credential), separators=(",", ":"), sort_keys=True)
        try:
            self._backend.set_password(SERVICE, account, payload)
        except (KeyringError, NoKeyringError) as error:
            raise CredentialStoreError("OS credential store write failed") from error

    def delete(self, account: str) -> bool:
        if self.load(account) is None:
            return False
        try:
            self._backend.delete_password(SERVICE, account)
        except (KeyringError, NoKeyringError) as error:
            raise CredentialStoreError("OS credential store delete failed") from error
        return True

    def selected_account(self, selector: str) -> str | None:
        try:
            return self._backend.get_password(SELECTOR_SERVICE, selector)
        except (KeyringError, NoKeyringError) as error:
            raise CredentialStoreError("credential selection read failed") from error

    def select_account(self, selector: str, account: str) -> None:
        try:
            self._backend.set_password(SELECTOR_SERVICE, selector, account)
        except (KeyringError, NoKeyringError) as error:
            raise CredentialStoreError("credential selection write failed") from error

    def clear_selection(self, selector: str) -> None:
        if self.selected_account(selector) is None:
            return
        try:
            self._backend.delete_password(SELECTOR_SERVICE, selector)
        except (KeyringError, NoKeyringError) as error:
            raise CredentialStoreError("credential selection delete failed") from error


def _required_string(body: object, name: str) -> str:
    if not isinstance(body, dict):
        raise TypeError("credential")
    value = body[name]
    if not isinstance(value, str) or not value:
        raise ValueError(name)
    return value


def _required_string_list(body: object, name: str) -> list[str]:
    if not isinstance(body, dict):
        raise TypeError("credential")
    value = body[name]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(name)
    return value
