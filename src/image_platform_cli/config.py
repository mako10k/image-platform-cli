import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Config:
    issuer: str
    audience: str
    client_id: str
    organization_id: str
    api_base_url: str

    @classmethod
    def staging(cls) -> "Config":
        return cls(
            issuer=os.getenv(
                "IMAGE_PLATFORM_ISSUER", "https://daring-haven-18-staging.authkit.app"
            ).rstrip("/"),
            audience=os.getenv("IMAGE_PLATFORM_AUDIENCE", "client_01M0F65BD7G48KBFXZ2HT2NQFM"),
            client_id=os.getenv("IMAGE_PLATFORM_CLIENT_ID", "client_01M0FBDFJ78Q95AF1GB52HR8J5"),
            organization_id=os.getenv(
                "IMAGE_PLATFORM_ORGANIZATION_ID", "org_01M0F9R7CCGGMVKAA2G3Z93J0G"
            ),
            api_base_url=os.getenv(
                "IMAGE_PLATFORM_API_BASE_URL", "https://api-staging.image.mk10.org"
            ).rstrip("/"),
        )

    @property
    def credential_account(self) -> str:
        return f"{self.issuer}|{self.organization_id}"
