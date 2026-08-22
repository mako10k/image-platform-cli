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
image prompt optimize "a blue ceramic cup" [--width 1024] [--height 1024] [--seed N]
```

`login` performs the WorkOS Device Authorization Flow. It will fail closed when the platform has
no usable OS credential-store backend. Its default application scopes are `images:generate`,
`campaigns:read`, `artifacts:read`, and `batches:plan`.

`prompt optimize` sends only the user's query and optional bounded dimensions to the native
`POST /v1/prompt-plans` endpoint and prints only the optimized prompt. The server owns the planning
prompt, output schema, validation, and the replaceable provider call to `POST /v1/chat/completions`;
the CLI never calls that provider-compatible endpoint directly. `--seed N` makes both prompt
variation and a later generation with the same seed reproducible; omitting it selects a fresh
random seed while keeping stdout limited to the optimized prompt.

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

## Editing semantics and receipts

`image edit image-to-image` (`i2i`) uses descriptive Stable Diffusion 1.5 image-to-image. Its
prompt describes the desired final image; it is not an instruction such as “remove the person”.
Instruction editing is a separate platform capability backed by the `edit-flux2-klein-4b` profile.
The I2I command keeps its existing strength `0.75`, guidance `7.5`, and 25-step defaults.

Synchronous I2I and explicit-mask inpaint print the verified output SHA-256, effective seed,
backend model and revision, and the server-provided measured compute cost. This cost is a measured
estimate from the platform receipt, not a finalized cloud invoice. Inpaint retains the current
contract: white mask pixels are repainted, black pixels are preserved, and `grow_mask=0`.

Inpaint also accepts `--safety-filter default|enabled|disabled`. Non-default modes succeed only
when the authenticated server explicitly permits per-request control. The CLI verifies and prints
the server-reported requested mode, effective mode, and outcome so equal-seed smoke comparisons can
be measured. Servers remain filter-on and control-denied by default.

`image edit run --program edit.json --input scene=scene.png --mask selection=mask.png -o
result.png` executes the platform's complete `deterministic-edit-v1` contract. Bindings must exactly
match the program's named image and mask inputs. The CLI verifies the output, input, command order,
program, normalized-command, and per-command pixel hashes before writing the PNG. `--dry-run`
validates bindings and emits stable compact JSON without authentication or an API request; omit
`--output` in that mode.
