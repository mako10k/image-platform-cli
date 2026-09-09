# CLI to Native API V4 replacement revision 4 first owner review

- Date: 2026-09-09
- Lifecycle step: 2
- Status: `AWAITING_OWNER_ROUTE`
- Requirement text changed after revision 3 review: yes

## Exact review subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v4.md` | `7573da268d788eb52788b118bab3f9a12aff32af792cc87a24b5dbbf5b88c7c8` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v4-self-review.md` | `2603fae82b284066994e339f99bdffeb9510ca5cffe8239d97dfd7ff94c466e1` |

## Source provenance and prior authority

Revision 4 retains the accepted Native API V4 requirement and design and the accepted CLI
authentication contract as normative sources. Current CLI commit `1f298f3` supplies the functional
inventory for `image1`; it is not a V4 contract or output-compatibility authority.

Revision 3 remains unaccepted. Its step-4 `REVISE` disposition supplies the owner decisions applied
here: cutover follows complete `image1` functional coverage, the controls should be proportional,
and output compatibility is excluded because no application currently depends on the CLI.

## In-scope and out-of-scope behavior

In scope:

- `image` as a thin packaged dispatcher from `image1` to `image4`;
- internal `common`, `v1` and `v4` code boundaries;
- every current leaf command inventoried into a complete functional-capability matrix;
- Native API V4-only product API traffic with accepted WorkOS OAuth transport;
- shared credential identity and configuration contracts;
- the existing Pylint clone detector; and
- two cutover-readiness conditions: tested capability coverage and built-package dispatcher proof.

Out of scope:

- compatibility of command names, options, stdout, stderr, JSON, help text and exit status;
- implementation, live requests, credentials, deployment, release and Git publication;
- API, OAuth-edge, WorkOS, Modal, Cloudflare or DNS changes; and
- a mandatory post-cutover retention window for `image1`.

## Acceptance criteria and unknowns

The candidate is acceptable only if capability coverage can prove that every operation available
through the current CLI remains reachable in `image4`, while allowing its command structure and
presentation to change. Image-result correctness and accepted Native API V4 contract checks remain
required; matching `image1` output does not.

The functional-coverage matrix is not yet authored. Release-time rollback and any live authenticated
smoke set also remain undecided. Those are later design, verification or release inputs and do not
authorize an effect through this review.

## Proposed independent-review questions

1. Does the capability definition preserve every operation available through the current leaf
   commands while allowing commands and output presentation to change?
2. Is output compatibility fully removed without weakening image-result correctness or Native API V4
   contract verification?
3. Are the two cutover-readiness conditions sufficient and free of duplicated approval gates?
4. Does `image4` remain V4-only for product API traffic while accepted WorkOS OAuth transport remains
   possible?
5. Are shared code, credentials, clone detection, rollback and later-effect boundaries internally
   consistent with the narrower compatibility premise?

## Owner route

Choose exactly one:

- `REVISE`: return directly to candidate authoring;
- `REVIEW_THEN_REVISE`: add owner questions, independently review, then return to authoring;
- `REVIEW_THEN_DECIDE`: add owner questions if needed, independently review, then return for the
  second owner decision; or
- `REVIEW`: independently review without added questions, then return for the second owner decision.

The recommended route is `REVIEW_THEN_DECIDE`: revision 4 materially changes the coverage and
cutover contract, so an independent contradiction check should return to the owner before acceptance.

Independent review cannot edit or accept the requirement. This review authorizes no implementation,
external request, credential change, Git publication, deployment or release.
