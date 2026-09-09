# CLI to Native API V4 replacement revision 4 second owner review

- Date: 2026-09-09
- Lifecycle step: 4
- Status: `AWAITING_OWNER_DECISION`
- Step-2 route: `REVIEW_THEN_DECIDE`
- Requirement candidate changed since step 2: no
- Independent-review status: `COMPLETED`

## Exact decision subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v4.md` | `7573da268d788eb52788b118bab3f9a12aff32af792cc87a24b5dbbf5b88c7c8` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v4-self-review.md` | `2603fae82b284066994e339f99bdffeb9510ca5cffe8239d97dfd7ff94c466e1` |
| First owner-review packet | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v4-first-owner-review.md` | `18bd3ee046c03bcf8d45d929165cf45651ab515bda44261e8e5d58206ed2e374` |
| First owner-review result | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v4-first-owner-review-result.md` | `9ed696a079eb6932f029b06752ebbf4d5559734ebfd17fcfae84e9d196fd9ba8` |
| Independent review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v4-independent-review.md` | `e7d2d98f9ddc51b62b75892f9fb8ff33f92540e1baf7d2c16605a72b92917331` |

## Independent-review result

The reviewer confirmed the intended revision 4 changes:

1. functional capabilities are a workable coverage unit while every current leaf command remains an
   inventory input;
2. output, presentation, command-shape and exit-status compatibility are excluded without weakening
   artifact correctness or Native API V4 protocol validation;
3. the two readiness conditions cover distinct implementation claims without duplicated approval
   gates; and
4. image-platform product traffic remains V4-only while accepted WorkOS OAuth traffic remains
   permitted.

One contradiction with the accepted authentication contract was found. Revision 4 says the shared
credential account identity is issuer plus organization. The accepted contract requires issuer plus
user subject plus organization ID. Omitting user subject could cause two users in one organization
to address the same stored credential.

One later evidence gap remains: the functional-coverage matrix must demonstrate that option-driven
semantic variants are inventoried. The existing no-`missing` readiness rule already blocks a cutover
claim until that evidence exists, so no additional requirement gate was proposed.

## Owner decision

Choose exactly one:

- `REVISE`: return to step 1 and correct the credential identity in a new requirement revision;
- `REREVIEW`: keep the requirement digest unchanged, add or change a review question, and return to
  step 3; or
- `ACCEPT`: accept only requirement revision 4 at SHA-256
  `7573da268d788eb52788b118bab3f9a12aff32af792cc87a24b5dbbf5b88c7c8`.

The supported recommendation is `REVISE`, because `ACCEPT` would preserve a direct contradiction
with the normative authentication contract. The bounded revision is to use issuer plus user subject
plus organization ID; the output-compatibility and cutover-readiness decisions need no change.

This decision authorizes no implementation, functional-coverage matrix, external request,
credential change, cutover, Git publication, deployment or release.
