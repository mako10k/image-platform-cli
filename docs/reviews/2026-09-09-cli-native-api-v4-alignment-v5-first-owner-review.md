# CLI to Native API V4 replacement revision 5 first owner review

- Date: 2026-09-09
- Lifecycle step: 2
- Status: `AWAITING_OWNER_ROUTE`
- Requirement text changed after revision 4 review: yes

## Exact review subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v5.md` | `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v5-self-review.md` | `f771573b891f1ffc97b3a8c3365cc4c468ca0a69ce1ef313f2aee78670ed8b79` |

## Source provenance and prior authority

Revision 5 retains the accepted Native API V4 requirement and design and the accepted CLI
authentication contract as normative sources. Revision 4 remains unaccepted after its second owner
review returned `REVISE`.

The only normative correction is the credential account identity. It now matches the accepted
authentication contract: service `image-platform`, account keyed by issuer plus user subject plus
organization ID.

## In-scope and out-of-scope behavior

In scope is the bounded credential-identity correction and confirmation that revision 4's
owner-confirmed direction remains unchanged: thin dispatcher, parallel `image1` and `image4`, internal `common`, full
functional-capability coverage without output compatibility, two cutover-readiness checks, V4-only
product traffic, accepted WorkOS OAuth traffic and initial Pylint clone detection.

Out of scope are implementation, the functional-coverage matrix, live requests, credential mutation,
cutover, Git publication, deployment and release.

## Acceptance criteria and unknowns

Revision 5 can be accepted only if the corrected account identity closes the direct authentication-
contract contradiction without changing the rest of the replacement requirement.

The later functional-coverage matrix remains an evidence gap for cutover, including option-driven
semantic variants. Release-time rollback and any live authenticated smoke set also remain later
decisions. They do not block review of the corrected requirement bytes.

## Proposed independent-review questions

1. Does revision 5 exactly close the credential-identity contradiction by requiring issuer plus user
   subject plus organization ID?
2. Is the revision otherwise normatively unchanged from revision 4?
3. Does the corrected credential identity remain compatible with the internal shared-authentication
   boundary without adding output compatibility?
4. Do the prior functional-coverage, cutover-readiness and V4/OAuth conclusions remain valid?

## Owner route

Choose exactly one:

- `REVISE`: return directly to candidate authoring;
- `REVIEW_THEN_REVISE`: add owner questions, independently review, then return to authoring;
- `REVIEW_THEN_DECIDE`: add owner questions if needed, independently review, then return for the
  second owner decision; or
- `REVIEW`: independently review without added questions, then return for the second owner decision.

The recommended route is `REVIEW_THEN_DECIDE`. The change is narrow, but it corrects a prior
high-impact contradiction with a normative authentication contract and should be independently
checked before owner acceptance.

Independent review cannot edit or accept the requirement. This review authorizes no implementation,
external request, credential change, Git publication, deployment or release.
