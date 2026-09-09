# CLI to Native API V4 replacement revision 3 second owner-review result

- Date: 2026-09-09
- Lifecycle step: 4 result
- Owner response: `REVISE`
- Owner route: `REVISE`
- Requirement candidate changed: no
- Next step: return to step 1 with requirement revision 4

## Owner disposition

Revision 3 is not accepted. The owner found that its cutover controls were stricter than the actual
product state and clarified the governing requirement:

- default cutover belongs after `image4` covers the functionality of `image1`;
- no application currently depends on `image` or `image1`; and
- output compatibility with `image1` must therefore be excluded from the evaluation.

This disposition rejects command-by-command output parity, exact stdout/stderr/exit-status matching,
and a mandatory post-cutover `image1` retention window as requirement-level cutover conditions.
It does not weaken Native API V4 contract correctness or authorize implementation or cutover.

Requirement revision 4 must restart at lifecycle step 1. Revision 3 remains an unchanged review
record at SHA-256 `fdbb8f28bc33e39dc4f2a44c12616730b556fa5fffa19582a184bc110569a60b`.
