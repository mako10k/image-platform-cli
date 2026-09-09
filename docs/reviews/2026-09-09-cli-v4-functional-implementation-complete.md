# Image4 functional implementation completion

Date: 2026-09-09. Task: T_CLI_V4_ALIGNMENT.
Requirement: accepted CLI revision 6, SHA-256
`711a4db7b98b14739f73bd5ce4d9fc6f7f450c7de708f38dc115a113acfaed5e`.
Current coverage: `docs/design/cli-v4-functional-coverage.v19.md`.

## Result and scope

All 49 V1 canonical leaf commands are represented in the 37-row functional matrix: two
local/common rows, 35 V4-bound rows, zero missing rows. A direct parser traversal found no missing
V1 command path in V4 (51 V4 leaves, with model-profiles and explicit preview-access added).
This is supporting inventory evidence, not a command/output compatibility requirement.

The owner requested continuous execution with incremental local commits and focused impact tests.
The remaining implementation is complete under that validation boundary. The broader acceptance
of T_CLI_V4_ALIGNMENT is still pending; this record does not close its PERT task or authorize cutover.
The image dispatcher still imports v1.cli.main, and no external publication or runtime selection
was performed.

## Increment evidence

| Local commit | Result | Focused verification |
| --- | --- | --- |
| ff26de7 | Shared affine geometry; V4 resize, flip, rotate, canvas | 26 passed, 29 deselected; 8 local CPU fixtures |
| 6492f85 | Public-schema normalization; generic run and verify | 87 passed, 57 deselected; final program-file run 53 passed |
| b548d00 | Shared raster builders; V4 adjust, auto-crop, mesh | 86 passed, 19 deselected; 7 local CPU fixtures |
| 6f3b4c4 | Shared replacement builder and V4 object/background execution | 96 passed, 20 deselected; 8 local CPU fixtures |
| 42119f9 | Campaign functional verification, completing the matrix | 53 passed, 46 deselected |

These counts describe overlapping focused runs and must not be added as unique test coverage.
The final complexity correction separated CLI preflight from dispatch and planner verification
from execution receipt verification. Its focused program/replacement/raster/geometry/CLI run
passed 109 tests. Changed-source Ruff, strict Mypy, Xenon and Pylint duplicate-code checks pass;
the final scope consists of the 12 Python source files changed since e31381e.

## Evidence boundaries and restart point

CPU fixtures were generated locally against the API r8 implementation at 5d053dd. Campaign tests
use fake HTTP responses validated against the exported public schema. None is evidence of the
currently deployed service, live OAuth, paid provider execution or public-edge behavior.

For split deterministic execution, V4 returns the final physical execution receipt. The CLI
verifies the logical program identity, physical subprogram hashes/order, static input hashes,
final command receipt and output bytes. Intermediate source bytes and intermediate pixel receipts
are not returned and are not independently verified. The split-response regression is a derived
contract case, not a full real split execution fixture.

No full-suite, whole-repository static or newly built package test was run in these increments,
following the owner's explicit focused-test limit. Those broader checks and whole-matrix acceptance
are the remaining cutover-readiness work. Default image-to-image4 rebinding and release require
the separate authorization stated in the accepted requirement. Continue from the current local
codex/cli-v4-alignment branch; remote publication has not been performed for these commits.
