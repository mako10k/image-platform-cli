# CLI V4 continuation: upstream image-edit response contradiction

- Observed: 2026-09-09 19:49 JST; workday extended by owner to 22:00, buffer starts 21:50.
- State: preserved WIP; downstream implementation paused for owner design disposition.
- CLI worktree: `/home/katsumata-m/.codex/worktrees/cli-v4-alignment/image-platform-cli`
- CLI branch/base: `codex/cli-v4-alignment`, `1f298f39027ac5b6c4028ef45d24b37d481a1c97`.
- API reference worktree: `/home/katsumata-m/.codex/worktrees/native-api-v2-interface-alignment/image`.
- API HEAD: `a1d6fcc9f55a698c41caf73510a5ef8261884a63`.

## Blocking contradiction precedes coverage claims

Current phase: CLI implementation. Earliest observed cause: accepted design and contract.
The accepted r7 design line 186 declares `V4ImageEditResult.receipt: ImageEditReceipt`.
Line 264 assigns this result to `POST /v4/image-edits`, whose producer is
`ImageEditService.image_to_image`. That producer returns `ImageToImageReceipt`, a distinct
model with `controls` and `implementation_revision`; it is not an `ImageEditReceipt`.
`native_v4_success` validates the actual model before producing the response and rejects it.

Local ASGI reproduction, with a fake provider returning a valid PNG and consistent receipt:

```json
{"surface":"local ASGI only","v4_status":500,"v4_error":{"code":"internal_error","message":"native operation failed","retryable":false},"provider_calls_after_v4":1}
{"serialization_errors":[{"location":["receipt"],"type":"model_type"}]}
{"v1_status":200,"provider_calls_total":2,"producer_receipt":"ImageToImageReceipt","declared_v4_receipt":"ImageEditReceipt"}
```

No live/public request or inference was made. The V1 call is a local comparison only;
`image4` never falls back to V1. A failed V4 response occurs after the fake provider completes,
so retrying real inference would not be an appropriate diagnostic action.

Related scope checked: both routes using `V4ImageEditResult`. Inpaint uses
`ImageEditService.apply -> ImageEditResult -> ImageEditReceipt` and matches the declared receipt
by source inspection. Image-to-image does not. No claim is made about every other operation.

Root cause: one success-result type was assigned to two producers with different receipt contracts.
Detection cause: earlier CLI fake responses were locally constructed, and route inventory tests
alone did not exercise a correctly typed image-to-image result through V4 serialization.
Proposed correction (not authorized or applied): give image-to-image a result model retaining
`ImageToImageReceipt`; keep inpaint's `ImageEditReceipt`; revise accepted r7 design first.
Proposed regression: run a valid fake image-to-image provider through the V4 route and verify
200, required headers, output bytes, applied controls and receipt identity together.

## Preserved continuation work

- Added V4 Campaign run/iterate/status/evaluate/results/cancel and corresponding CLI scope selection.
- Added 18 Campaign tests; total most recent test run: 143 passed.
- Added pinned route status/header/error and serialized response-schema verification. The 33
  paths were checked against accepted r7 design. `route_contracts.json` is implementation data,
  not new normative authority; it deliberately still reflects the discovered r7 contradiction.
- Added `jsonschema` runtime validation and its development type stubs, with lock updates.
- Rejected request-target metacharacters in resource IDs; checked returned Job/Artifact identity.
- Added streamed Artifact byte limits and early output-file availability checks.
- Existing functional matrix has NOT been promoted. Campaign coverage and all new validation
  remain WIP pending the design recovery and subsequent complete verification.
- Packaged `image` remains bound to `image1`. No cutover, commit, push, release or API mutation.
- PERT history/lifecycle has not been changed on discovery; `T_CLI_V4_ALIGNMENT` is logically
  paused here pending owner routing. Do not mark it complete or select another task.

## Source digests

| Source in API reference worktree | SHA-256 |
| --- | --- |
| `docs/design/native-api-v4-interface-alignment.r7.md` | `6bd786b13f27d79e6c50cbd4d2b14bf92d2bb2378b43b9f8c9cdfe6427523252` |
| `src/image_platform/native_v4.py` | `015df27c5027e7b1226ac8e5903fab92ea682a9eaa830e94afaf8a93b1f2de60` |
| `src/image_platform/api.py` | `c9bc629a84e87ada6e31329e24b5d55754bcc096001a61f37997e402faedf0d8` |
| `src/image_platform/editing.py` | `e13333ae488c66604b94601e37bbd3c5bc238d55d7ddc165b5c6e6a442b0a73e` |

The route snapshot was exported without external calls from `create_app().state.native_v4_routes`,
using `TypeAdapter(model).json_schema(mode="serialization")` for declared success models and exact
route status, scope, header and fixed-error metadata. No server import is required at CLI runtime.
Request schemas explored in `/tmp/native-v4-route-contracts.json` have NOT been installed in the CLI.

## Exact restart point

1. Obtain owner disposition on the accepted design mismatch; do not bypass it in CLI code.
2. If REVISE is authorized, use the applicable design/review workflow and forward-only PERT recovery;
   preserve completed history and current WIP. Do not infer permission for publication or deployment.
3. After design acceptance, correct the API result contract and add the local producer-through-route
   regression, then refresh the CLI's pinned contract snapshot and resume remaining image commands.
4. Finish complete functional coverage and package checks before any cutover-readiness claim.

Reproduction script is preserved as `2026-09-09-v4-image-edit-repro.txt` beside this handoff.
From the API reference worktree, run `PYTHONPATH=. uv run python PATH_TO_THAT_FILE`.
Audited CLI reasoning: `/tmp/cli-v4-design-receipt-blocker.dsl` (fatal/error/warning all zero).

## Preservation verification at 19:50 JST

- Ruff, strict mypy (22 source files), Xenon and duplicate-code checks passed.
- Source distribution and wheel built successfully into `/tmp/cli-v4-resume-build`.
- In an isolated non-project environment, the wheel included all 33 route contracts and
  `image`, `image1`, `image4 --help` all exited successfully.
- `git diff --check` passed. No remote synchronization was performed.
- Shared workday readback still shows `working`, start 08:35, planned end 22:00.
