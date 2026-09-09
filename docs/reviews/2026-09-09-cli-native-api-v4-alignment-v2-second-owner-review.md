# CLI to Native API V4 replacement revision 2 second owner review

- Date: 2026-09-09
- Lifecycle step: 4
- Status: `AWAITING_OWNER_DECISION`
- Step-2 route: `REVIEW_THEN_DECIDE`
- Requirement candidate changed since step 2: no
- Independent-review status: `COMPLETED_WITH_CONTRADICTION`

## Exact decision subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v2.md` | `366fee5f10e0662957e7a263dc3218c879d06f844bd4216a9c67e305751587d5` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v2-self-review.md` | `20ad4150e467585eb290f94f095986fa85f461e8e0e9ed951dd9334b26892dc3` |
| First owner-review packet | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v2-first-owner-review.md` | `193ca678860672639fc6c5f26c2bbba874128c8777cd874829ce080a3789a60a` |
| First owner-review result | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v2-first-owner-review-result.md` | `1a3db686b64308cb8544037e3674f2dd9ea4e90f2a5127eafbeec79053d028e2` |
| Independent review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v2-independent-review.md` | `6592491d59d4a44c42dba5d826519a2c33610db57ef04e1b29a4895ee693fda9` |

## Independent-review result

The dispatcher, atomic default cutover, command parity blocker, internal common boundary, existing
clone checker, credential identity, and rollback gates have no contradiction.

One requirement contradiction remains. Section 5 says `image4` uses only V4 bindings for all network
operations. That wording also prohibits WorkOS OAuth device authorization, refresh and issuer/JWKS
requests required by section 6 and the accepted authentication contract.

The correction is bounded: apply the V4-only rule to **image-platform product API operations** and
explicitly retain accepted WorkOS OAuth transport. The independent reviewer did not edit the
candidate.

Two non-blocking evidence gaps remain for later phases:

- the 47 current leaf commands have not yet been assigned across the 33 V4 bindings and local/common
  behavior in a parity matrix; and
- stabilization criteria for final removal of `image1` are not yet defined.

Both already remain gated before cutover or removal.

## Owner decision

Choose exactly one:

- `REVISE`: return to step 1 and make the bounded OAuth wording correction;
- `REREVIEW`: keep the requirement bytes unchanged, add or change a review question, and return to
  step 3; or
- `ACCEPT`: unavailable because the completed review found a contradiction.

The supported recommendation is `REVISE`. Revision 3 should change only the network-operation
boundary described above and then restart lifecycle step 1. This decision authorizes no
implementation or external effect.
