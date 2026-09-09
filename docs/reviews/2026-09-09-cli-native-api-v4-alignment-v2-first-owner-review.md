# CLI to Native API V4 replacement revision 2 first owner review

- Date: 2026-09-09
- Lifecycle step: 2
- Status: `AWAITING_OWNER_ROUTE`
- Requirement text changed after self-review: no

## Exact review subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v2.md` | `366fee5f10e0662957e7a263dc3218c879d06f844bd4216a9c67e305751587d5` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v2-self-review.md` | `20ad4150e467585eb290f94f095986fa85f461e8e0e9ed951dd9334b26892dc3` |

## Proposed replacement

The stable `image` command remains a behavior-free dispatcher. It calls `image1` for the entire
pre-cutover period and `image4` after one separately authorized release cutover. `image1` preserves
the current CLI. `image4` is built and verified in parallel and cannot call V1,
provider-compatible, or direct-Modal network endpoints.

API-version-independent authentication, credential, configuration, I/O and safety behavior moves
only when its contract is identical into internal `image_platform_cli/common`. Version-specific
paths, models, envelopes, headers, receipts and command availability remain isolated.

## Compatibility and completion boundary

Before cutover, every current command must receive one accepted parity disposition. Missing V4
authority blocks cutover; it does not permit silent command removal or V1 fallback. Credentials and
non-versioned configuration retain their identity across the switch.

The packaged dispatcher, rather than mutable user configuration, owns the default selection.
`image1` remains available for the first post-cutover release as a deprecated rollback/diagnostic
entrypoint. Release and default-binding changes require separate authorization.

## Duplication control

The repository already runs Pylint's eight-line duplicate-code check over source and tests. Revision
2 keeps that check and requires semantic review before moving a clone into `common`. No additional
checker is proposed without an observed detection gap.

## Acceptance criteria and unknowns

The candidate's nine acceptance criteria cover entrypoint lifecycle, common/versioned boundaries,
current behavior preservation, V4-only network behavior, command parity, credential/config
continuity, clone detection, cutover and rollback.

The complete parity matrix is not yet authored. This is intentionally a cutover blocker. The review
must determine whether the blocker rule is sufficient or whether the matrix must be part of this
requirement snapshot before acceptance.

## Proposed independent-review questions

1. Does the dispatcher and three-entrypoint lifecycle prevent a partially migrated default CLI?
2. Are `image1` preservation and `image4` no-fallback rules decidable and compatible with accepted
   API authority?
3. Does the parity-matrix blocker prevent silent command loss without making completion circular or
   impossible?
4. Do `common`, credential, configuration and clone-detection boundaries avoid duplication and
   false abstraction?
5. Are cutover and rollback conditions sufficient and independently authorized?
6. Have new executable names or a hidden broader redesign entered scope without owner disposition?

## Owner decisions and route

Confirm or revise these proposed decisions:

- `image1` and `image4` are acceptable transitional executable names;
- a command without an accepted V4 disposition blocks cutover;
- `image1` remains for at least the first post-cutover release;
- `common` remains internal rather than a separately versioned library; and
- the existing Pylint clone check is the initial duplication control.

Then choose exactly one route:

- `REVISE`: return directly to candidate authoring;
- `REVIEW_THEN_REVISE`: add owner questions, independently review, then return to authoring;
- `REVIEW_THEN_DECIDE`: add owner questions, independently review, then return for the second owner
  decision; or
- `REVIEW`: independently review the questions above, then return for the second owner decision.

The recommended route is `REVIEW_THEN_DECIDE`. The new executable namespaces, parity blocker and
rollback lifetime are material decisions, so independent review should test them before final owner
acceptance.

Independent review cannot edit or accept the requirement. This review authorizes no implementation,
external request, credential change, publication, deployment or release.
