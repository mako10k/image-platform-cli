# CLI to Native API V4 replacement revision 3 second owner review

- Date: 2026-09-09
- Lifecycle step: 4
- Status: `AWAITING_OWNER_DECISION`
- Step-2 route: `REVIEW_THEN_DECIDE`
- Requirement candidate changed since step 2: no
- Independent-review status: `COMPLETED`

## Exact decision subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v3.md` | `fdbb8f28bc33e39dc4f2a44c12616730b556fa5fffa19582a184bc110569a60b` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v3-self-review.md` | `f674ee546ca2ff98072f2a3452200d0d9179376f7d95902fc9f322879de6188d` |
| First owner-review packet | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v3-first-owner-review.md` | `5df33e146d39e4471240f7f1d260ff6970e4045ee155fadfa62979d379da5d59` |
| First owner-review result | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v3-first-owner-review-result.md` | `ea60be44217df6c30afe62c8fc737abee2c52941545eff3ebed91a8a08df695e` |
| Independent review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v3-independent-review.md` | `7c962d7f9cbb4d107c25658485c14a611469d3e86c5c72a08c8881e285e6a049` |

## Independent-review result

The reviewer found no contradiction:

1. WorkOS OAuth transport remains allowed while image-platform product API traffic is V4-only;
2. Native API V1, `/v2beta`, provider-compatible, worker and direct-Modal fallback remains
   prohibited for `image4`;
3. `image` still switches atomically between complete `image1` and `image4` implementations;
4. all 47 current leaf commands require an accepted parity disposition before cutover;
5. `common` remains internal and the existing Pylint clone check retains semantic review; and
6. cutover, rollback, live smoke and release keep separate authority.

Two later evidence gaps remain gated:

- the complete command parity matrix against 33 accepted V4 bindings and local/common behavior; and
- stabilization criteria for eventual `image1` removal.

Neither permits cutover or removal by implication.

## Owner decision

Choose exactly one:

- `REVISE`: return to step 1 for any requirement-text change;
- `REREVIEW`: keep the requirement digest unchanged, add or change a review question, and return to
  step 3; or
- `ACCEPT`: accept only requirement revision 3 at SHA-256
  `fdbb8f28bc33e39dc4f2a44c12616730b556fa5fffa19582a184bc110569a60b`.

The supported recommendation is `ACCEPT`. Acceptance fixes the replacement requirement only. It
does not authorize implementation, parity-matrix acceptance, live requests, credential changes,
cutover, publication, deployment or release.
