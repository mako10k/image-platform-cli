# CLI to Native API V4 replacement revision 5 second owner review

- Date: 2026-09-09
- Lifecycle step: 4
- Status: `AWAITING_OWNER_DECISION`
- Step-2 route: `REVIEW_THEN_DECIDE`
- Requirement candidate changed since step 2: no
- Independent-review status: `COMPLETED`

## Exact decision subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v5.md` | `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v5-self-review.md` | `f771573b891f1ffc97b3a8c3365cc4c468ca0a69ce1ef313f2aee78670ed8b79` |
| First owner-review packet | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v5-first-owner-review.md` | `416b06a2aa5f0675d0231d1fa8d41fe01bac8a8e80f11f8587b0d2163572c5fa` |
| First owner-review result | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v5-first-owner-review-result.md` | `2e7dff472f487735832a1ebb36751a6964860bdef5e4aac6dfafd9cc0891e8b0` |
| Independent review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v5-independent-review.md` | `4d3357e6d9d11c037110ee5e235fe179e883288a2802424536afa22a4b2bb48d` |

## Independent-review result

The reviewer found no contradiction:

1. credential identity now exactly follows the accepted authentication contract: service
   `image-platform`, account keyed by issuer plus user subject plus organization ID;
2. revision 5 otherwise preserves revision 4's normative content;
3. the correction fits the internal shared-authentication boundary and adds no output-compatibility
   promise; and
4. the functional-coverage, proportional cutover-readiness and V4/OAuth conclusions remain valid.

Two later evidence gaps remain explicit:

- the functional-coverage matrix must inventory leaf commands and option-driven semantic variants
  before a no-`missing` cutover claim; and
- the current two-part credential key implementation must be replaced by a subject-aware three-part
  design and verified during implementation.

These gaps do not contradict revision 5 or prevent requirement acceptance. They prevent later
implementation or cutover claims until the corresponding evidence exists.

## Owner decision

Choose exactly one:

- `REVISE`: return to step 1 for any requirement-text change;
- `REREVIEW`: keep the requirement digest unchanged, add or change a review question, and return to
  step 3; or
- `ACCEPT`: accept only requirement revision 5 at SHA-256
  `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6`.

The supported recommendation is `ACCEPT`. Acceptance fixes the replacement requirement only. It
does not authorize implementation, the functional-coverage matrix, credentials, live requests,
cutover, Git publication, deployment or release.
