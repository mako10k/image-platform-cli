class CliError(Exception):
    """A safe user-facing error that contains no secret values."""


class AuthenticationError(CliError):
    """Authentication could not be completed safely."""


class CredentialStoreError(CliError):
    """The OS credential store is unavailable or failed."""


class ApiError(CliError):
    """The public image API failed or returned an invalid response."""
