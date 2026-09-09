# CLI to Native API V4 alignment revision 1 second owner-review result

- Date: 2026-09-09
- Lifecycle step: 4 result
- Owner decision: `REVISE`
- Owner direction: preserve `image` as a thin placeholder, name the current implementation
  `image1`, build `image4` in parallel, share version-independent code, and change the
  `image` binding to `image4` only at the final cutover
- Accepted candidate: no
- Candidate SHA-256: `674a316d49b7f05423dc230638528a3be50c582366a7828466d9711a50cfe224`
- Historical candidate changed: no
- Next step: lifecycle step 1 with requirement revision 2

The owner found no useful product state in exposing a partially V4-updated existing CLI. Revision 1
therefore remains an unaccepted historical snapshot. Its completed review does not carry forward to
revision 2.
