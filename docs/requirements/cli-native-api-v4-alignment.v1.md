# CLI to Native API V4 alignment requirements, document revision 1

- Status: `DRAFT_FOR_FIRST_OWNER_REVIEW`
- Date: 2026-09-09
- API major version: `4`
- Requirement document revision: `1`
- Lifecycle phase: step 1 complete
- Decision authority: user

## 1. Provenance and authority

This candidate defines a bounded intermediate alignment for the existing CLI. It does not become
authoritative until the owner accepts these exact bytes through the requirement-review lifecycle.

Normative inputs are:

| Role | Path | SHA-256 |
| --- | --- | --- |
| Accepted Native API V4 requirement | image repository `docs/requirements/native-api-v4-interface-alignment.r3.md` | `e825d34ad807b4236dbd91b84fa09e9fac6086ff7617935dff197988becd5873` |
| Accepted Native API V4 design | image repository `docs/design/native-api-v4-interface-alignment.r7.md` | `6bd786b13f27d79e6c50cbd4d2b14bf92d2bb2378b43b9f8c9cdfe6427523252` |
| Accepted CLI authentication contract | `docs/auth-contract.md` | `4085db4513d39ba66bd68d215316815401fdb8b8d832e68751ff2bc2de7d4303` |

The current CLI implementation at commit `1f298f39027ac5b6c4028ef45d24b37d481a1c97` and the
deployed public-edge observations are non-normative feasibility evidence. They cannot expand or
override the accepted API or authentication contracts.

## 2. Product outcome

Make the existing `image capabilities` command and deterministic edit command family use the
public OAuth edge's Native API V4 contract. Preserve command names, options, local dry-run behavior,
output-file safety, token handling, receipt verification, and user-visible output.

This intermediate increment proves that the existing CLI can discover and execute one complete,
useful V4 capability without importing the broader pre-1.0 CLI redesign. Other existing commands
continue to use their current V1 or provider-compatible routes until separately aligned.

## 3. Exact selected bindings

Only these two V4 bindings are selected:

| CLI surface | Method and path | OAuth scopes | Success data |
| --- | --- | --- | --- |
| `image capabilities` | `GET /v4/capabilities` | bearer required; no operation scope | `V4CapabilityList` |
| deterministic edit commands that currently call the native image-operations producer | `POST /v4/image-operations` | `images:edit` | `StatelessImageOpsResponse` |

The deterministic family includes `edit run`, `edit verify`, composite, replacement, and raster
commands only where the current implementation already compiles the command into
`deterministic-edit-v1` and calls the image-operations producer. This requirement adds no command,
primitive, recipe, compiler, or local execution engine.

## 4. V4 request and response handling

### 4.1 Common envelope

For both selected bindings, the CLI must require a JSON success envelope with exactly one `data`
object and one `meta` object. It must verify:

- `meta.api_version == "4"`;
- `meta.contract_revision == "2026-09-07-r7"`;
- `meta.request_id` matches `^req_[0-9a-f]{32}$`; and
- `meta.request_id` equals the single `X-Request-ID` response header.

Malformed, missing, mismatched, or unsupported-version envelope facts fail closed before any output
file is created.

For an error response, the CLI may expose only the HTTP status, a validated lowercase public
`error.code`, and the validated request ID. It must not print `error.message`, response bodies,
tokens, cookies, private headers, or upstream diagnostics.

### 4.2 Capability projection

The CLI retains its current four-item user-facing capability projection. It derives each item from
the matching V4 binding and does not infer availability from unrelated catalog items:

| CLI item | V4 route ID | Display endpoint |
| --- | --- | --- |
| `image_to_image` | `v4.image_edits.create` | `/v4/image-edits` |
| `segmentation` | `v4.segmentations.create` | `/v4/segmentations` |
| `image_operations` | `v4.image_operations.create` | `/v4/image-operations` |
| `inpaint` | `v4.inpaints.create` | `/v4/inpaints` |

Each selected binding must have the accepted method, path, ordered scope tuple, `configured`,
`authorized`, and optional reason. Missing or duplicate route IDs, changed method/path/scope facts,
or inconsistent state/reason combinations fail closed. Platform-only items and private catalog facts
are not displayed.

### 4.3 Deterministic image operations

The CLI sends the existing named inline inputs and unchanged `deterministic-edit-v1` program in a
`StatelessImageOpsJsonRequest`. It omits the V1-only `response_format`, sends
`max_cost_usd: "0"`, and relies on the accepted default deadline unless a later accepted CLI
requirement exposes it.

After unwrapping `data`, the CLI retains all current byte, MIME type, dimensions, input SHA-256,
program SHA-256, command order, normalized-command SHA-256, per-command pixel SHA-256, output
SHA-256, and cost checks. It additionally verifies the required V4 image-operation headers against
the body: output SHA-256, width, height, program SHA-256, and non-empty implementation revision.
Logical-program and physical-graph headers remain optional and are accepted only when the typed
receipt supplies matching values.

No output file may be created before every applicable envelope, header, body, and receipt check
passes.

## 5. Authentication, transport, and compatibility

The CLI remains a public OAuth client. It sends the bearer only to the configured API origin and
never learns, stores, or forwards Modal proxy credentials. `image capabilities` requests a valid
bearer without adding an image-operation scope. Deterministic edits continue to require
`images:edit` before request dispatch.

The API base URL remains configuration, and the staging default remains
`https://api-staging.image.mk10.org`. There is no silent fallback from V4 to V1 after a V4 request
fails. Local `--dry-run` remains credential-free and network-free.

All unselected CLI routes, wires, response handling, and commands remain unchanged in this
increment. Native API V1 and provider-compatible compatibility remain owned by their existing
contracts.

## 6. Acceptance criteria

This candidate may be accepted only when the owner confirms that:

1. the two-binding boundary is the intended intermediate meaning of CLI V4 usability;
2. current command names, options, output, and local dry-run behavior remain stable;
3. capability projection is bound to the four named V4 route IDs without exposing private facts;
4. deterministic requests omit `response_format`, cap cost at zero, and retain the existing program;
5. common V4 envelope, request identity, revision, required headers, output bytes, and receipts all
   fail closed on mismatch;
6. token and private Modal credential boundaries remain unchanged; and
7. every unselected command stays on its current route pending separate alignment.

Implementation acceptance later requires deterministic fake-server tests for success and every
new fail-closed boundary, the repository's full static checks, and one separately authorized
authenticated staging smoke through the existing CLI for `capabilities` and one one-command
deterministic edit. The live smoke must validate the returned image and request identity and must not
be treated as authority for this requirement.

## 7. Out of scope

- aligning any CLI command beyond capability discovery and existing deterministic image operations;
- changing the command taxonomy, parser structure, configuration model, or presentation format;
- adding model-profile discovery or a new command;
- changing API V4, OAuth edge, WorkOS roles/grants, Modal, Cloudflare, or DNS;
- live authentication, live requests, deployment, release, publication, push, PR, or merge; and
- importing the broader CLI redesign, V5 candidates, generic Program execution, or local daemon work.

## 8. First owner-review decisions

The first owner review decides:

1. whether the two-binding boundary is sufficiently complete for this intermediate milestone;
2. whether deterministic requests must use the explicit zero-dollar cap;
3. whether the current four-item capability output should be preserved as specified; and
4. which lifecycle route to take.

No answer is inferred. This candidate authorizes no independent review, implementation, live
request, deployment, credential change, Git publication, or release.
