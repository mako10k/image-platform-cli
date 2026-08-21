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
image prompt optimize "a blue ceramic cup" [--width 1024] [--height 1024]
```

`login` performs the WorkOS Device Authorization Flow. It will fail closed when the platform has
no usable OS credential-store backend. Its default application scopes are `images:generate`,
`campaigns:read`, `artifacts:read`, and `batches:plan`.

`prompt optimize` sends only the user's query and optional bounded dimensions to the native
`POST /v1/prompt-plans` endpoint and prints only the optimized prompt. The server owns the planning
prompt, output schema, validation, and the replaceable provider call to `POST /v1/chat/completions`;
the CLI never calls that provider-compatible endpoint directly.

`generate` refreshes the session, validates the new access token, and submits one idempotent native
generation Job. It waits up to 30 seconds by default, automatically polls any HTTP 202 response,
retrieves the completed Artifact through its short-lived signed URL, verifies its SHA-256, byte
count, MIME type, and PNG dimensions, then creates the output without overwriting an existing file.
When `--seed N` is omitted, the CLI selects a fresh random non-zero 63-bit seed for that Job and
prints the effective seed with the result. An explicitly supplied seed, including zero, is preserved.
The OAuth token is sent only to the configured API origin and never to the signed Artifact URL.
`--wait 0` begins polling immediately. Waits from 61 through 120 seconds additionally require
`--allow-long-wait`; the CLI intentionally has no option that disables polling. Live login and
generation remain separately gated.
