from collections.abc import Callable

from .config import Config
from .credentials import CredentialStore
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
        self._store.save(self._config.credential_account, credential)
        return credential

    def status(self) -> StoredCredential | None:
        return self._store.load(self._config.credential_account)

    def logout(self) -> bool:
        return self._store.delete(self._config.credential_account)
