# CLI to Native API V4 replacement revision 3 first owner review

- Date: 2026-09-09
- Lifecycle step: 2
- Status: `AWAITING_OWNER_ROUTE`
- Requirement text changed after revision 2 review: yes

## Exact review subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v3.md` | `fdbb8f28bc33e39dc4f2a44c12616730b556fa5fffa19582a184bc110569a60b` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v3-self-review.md` | `f674ee546ca2ff98072f2a3452200d0d9179376f7d95902fc9f322879de6188d` |

## Revision 3 correction

Revision 3 retains the parallel `image1`/`image4` replacement, internal `common` package, parity
blocker, existing clone checker, atomic default cutover and rollback conditions from revision 2.

It changes the contradictory network rule only:

- image-platform product API operations from `image4` must use accepted V4 bindings;
- WorkOS Device Authorization, refresh and issuer/JWKS access continue through the accepted OAuth
  transport; and
- WorkOS traffic is not a product API fallback.

## Acceptance criteria and remaining unknowns

The correction closes the only contradiction found in revision 2. The complete command parity
matrix and final `image1` removal criteria remain later evidence gates. They do not authorize silent
command removal or cutover.

## Proposed independent-review questions

1. Does the corrected rule permit required WorkOS OAuth traffic while keeping image-platform product
   API traffic V4-only?
2. Is the revision 2 contradiction fully removed without weakening V1/provider/direct-Modal fallback
   prohibitions?
3. Are dispatcher, parity, common-code, clone-detection, cutover and rollback requirements otherwise
   unchanged and internally consistent?
4. Have the remaining parity and stabilization unknowns stayed gated rather than becoming implicit
   acceptance?

## Owner route

Choose exactly one:

- `REVISE`: return directly to candidate authoring;
- `REVIEW_THEN_REVISE`: add owner questions, independently review, then return to authoring;
- `REVIEW_THEN_DECIDE`: add owner questions, independently review, then return for the second owner
  decision; or
- `REVIEW`: independently review the questions above, then return for the second owner decision.

The recommended route is `REVIEW_THEN_DECIDE`, matching the owner's requested revise-and-review
intent while returning the completed review for a final decision on the new digest.

Independent review cannot edit or accept the requirement. This review authorizes no implementation
or external effect.
