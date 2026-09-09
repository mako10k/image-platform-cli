# CLI to Native API V4 replacement revision 2 independent review

- Date: 2026-09-09
- Lifecycle step: 3
- Status: `COMPLETED_WITH_CONTRADICTION`
- Owner route: `REVIEW_THEN_DECIDE`
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v2.md`
- Verified candidate SHA-256: `366fee5f10e0662957e7a263dc3218c879d06f844bd4216a9c67e305751587d5`
- Candidate changed by reviewer: no

## Results

### 1. Dispatcher and entrypoint lifecycle

Classification: no contradiction.

The dispatcher selects one complete implementation in the built package. It performs no parsing and
has no per-command or environment-controlled version choice. Therefore the default `image` command
cannot expose a partially migrated mix: it delegates wholly to `image1` before cutover and wholly to
`image4` afterward. Transitional direct entrypoints remain callable without changing the default
product state.

### 2. `image1` preservation and `image4` no-fallback rule

Classification: contradiction with the reviewed requirement and its authoritative authentication
source.

Section 5 says `image4` “uses only accepted Native API V4 bindings for network operations.” Read
literally, this prohibits WorkOS Device Authorization, token refresh and issuer/JWKS network access.
Section 6 simultaneously requires `image4` to use the accepted public OAuth-client contract, which
requires those communications.

Cause phase: requirement wording. The intended V4-only restriction must apply to image-platform
product API operations, with accepted WorkOS OAuth transport explicitly retained. The reviewer does
not insert that correction into the candidate.

The remaining no-fallback boundary is decidable: product API requests from `image4` may use accepted
V4 bindings only and must never use V1, `/v2beta`, provider-compatible endpoints, workers or Modal.

### 3. Command parity and completion

Classification: evidence gap or unresolved unknown; no additional contradiction.

Mechanical discovery found 47 current leaf commands and 33 accepted V4 bindings. Several commands
can map to one semantic V4 binding, while authentication, help and offline operations can be
`local-common`. A versioned many-to-one parity matrix is therefore feasible.

The requirement prevents circular acceptance: revision 2 fixes the disposition rules, while the
later matrix supplies the command facts. Every unresolved row is a cutover blocker, so absence of the
matrix cannot be mistaken for completion. A missing V4 counterpart requires a separate owner
decision and cannot silently remove a command or invoke V1.

### 4. Common-code and duplication boundaries

Classification: no contradiction.

`common` is internal and admits only contracts with identical meaning across implementations.
Version-specific paths, wires, envelopes, headers, receipts and availability stay outside it. The
existing Pylint duplicate-code check scans `src` and `tests` with an eight-line threshold. The
candidate treats findings as review inputs rather than automatic abstraction instructions.

### 5. Cutover and rollback

Classification: no contradiction, with one evidence gap.

The cutover conditions separately require parity acceptance, characterization, local verification,
wheel entrypoint checks, authorized live smoke, zero blockers, an exact rollback revision and
separate release authorization. Retaining `image1` for the first cutover release does not make the
default binding partial.

Evidence gap or unresolved unknown: the stabilization criteria and exact release that removes
`image1` are not yet defined. Removal already requires later readback and a separate decision, so
this does not need to be invented in revision 2.

### 6. Namespace and broader-scope check

The owner explicitly proposed `image1` and `image4` as transitional names. They are not silently
introduced by the reviewer. The candidate keeps `image` as the stable supported command.

- Optional or future candidate: a separately distributed common library, additional clone checker,
  and final `image1` removal criteria.
- Out of scope: API/edge/identity-provider/cloud changes, live requests, credentials, publication,
  deployment and release.
- Evidence gap or unresolved unknown: complete command parity and post-cutover stabilization data.

## Reviewer conclusion

The review is complete, but `ACCEPT` is not supportable for the current bytes because section 5
contradicts the required OAuth network behavior. The unchanged snapshot proceeds to lifecycle step
4. The supported owner decision is `REVISE`, followed by a new requirement revision that limits the
V4-only rule to image-platform product API operations. No other contradiction was found.

This review does not edit or accept the requirement and authorizes no implementation or external
effect.
