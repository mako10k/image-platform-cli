# CLI to Native API V4 alignment revision 1 independent review

- Date: 2026-09-09
- Lifecycle step: 3
- Status: `COMPLETED`
- Owner route: `REVIEW_THEN_DECIDE`
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v1.md`
- Verified candidate SHA-256: `674a316d49b7f05423dc230638528a3be50c582366a7828466d9711a50cfe224`
- Candidate changed by reviewer: no

## Results

### 1. Exact selected bindings and capability route IDs

Classification: no contradiction.

Accepted V4 design revision 7 defines `GET /v4/capabilities` with an empty operation-scope tuple
and `POST /v4/image-operations` with `images:edit`. It uniquely defines all four capability route
IDs and the candidate copies their accepted method and path:

- `v4.image_edits.create` -> `POST /v4/image-edits`;
- `v4.segmentations.create` -> `POST /v4/segmentations`;
- `v4.image_operations.create` -> `POST /v4/image-operations`; and
- `v4.inpaints.create` -> `POST /v4/inpaints`.

The candidate does not treat those three displayed but unselected operation bindings as authority to
invoke them in this increment.

### 2. Two-binding intermediate boundary

Classification: no contradiction.

The accepted API requirement makes CLI alignment a separately named and accepted subject. It records
eventual CLI dispositions for the semantic inventory but does not require every disposition to ship
in one task or milestone. The portfolio task requires a bounded CLI-to-V4 requirement, preserves the
broader redesign for later, and describes the intermediate result as the existing CLI being usable
through V4. Capability discovery plus a complete deterministic edit is a useful end-to-end V4
operation, so the selected boundary is consistent with that intermediate wording.

Aligning the remaining current CLI operations is an optional or future candidate. It cannot be added
to revision 1 by this review.

### 3. Request and response checks

Classification: no contradiction.

The candidate removes the V1-only `response_format`, preserves the existing program and named
inputs, selects an allowed zero-dollar maximum cost, and requires the accepted V4 envelope. It
checks API version, contract revision, header/body request identity, required image-operation
headers, output bytes, metadata, program/input/output hashes, command order, normalized-command and
pixel hashes, receipts, and cost before creating an output file.

Evidence gap or unresolved unknown: implementation must prove that every current deterministic
command path reaches the shared verifier. Current source shows calls through
`run_deterministic_program` and `composite`, with three image-operation request sites. This is a
test obligation already covered by the candidate, not a requirement contradiction.

### 4. Security and compatibility boundaries

Classification: no contradiction.

The candidate preserves the public-client bearer boundary, least-privilege scope selection,
configured API origin, credential-free offline dry-run, safe error projection, and the rule that the
CLI never knows Modal credentials. It adds no fallback after a V4 failure and leaves unselected
routes unchanged. These choices agree with the accepted CLI authentication contract and Native API
V4 compatibility boundary.

Evidence gap or unresolved unknown: the required authenticated CLI staging smoke has not run. It is
correctly classified as separately authorized implementation-acceptance evidence rather than
requirement authority.

### 5. Scope-expansion check

No unauthorized concern became a requirement blocker.

- Optional or future candidate: V4 alignment for the remaining CLI operations, model-profile
  discovery, new commands, and command-taxonomy redesign.
- Out of scope: API or edge changes, WorkOS/Modal/Cloudflare/DNS changes, deployment, credential
  mutation, Git publication, release, and live requests.
- Evidence gap or unresolved unknown: complete deterministic-family test coverage and later live CLI
  behavior.

## Reviewer conclusion

The unchanged snapshot can proceed to lifecycle step 4. No contradiction was found in the five
owner-reviewed questions. `ACCEPT` is supportable if independently chosen by the owner. This review
does not accept the requirement or authorize implementation, live requests, external configuration,
publication, or release.
