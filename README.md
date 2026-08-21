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
  [--wait 0..120] [--allow-long-wait]
```

`login` performs the WorkOS Device Authorization Flow. It will fail closed when the platform has
no usable OS credential-store backend. Its default application scopes are `images:generate`,
`campaigns:read`, and `artifacts:read`.

`generate` refreshes the session, validates the new access token, and submits one idempotent native
generation Job. It waits up to 30 seconds by default, automatically polls any HTTP 202 response,
retrieves the completed Artifact through its short-lived signed URL, verifies its SHA-256, byte
count, MIME type, and PNG dimensions, then creates the output without overwriting an existing file.
The OAuth token is sent only to the configured API origin and never to the signed Artifact URL.
`--wait 0` begins polling immediately. Waits from 61 through 120 seconds additionally require
`--allow-long-wait`; the CLI intentionally has no option that disables polling. Live login and
generation remain separately gated.
