from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DeviceAuthorization:
    device_code: str = field(repr=False)
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass(frozen=True, slots=True)
class TokenSet:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedToken:
    subject: str
    organization_id: str
    scopes: frozenset[str]
    expires_at: int
    session_id: str | None


@dataclass(frozen=True, slots=True)
class StoredCredential:
    refresh_token: str = field(repr=False)
    subject: str
    organization_id: str
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    data: bytes = field(repr=False)
    mime_type: str
    sha256: str
    width: int
    height: int
    seed: int
    measured_compute_cost_usd: Decimal | None = None
    model_id: str | None = None
    model_revision: str | None = None
    safety_filter_requested: str | None = None
    safety_filter_effective: str | None = None
    safety_filter_outcome: str | None = None


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    source_data: bytes = field(repr=False)
    mask_data: bytes = field(repr=False)
    mask_sha256: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class DeterministicEditResult:
    data: bytes = field(repr=False)
    mime_type: str
    sha256: str
    width: int
    height: int
    program_sha256: str
