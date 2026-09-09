# CLI to Native API V4 replacement revision 3 independent review

- Date: 2026-09-09
- Lifecycle step: 3
- Status: `COMPLETED`
- Owner route: `REVIEW_THEN_DECIDE`
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v3.md`
- Verified candidate SHA-256: `fdbb8f28bc33e39dc4f2a44c12616730b556fa5fffa19582a184bc110569a60b`
- Candidate changed by reviewer: no

## Results

### 1. OAuth and product API transport

Classification: no contradiction.

Revision 3 limits the V4-only rule to image-platform product API operations. It explicitly retains
WorkOS Device Authorization, token refresh and issuer/JWKS access under the accepted public
OAuth-client contract. Those identity-provider requests cannot be interpreted as a V1 or
provider-compatible product API fallback.

The prohibition on Native API V1, `/v2beta`, provider-compatible endpoints, workers and direct Modal
calls remains complete for `image4` product API operations.

### 2. Revision 2 contradiction closure

Classification: no contradiction.

Mechanical comparison confirms that revision 3 changes only revision/provenance metadata and the
bounded OAuth wording correction. The previous all-network V4 restriction is gone, while the
intended product API restriction remains decidable.

### 3. Dispatcher, preservation and parity

Classification: no contradiction.

`image` delegates wholly to `image1` before cutover and wholly to `image4` afterward. `image1`
characterization preserves current behavior. Every one of the 47 current leaf commands must receive
one accepted disposition against the 33 V4 bindings or local/common behavior; an unresolved row
blocks cutover. This prevents silent command loss and a partially migrated default CLI.

Evidence gap or unresolved unknown: the complete parity matrix has not yet been authored. It remains
explicitly gated before cutover and does not constitute implicit acceptance.

### 4. Common code and clone detection

Classification: no contradiction.

`common` remains internal and accepts only API-version-independent contracts. Version-specific
paths, wires, envelopes, headers, receipts and availability remain isolated. The existing Pylint
eight-line duplicate-code check supplies mechanical detection while semantic review controls
abstraction.

### 5. Cutover, rollback and namespace

Classification: no contradiction.

The packaged delegate provides one default cutover boundary. `image1` and `image4` are explicit
transitional names selected by the owner; `image` remains the stable supported command. Cutover,
live smoke and release each retain separate authorization.

Evidence gap or unresolved unknown: stabilization criteria and the exact release that removes
`image1` remain a later decision. The first cutover release retains `image1`, and no removal is
authorized by revision 3.

- Optional or future candidate: separate common-library distribution, an additional clone checker,
  and final `image1` removal criteria.
- Out of scope: API/edge/identity-provider/cloud changes, live requests, credential mutation,
  publication, deployment and release.

## Reviewer conclusion

The revision 2 contradiction is resolved. No contradiction was found in the unchanged revision 3
snapshot. The two evidence gaps remain explicitly gated and do not prevent requirement acceptance.
The candidate can proceed to lifecycle step 4, and `ACCEPT` is supportable if independently chosen
by the owner.

This review does not accept the requirement or authorize implementation or any external effect.
