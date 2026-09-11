# image-platform CLI

Independent command-line client for the image platform.

The default client uses Native API V4 and the accepted public OAuth authentication flow.
Local validation and authenticated Staging smoke evidence are recorded under `docs/reviews/`.

See [`docs/auth-contract.md`](docs/auth-contract.md).

## Parallel CLI implementations

`image` delegates to `image4`. `image1` retains the former Native API V1 implementation.
`image` and `image4` product API calls use the accepted V4 r8 contract. Authentication and API-independent local
program builders are shared internally. The default binding is fixed by the package.

The earlier accepted 49-command baseline has functional coverage in `image4`. The current parser
has 56 product-command leaves, plus `help` and the `i2i` alias (58 leaf paths); all 66 help paths,
including groups and the root, are checked offline. See the
[functional coverage matrix](docs/design/cli-v4-functional-coverage.v19.md) and
[completion evidence](docs/reviews/2026-09-09-cli-v4-functional-implementation-complete.md).
The cutover candidate passed the complete local test suite, repository static checks, built-wheel
entrypoint checks, and authenticated public V4 smoke tests. Release remains a separate action.

## Development

```bash
uv sync --all-groups
uv run ruff check .
uv run mypy
uv run pytest -q
```

Start with these commands; `image help` lists all groups and `image help GROUP [COMMAND]`
shows their options and examples:

```text
image auth login [--scope SCOPE]...
image auth status
image auth logout
image generate "a blue ceramic cup" --output cup.png [--width 1024] [--height 1024]
  [--wait 0..120] [--allow-long-wait]
image prompt optimize "a blue ceramic cup" [--width 1024] [--height 1024] [--seed N]
```

`login` performs the WorkOS Device Authorization Flow. It will fail closed when the platform has
no usable OS credential-store backend. V4 defaults cover fourteen application scopes:
`images:generate`, `images:edit`, `images:understand`, `batches:plan`, `batches:execute`,
`campaigns:read`, `campaigns:write`, `jobs:submit`, `jobs:read`, `jobs:cancel`,
`artifacts:read`, `artifacts:write`, `artifacts:access`, and `artifacts:delete`.
Repeat `--scope` to select an explicit subset for login.

`prompt optimize` submits the query, optional dimensions and effective seed to
`POST /v4/prompt-plans`. It prints the optimized prompt by default, or the validated plan with
`--json`. The server owns prompt planning; the CLI does not call provider-compatible routes.
An explicit seed is preserved; otherwise the CLI chooses a random seed in `0..2^63-1`.
A seed alone is not a cross-model or cross-revision reproducibility guarantee.

`generate` refreshes the session, validates the new access token, and submits one idempotent native
generation Job. It waits up to 30 seconds by default, automatically polls any HTTP 202 response,
retrieves the completed Artifact through its short-lived signed URL, verifies its SHA-256, byte
count, MIME type, and PNG dimensions, then creates the output without overwriting an existing file.
When `--seed N` is omitted, the CLI selects a random seed in `0..2^63-1`. An explicitly supplied
seed, including zero, is preserved. The V4 command prints saved dimensions and the output path;
it does not print the seed. Specify `--seed` when you need to retain it for a later comparison.
The OAuth token is sent only to the configured API origin and never to the signed Artifact URL.
`--wait 0` begins polling immediately. Waits from 61 through 120 seconds additionally require
`--allow-long-wait`; the CLI intentionally has no option that disables polling. Live login and
generation remain separately gated.

## Editing semantics and receipts

`image edit image-to-image` (`i2i`) uses descriptive Stable Diffusion 1.5 image-to-image. Its
prompt describes the desired final image; it is not an instruction such as “remove the person”.
Instruction editing is a separate platform-only capability backed by the `edit-flux2-klein-4b`
profile; it is not callable through the current public V4 image-edit route.
The I2I command keeps its existing strength `0.75`, guidance `7.5`, and 25-step defaults.

Staging's I2I adapter now executes typed VAE Encode → latent denoise → Decode internally via
`/v4/image-edits`. Use the existing I2I command; there are no standalone VAE-stage commands,
optimizer switches or new in-VAE operations in this CLI. This extraction does not claim a
speed or image-quality improvement. A light composition-preserving example is:

```bash
image edit image-to-image "watercolor coastal cottage" --input sketch.png -o watercolor.png \
  --width 256 --height 256 --steps 10 --strength 0.6 --guidance-scale 7.5 --seed 17
```


Synchronous V4 I2I and explicit-mask inpaint validate their response receipts before saving,
then print dimensions and the output path. They do not print the full receipt, model revision,
seed or compute cost. The legacy `image1` output format differs. Inpaint retains the current
contract: white mask pixels are repainted, black pixels are preserved, and `grow_mask=0`.

Inpaint also accepts `--safety-filter default|enabled|disabled`. Non-default modes succeed only
when the authenticated server explicitly permits per-request control. The V4 CLI validates the
requested and effective safety modes and outcome in the response; it does not print these fields.
Development Staging currently composes the Safety Checker out because of excessive false positives;
the CLI does not add a local checker.

`image edit upscale --input scene.png --width 2048 --height 2048 -o enlarged.png` and
`image edit restore --input scene.png -o restored.png` call `POST /v4/enhancements`.
Both use deterministic quality by default; `--quality-tier ai` requests the registered AI profile
and remains subject to server authorization. Restore always preserves the input dimensions.

`image edit run --program edit.json --input scene=scene.png --mask selection=mask.png -o
result.png` executes the platform's complete `deterministic-edit-v1` contract. Bindings must exactly
match the program's named image and mask inputs. The CLI verifies the output, input, command order,
program, normalized-command, and per-command pixel hashes before writing the PNG. `--dry-run`
validates bindings and emits stable, sorted JSON without authentication or an API request; omit
`--output` in that mode.

`image edit plan --request edit-plan-request.json` sends a complete bounded planner request and
prints the verified physical Pipeline and planning receipt. `image edit batch --request
edit-batch-request.json` sends a complete synchronous batch request and verifies the batch receipt
and every successful inline image before printing the response.

`image batch list --limit 10` lists Campaigns with cursor pagination. `image job submit --request
job-request.json` submits a complete durable Pipeline and policy request with an idempotency key;
the returned accepted Job is validated before it is printed.

## Help and quality gates

`image help` prints the command catalog. Continue with `image help edit` or
`image help edit run` to navigate into a group or command; detailed topics include guidance,
copyable examples, child topics, and a related parent topic. Replace example paths, IDs and font
digests with real values. Help is offline; commands in examples may perform API operations when run.
The catalog reflects CLI support, while `image capabilities --json` reports server availability.

Generic durable Job profiles also have help-only topics. Follow `image help job`, then
`image help job submit`, and choose `guided-edit`, `controlnet-canny`, `ip-adapter-plus`, or
`recovery`. The profile pages include complete request JSON while execution remains on
`image artifact upload` and `image job submit`. Command failures print a contextual `image help`
recovery route; the help page distinguishes Canny structure guidance from IP-Adapter appearance
guidance and records that the current profiles cannot combine both in one Job.

`image edit replace-object` and `image edit replace-background` compile common replacement
workflows into the same deterministic program contract. They support thresholding, disk dilation
(`--padding` is its bounding-mask convenience alias), erosion, feathering, and union,
intersection, subtraction, or explicit inversion of object masks. Background replacement inverts
one foreground mask automatically.
The replacement command uses coverage-limited `replace` compositing, so pixels outside the resolved
coverage remain the original base pixels. Both commands support `--dry-run`, and their detailed
examples are available through `image help edit replace-object` and
`image help edit replace-background`.

`image edit raster` adds discoverable CPU-only recipes. `crop` uses an exact pixel rectangle,
`filter` exposes Gaussian blur, box blur, and unsharp mask, and `adjust` composes hue/saturation,
white balance, exposure, brightness, and contrast in a stable order. `auto-crop` uses an explicit
mask, `shape` draws bounded rectangles or ellipses, and `color-match` uses an explicit reference.
`text` requires an administrator-registered font ID and its exact SHA-256 rather than accepting an
arbitrary font path.
`resize --fit`, `flip`, right-angle `rotate`, and `canvas` compile exact affine matrices after
reading only the source dimensions locally. Each child supports `--dry-run` and has examples under
`image help edit raster CHILD`.

`image edit matte-portrait --input portrait.png --person-mask person.png -o matte.png` calls the
private registry-pinned portrait-matting route. `--uncertainty-radius 0..64` bounds how far the
server may recover fractional hair or eyeglass alpha beyond the supplied person mask. The CLI
verifies the source, mask, output, profile, model revision, normalized radius, dimensions, and
SHA-256 receipt before writing the RGBA PNG. Detailed guidance is available through
`image help edit matte-portrait`.

`image artifact delete ARTIFACT_ID` tombstones only an unreferenced principal-owned Artifact. It
requires typing the exact Artifact ID unless `--force` is supplied for automation. The server
rejects Job input/output references, makes retries idempotent, and retains content-addressed object
bytes because another Artifact may share them; the CLI verifies the returned deleted state and
deletion timestamp.

Advanced deterministic surfaces include `project-quad` for perspective placement with explicit
composite modes and `mesh` for a bounded saved vertex/triangle JSON specification. The ordinary
`composite` command also accepts `source_over`, `replace`, `multiply`, or `screen`. `image edit
verify` runs a saved program exactly twice and fails unless the bytes, output and program hashes,
dimensions, and every normalized-command and pixel receipt hash match.

Run `./scripts/static-checks.sh` before committing. In addition to Ruff and strict mypy, it rejects
cyclomatic-complexity regressions through Xenon and clone-code blocks of eight or more similar
lines through Pylint. CI runs the same locked checks and the complete test suite.

## License and contributions

The CLI source and its repository-authored documentation are licensed under the
[Apache License 2.0](LICENSE). Attribution information is in [NOTICE](NOTICE).
Contributions require Developer Certificate of Origin 1.1 sign-off; see
[CONTRIBUTING.md](CONTRIBUTING.md).

This software license does not grant rights to platform service marks, models,
weights, fonts, user inputs, generated outputs, or other external assets. Those
remain governed by their applicable terms and recorded provenance.
