# CLI to Native API V4 replacement revision 5 self-review

- Date: 2026-09-09
- Lifecycle step: 1 self-review
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v5.md`
- Candidate SHA-256: `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6`
- Result: `PASS_FOR_FIRST_OWNER_REVIEW`

## Revision boundary

PASS. Mechanical comparison with revision 4 shows only:

- required revision and predecessor metadata;
- the revision 4 `REVISE` disposition and its digest; and
- correction of credential account identity from issuer plus organization to issuer plus user
  subject plus organization ID.

Output-compatibility exclusions, functional-capability coverage, the two cutover-readiness
conditions, dispatcher lifecycle, V4/OAuth traffic boundary, internal `common` boundary and clone
detection are unchanged.

## Contradiction closure

PASS. The accepted authentication contract requires service `image-platform` and an account keyed by
issuer plus user subject plus organization ID. Revision 5 states the same identity and applies it to
the credential store shared by `image1` and `image4`. The same issuer and organization can therefore
retain distinct credentials for distinct user subjects.

## Provenance, scope and namespace

PASS. The accepted Native API V4 requirement, V4 design and CLI authentication contract remain the
normative sources with unchanged verified digests. Revision 4 remains unchanged and unaccepted.
Current implementation commit `1f298f3` remains only the functional inventory source for `image1`.

No product, API or executable namespace changes. `image`, `image1` and `image4` retain their revision
4 meanings. Implementation, live requests, credential mutation, cutover, Git publication,
deployment and release remain out of scope.

## Assumptions, unknowns and acceptance criteria

The owner-supplied no-dependent-application premise remains the basis for excluding output
compatibility. The functional-coverage matrix remains unimplemented later evidence; it must include
option-driven semantic variants before a no-`missing` cutover claim. Release-time rollback and any
live smoke set also remain later decisions.

All revision 4 acceptance criteria remain decidable. The credential criterion now directly matches
the accepted authentication contract.

## Proposed independent-review input

The reviewer should receive only this digest-pinned candidate and the first-owner packet. It should
answer:

1. Does revision 5 exactly close the credential-identity contradiction by requiring issuer plus user
   subject plus organization ID?
2. Is the revision otherwise normatively unchanged from revision 4?
3. Does the corrected credential identity remain compatible with the internal shared-authentication
   boundary without adding output compatibility?
4. Do the prior functional-coverage, cutover-readiness and V4/OAuth conclusions remain valid?

Findings must be classified as contradiction, evidence gap or unresolved unknown, optional or future
candidate, or out of scope. They must not be inserted into the candidate automatically.
