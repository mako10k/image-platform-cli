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
```

`login` performs the WorkOS Device Authorization Flow. It will fail closed when the platform has
no usable OS credential-store backend. Live login remains separately gated.

