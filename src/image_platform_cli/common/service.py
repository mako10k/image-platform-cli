from collections.abc import Callable

from .config import Config
from .credentials import CredentialStore
from .errors import AuthenticationError
from .models import StoredCredential
from .oauth import DeviceFlowClient
from .tokens import TokenValidator

IDENTITY_SCOPES = ("openid", "profile", "email", "offline_access")


class AuthService:
    def __init__(
        self,
        config: Config,
        flow: DeviceFlowClient,
        validator: TokenValidator,
        store: CredentialStore,
    ) -> None:
        self._config = config
        self._flow = flow
        self._validator = validator
        self._store = store

    def login(
        self,
        image_scopes: tuple[str, ...],
        announce: Callable[[str, str], None],
    ) -> StoredCredential:
        scopes = tuple(dict.fromkeys((*IDENTITY_SCOPES, *image_scopes)))
        authorization = self._flow.authorize(scopes)
        announce(authorization.user_code, authorization.verification_uri_complete)
        tokens = self._flow.poll(authorization)
        verified = self._validator.validate(
            tokens.access_token,
            organization_id=self._config.organization_id,
            required_scopes=frozenset(image_scopes),
        )
        credential = StoredCredential(
            refresh_token=tokens.refresh_token,
            subject=verified.subject,
            organization_id=verified.organization_id,
            scopes=tuple(sorted(verified.scopes)),
        )
        account = self._config.credential_account(verified.subject)
        self._store.save(account, credential)
        self._store.select_account(self._config.credential_selector_account, account)
        return credential

    def status(self) -> StoredCredential | None:
        account = self._store.selected_account(self._config.credential_selector_account)
        if account is None:
            return None
        credential = self._store.load(account)
        if credential is None:
            return None
        self._validate_selected_credential(account, credential)
        return credential

    def logout(self) -> bool:
        selector = self._config.credential_selector_account
        account = self._store.selected_account(selector)
        if account is None:
            return False
        deleted = self._store.delete(account)
        self._store.clear_selection(selector)
        return deleted

    def access_token(self, required_scopes: frozenset[str]) -> str:
        account = self._store.selected_account(self._config.credential_selector_account)
        if account is None:
            raise AuthenticationError("not logged in")
        current = self._store.load(account)
        if current is None:
            raise AuthenticationError("not logged in")
        self._validate_selected_credential(account, current)
        tokens = self._flow.refresh(current.refresh_token, current.scopes)
        verified = self._validator.validate(
            tokens.access_token,
            organization_id=self._config.organization_id,
            required_scopes=required_scopes,
        )
        if verified.subject != current.subject:
            raise AuthenticationError("refreshed token subject does not match stored credential")
        replacement = StoredCredential(
            refresh_token=tokens.refresh_token,
            subject=verified.subject,
            organization_id=verified.organization_id,
            scopes=tuple(sorted(verified.scopes)),
        )
        self._store.save(account, replacement)
        return tokens.access_token

    def _validate_selected_credential(self, account: str, credential: StoredCredential) -> None:
        if (
            credential.organization_id != self._config.organization_id
            or account != self._config.credential_account(credential.subject)
        ):
            raise AuthenticationError("selected credential identity is invalid")
