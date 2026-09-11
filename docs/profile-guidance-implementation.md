# Plain text model guidance

Implemented from the owner-selected plain text design r2, in the matching CLI worktree.
The API source is the current image-platform worktree at dbe352f plus its guidance implementation.

- `model-profiles --details` requests the opt-in usage collection. `--profile` filters exact IDs.
- Default output displays text unchanged; JSON retains that same string and metadata. No renderer,
  content parser, cache, automatic setting selection or inference was added.
- Offline help points to online details. Old servers, unknown schema/profile and missing text fail
  explicitly. Existing no-query summary behavior is unchanged.
- The embedded route contract accepts summary or usage responses. The three descriptive usage
  object schemas tolerate extra metadata; binding semantics and common V4 validation remain intact.
  A future schema ID is reported as unsupported by the method rather than treated as current text.
- Generation remains one registered model; ordinary i2i already has --profile but the current API
  supports one base profile there. Generic Job profile selection is task-profile selection, not
  arbitrary model loading. This implementation does not change those execution contracts.

Validation: 193 focused CLI/API-protocol/help tests passed. Following a test-only typing correction,
all 8 new guidance tests passed again. Changed source modules and the new tests pass mypy; Ruff and
formatting checks passed. Complexity thresholds and the repository duplicate-code check passed.
The real local API usage envelope was verified through CLI MockTransport (13 profiles, no network).
All 15 actual command examples in the server text parse with this CLI. The API wheel was independently
checked for all 13 exact UTF-8 text resources. No deployment, local tool reinstall, push or live
inference was performed.
