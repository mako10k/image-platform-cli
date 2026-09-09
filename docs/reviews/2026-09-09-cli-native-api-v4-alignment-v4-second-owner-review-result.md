# CLI to Native API V4 replacement revision 4 second owner-review result

- Date: 2026-09-09
- Lifecycle step: 4 result
- Owner response: `REVISE`
- Owner route: `REVISE`
- Requirement candidate changed: no
- Next step: return to step 1 with requirement revision 5

## Owner disposition

Revision 4 is not accepted. The independent review found that its issuer-plus-organization
credential identity contradicts the accepted authentication contract, which requires issuer plus
user subject plus organization ID. The owner selected `REVISE`.

Revision 5 is limited to correcting that credential identity and required revision/provenance
metadata. Revision 4's output-compatibility exclusion, functional-capability coverage, proportional
cutover-readiness conditions, V4/OAuth boundary, shared-code boundary and clone-detection decision
remain unchanged.

This disposition authorizes no implementation, credential mutation, external request, cutover,
publication, deployment or release. Revision 4 remains an unchanged review record at SHA-256
`7573da268d788eb52788b118bab3f9a12aff32af792cc87a24b5dbbf5b88c7c8`.
