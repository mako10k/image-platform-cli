# image-platform CLI

Independent command-line client for the image platform.

The repository contains the accepted authentication contract and a locally tested initial
authentication CLI. No WorkOS setting change, invitation, live request, or credential has been
created here.

See [`docs/auth-contract.md`](docs/auth-contract.md).

## Development

```bash
uv sync --all-groups
uv run ruff check .
uv run mypy
uv run pytest -q
```

The initial command surface is:

```text
image auth login [--scope SCOPE]...
image auth status
image auth logout
image generate "a blue ceramic cup" --output cup.png [--width 1024] [--height 1024]
```

`login` performs the WorkOS Device Authorization Flow. It will fail closed when the platform has
no usable OS credential-store backend. Its default application scope is `images:generate`.
`generate` refreshes the session, validates the new access token, calls the native
`POST /v1/generations` endpoint, verifies the inline PNG digest and dimensions, and creates the
output without overwriting an existing file. Live login and generation remain separately gated.
