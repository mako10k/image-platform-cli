class CliError(Exception):
    """A safe user-facing error that contains no secret values."""


class AuthenticationError(CliError):
    """Authentication could not be completed safely."""


class CredentialStoreError(CliError):
    """The OS credential store is unavailable or failed."""
