# CLI Native API V4 implementation handoff

- Updated: 2026-09-09 19:30 JST
- Worktree: `/home/katsumata-m/.codex/worktrees/cli-v4-alignment/image-platform-cli`
- Branch: `codex/cli-v4-alignment`
- State: uncommitted WIP; no push or cutover performed

## Accepted authority

- Requirement: `docs/requirements/cli-native-api-v4-alignment.v5.md`
- Requirement SHA-256: `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6`
- Owner result: `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v5-second-owner-review-result.md`
- Decision: `ACCEPT`

The stable packaged `image` dispatcher remains fixed to `image1`. Default rebinding, live requests,
release, commit, and push have not been performed.

## Implemented WIP

- Physical `common`, `v1`, `v4`, and thin `dispatch.py` boundaries are present.
- Packaged entrypoints are `image -> v1`, `image1 -> v1`, and nondefault `image4 -> v4`.
- Shared credentials use issuer, subject, and organization identity with a nonsecret selected-account
  pointer. Status and refresh reject mismatched stored identity, and refresh cannot replace a
  credential when the token subject changes.
- Shared local input, safe output-file, generation-argument, and caption-input behavior lives under
  `common` only where both implementations use the same contract.
- `image4` validates the Native API V4 r7 envelope, no-store policy, request identity, public errors,
  and the operation-specific projections implemented so far.
- `docs/design/cli-v4-functional-coverage.v1.md` records 13 `V4-bound`, 2 `local-common`, and 22
  `missing` rows. The implemented V4 rows cover capability discovery, generation including accepted
  Job follow-up, prompt optimization, Job reads/cancel/previews/access, Artifact list/show/download/
  upload/delete, search, BatchPlan creation, and captioning including optional input capture.
- Artifact and generation downloads verify explicit-access metadata, SHA-256, byte size, MIME type,
  image format, dimensions, and exclusive destination creation before reporting success.

## Verification

- `./scripts/static-checks.sh`: passed, including Ruff, strict mypy, Xenon, and Pylint duplicate-code;
  Pylint score 10.00/10.
- `uv run pytest -q`: 125 passed.
- `uv build`: built source distribution and wheel successfully.
- Isolated installed-wheel checks: `image --help`, `image1 --help`, and `image4 --help` all exited 0.
- `git diff --check`: passed.

## Exact restart point

Continue from the 22 `missing` rows in `docs/design/cli-v4-functional-coverage.v1.md`. Close the
Campaign family first because BatchPlan creation, Job validation, Artifact access, and common bounded
wait support now exist. Implement and test:

1. `GET /v4/batch-plans/{plan_id}` and `GET /v4/evaluation-rubrics`;
2. `POST /v4/campaigns`, `GET /v4/campaigns/{campaign_id}`, and cancellation with both ordinary and
   iterative policies;
3. campaign evaluation/results projection and explicit Artifact access for result downloads;
4. then the image-edit families, beginning with the common inline-image/output validation already
   extracted.

Keep each matrix row `missing` until its CLI path, exact V4 binding, inner response/receipt checks,
and fake-server tests all pass. Do not rebind `image`; that remains a separate owner decision after
the matrix has no `missing` rows.
