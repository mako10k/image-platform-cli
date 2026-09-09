# CLI Native API V4 functional coverage matrix, revision 1

- Date: 2026-09-09
- Requirement: `docs/requirements/cli-native-api-v4-alignment.v5.md`
- Requirement SHA-256: `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6`
- Inventory source: CLI commit `1f298f39027ac5b6c4028ef45d24b37d481a1c97`
- Status: implementation baseline; default cutover is not ready

## Coverage rule

The current parser has 49 leaf commands when aliases are counted with their canonical command.
Every leaf appears in exactly one row below. Option values that select a different operation or
outcome are listed in the semantic-variant column. Command spelling, help, stdout, stderr, JSON
presentation and exit-status equality are not coverage dimensions.

`local-common` means the capability is implemented without an image-platform product API call.
WorkOS OAuth transport is permitted through the accepted authentication contract. `V4-bound` means
the capability is implemented and verified through the listed Native API V4 binding. `missing` means
the capability is not yet verified in `image4` and blocks default cutover.

## Matrix

| Current leaf command(s) | User-facing capability | Semantic variants that remain capabilities | Native API V4 binding(s) | Current result |
| --- | --- | --- | --- | --- |
| `help` | Browse CLI topics and usage | requested topic | none | `local-common` |
| `auth login`, `auth status`, `auth logout` | Establish, inspect and remove the selected public OAuth session | requested scopes; issuer, subject and organization credential identity | WorkOS Device Authorization, refresh and issuer/JWKS only | `local-common` |
| `capabilities` | Discover callable platform capabilities | authorization and configuration projection | `GET /v4/capabilities` | `V4-bound` |
| `generate` | Generate an image from text | dimensions, seed, prompt optimization and bounded wait | `POST /v4/generations`; job/artifact follow-up when accepted | `V4-bound` |
| `prompt optimize` | Produce a server-planned prompt | optional dimensions and seed | `POST /v4/prompt-plans` | `V4-bound` |
| `job list`, `job show` | Browse submitted jobs | status, operation, time, cursor and limit filters | `GET /v4/jobs`; `GET /v4/jobs/{job_id}` | `V4-bound` |
| `job cancel` | Cancel a cancellable job | state-conflict outcome | `POST /v4/jobs/{job_id}/cancel` | `V4-bound` |
| `job previews` | List preview outputs and obtain explicit preview access | step and output selection represented in returned previews | `GET /v4/jobs/{job_id}/previews`; `POST /v4/jobs/{job_id}/previews/{step_id}/{output}/access` | `V4-bound` |
| `artifact list`, `artifact show` | Browse Artifact metadata | state, kind, namespace, time, cursor and limit filters | `GET /v4/artifacts`; `GET /v4/artifacts/{artifact_id}` | `V4-bound` |
| `artifact download` | Download a ready Artifact through explicit access | destination file safety | `GET /v4/artifacts/{artifact_id}`; `POST /v4/artifacts/{artifact_id}/access` | `V4-bound` |
| `artifact upload` | Reserve, upload and complete an image or mask Artifact | namespace and kind | `POST /v4/artifacts/uploads`; external reserved upload; `POST /v4/artifacts/{artifact_id}/upload-completion` | `V4-bound` |
| `artifact delete` | Tombstone an unreferenced Artifact | explicit confirmation choice | `DELETE /v4/artifacts/{artifact_id}` | `V4-bound` |
| `search` | Search Artifacts by text, inline image or Artifact image | query source, namespace, MIME, time and limit filters | `POST /v4/artifacts/search` | `V4-bound` |
| `batch plan` | Create a generation BatchPlan | intent, dimensions, count, seed and optimization | `POST /v4/batch-plans` | `V4-bound` |
| `batch run`, `batch iterate` | Start a bounded campaign from a BatchPlan | cost bound, partial-result policy, threshold, rounds and wait | `GET /v4/batch-plans/{plan_id}`; `GET /v4/evaluation-rubrics`; `POST /v4/campaigns` | `missing` |
| `batch status`, `batch evaluate`, `batch results` | Inspect campaign state, evaluation and outputs | collection and result projections | `GET /v4/campaigns/{campaign_id}` plus explicit Artifact access for downloaded results | `missing` |
| `batch cancel` | Cancel a campaign | cancellation state | `POST /v4/campaigns/{campaign_id}/cancel` | `missing` |
| `caption` | Describe an inline or Artifact image | instruction, token bound and optional input capture | `POST /v4/captions`; Artifact upload bindings when capturing | `V4-bound` |
| `edit image-to-image` (`i2i`) | Generate an edited image from a source and target description | inline or Artifact input, capture, profile, prompts, strength, guidance, steps, seed and dimensions | `POST /v4/image-edits`; Artifact upload bindings when capturing | `missing` |
| `edit inpaint` | Replace selected image regions from a prompt | seed, profile and safety-filter mode | `POST /v4/inpaints` | `missing` |
| `edit segment` | Produce a segmentation mask | text, positive/negative points and bounding box | `POST /v4/segmentations` | `missing` |
| `edit matte-portrait` | Produce a refined portrait alpha matte | uncertainty radius | `POST /v4/portrait-mattings` | `missing` |
| `edit convert` | Convert an image with explicit format and quality | PNG, JPEG and WebP encodings and quality | `POST /v4/image-operations` | `missing` |
| `edit composite` | Place and blend one image over another | affine transform, opacity, mask, crop and blend mode | `POST /v4/image-operations` | `missing` |
| `edit run`, `edit verify` | Execute a deterministic edit program and verify reproducibility | input/mask bindings and repeated receipt/hash comparison | `POST /v4/image-operations` | `missing` |
| `edit replace-object`, `edit replace-background` | Replace selected object or background coverage | threshold, invert/combine, morphology, padding and feather controls | `POST /v4/image-operations` | `missing` |
| `edit raster crop` | Crop to an exact rectangle | rectangle geometry | `POST /v4/image-operations` | `missing` |
| `edit raster filter` | Apply deterministic filtering | Gaussian blur or unsharp mask, radius and amount | `POST /v4/image-operations` | `missing` |
| `edit raster adjust` | Apply ordered color and tone adjustments | hue, saturation, temperature, tint, exposure, brightness and contrast | `POST /v4/image-operations` | `missing` |
| `edit raster grayscale` | Convert visible pixels using the fixed luminance rule | fixed Rec. 709 behavior | `POST /v4/image-operations` | `missing` |
| `edit raster auto-crop` | Crop from mask coverage | threshold and padding | `POST /v4/image-operations` | `missing` |
| `edit raster shape` | Draw a deterministic vector shape into the raster | shape, rectangle, fill, stroke and stroke width | `POST /v4/image-operations` | `missing` |
| `edit raster text` | Draw deterministic text with a pinned font | text, position, font identity/hash, size, fill and stroke | `POST /v4/image-operations` | `missing` |
| `edit raster color-match` | Match source color statistics to a reference | algorithm, strength and luminance preservation | `POST /v4/image-operations` | `missing` |
| `edit raster resize`, `edit raster flip`, `edit raster rotate`, `edit raster canvas` | Apply deterministic affine geometry | fit, axis, quarter rotation, canvas placement and background | `POST /v4/image-operations` | `missing` |
| `edit raster project-quad` | Project a texture onto a quadrilateral | destination points and composite mode | `POST /v4/image-operations` | `missing` |
| `edit raster mesh` | Render a bounded mesh specification | mesh topology and texture input | `POST /v4/image-operations` | `missing` |

## Current cutover state

The two `local-common` rows and the rows marked `V4-bound` are implemented. Every row still marked
`missing` remains a cutover blocker until `image4` and its fake-server/contract tests supply
evidence. The stable `image` dispatcher must therefore remain bound to `image1`.

## Evidence index

- `tests/test_dispatch.py` and built-wheel isolated entrypoint checks cover the fixed default and
  three packaged commands.
- `tests/test_service.py` covers shared login, refresh rotation, three-part credential identity,
  selected-account integrity, and subject-change rejection.
- `tests/test_v4_api.py` covers exact V4 paths, r7 envelope/metadata checks, closed public
  projections, safe errors, repeated collection filters, synchronous and accepted-Job generation,
  Artifact upload/access/download integrity, search, captioning, and BatchPlan creation.
- `tests/test_v4_cli.py` covers reachability and semantic option variants for the implemented
  `image4` command families, including local topic help.
- `scripts/static-checks.sh` supplies Ruff, strict mypy, Xenon, and the repository's Pylint
  duplicate-code check across the extracted and replacement packages.
