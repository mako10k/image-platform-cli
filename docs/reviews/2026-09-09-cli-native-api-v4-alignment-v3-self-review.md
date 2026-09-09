# CLI to Native API V4 replacement revision 3 self-review

- Date: 2026-09-09
- Lifecycle step: 1 self-review
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v3.md`
- Candidate SHA-256: `fdbb8f28bc33e39dc4f2a44c12616730b556fa5fffa19582a184bc110569a60b`
- Result: `PASS_FOR_FIRST_OWNER_REVIEW`

## Revision boundary

PASS. The content differs from reviewed revision 2 only in required revision/provenance metadata and
the bounded correction requested by the owner:

- V4-only routing applies to image-platform product API operations; and
- accepted WorkOS Device Authorization, token refresh and issuer/JWKS transport remains permitted
  and is not treated as an API fallback.

The dispatcher, entrypoint lifecycle, command parity, common-code boundary, credential identity,
clone detection, cutover and rollback text is otherwise unchanged.

## Contradiction closure

PASS. Revision 2 prohibited all non-V4 network operations when read literally while separately
requiring WorkOS OAuth. Revision 3 distinguishes authentication-provider transport from
image-platform product API transport. It now permits the network behavior required by the accepted
authentication contract while continuing to prohibit V1, `/v2beta`, provider-compatible, worker and
direct Modal product API fallback.

## Source provenance and namespace

PASS. Revision 3 records reviewed revision 2 and preserves the accepted Native API V4 and
authentication sources. `image1` and `image4` remain explicit transitional executable names;
`image` remains the stable supported command. No additional external name or API version is added.

## Remaining evidence gaps

The 47 current leaf commands still require a complete parity matrix against the 33 accepted V4
bindings and local/common behavior before cutover. Post-cutover stabilization criteria for removing
`image1` also remain undefined. Both are still gated and neither is hidden by the OAuth correction.

## Proposed independent-review input

The reviewer should receive only this digest-pinned candidate and the first-owner packet. It should
recheck:

1. whether image-platform product API operations are V4-only without prohibiting accepted WorkOS
   OAuth transport;
2. whether the dispatcher prevents a partially migrated default CLI;
3. whether `image1` preservation, parity blockers and `image4` no-fallback remain decidable;
4. whether `common` and duplicate-code controls preserve semantic boundaries; and
5. whether cutover, rollback and new executable names remain explicitly governed.

Findings must be classified as contradiction, evidence gap or unresolved unknown, optional or
future candidate, or out of scope. They must not be inserted into the requirement automatically.
