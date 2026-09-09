# V4 image composition focused validation

Date: 2026-09-09. Authority: accepted CLI requirement v6, owner continuation and focused-test limit.
Starting CLI commit: 6928add. API contract and fixture source: local API commit 5d053dd.

Implemented image4 edit composite via POST /v4/image-operations with background, overlay, optional
mask, six affine coefficients, opacity, four blend modes and optional final crop. Programs use
explicit bicubic interpolation, transparent border, normalized mask coverage and PNG encoding.
The background is bound as the source image internally. Local checks preserve supported matrix,
opacity and crop bounds; destination safety uses the existing CLI preflight/exclusive save.

Generalized command verification from one command to an ordered command list within one physical
step. Each ID, operation and normalized command hash is checked, as is the planner's command list.
This verifies paste plus optional crop without claiming generic multi-step edit/run completion.
Existing named-input checks cover source, overlay and optional mask. No V1 or default change.

## Focused checks

82 tests passed from tests/test_v4_compositing.py (20 new cases), tests/test_v4_conversion.py,
tests/test_v4_crop.py, tests/test_v4_color_matching.py and tests/test_v4_cli.py. This covers the
changed command verifier with existing one-command cases, geometry changes, multiple inputs and
parser composition. Five local CPU fixtures cover source_over/replace/multiply/screen and a combined
translated, masked, opacity 0.5, cropped result. Missing/reordered crop commands, incorrect command
hashes, mask/overlay hashes, planner command lists and dimensions are rejected before saving.

Ruff passed on changed source/test files. Strict Mypy with --follow-imports=silent passed for four
changed source files. git diff --check passed. No full-suite, repository-wide static/clone or package
checks were rerun. Those broader checks remain pending for eventual cutover acceptance.

Coverage matrix v14 retains nine missing rows. Image remains image1. No public request, paid provider
call, push, release, deployment or default switch occurred.

## Fixture hashes

- `tests/fixtures/composite/cli-composite-masked-crop.json`: `6e5e227136a88bc6ec8cbdcb1b0492f7fac08edacd146ae2dfddf2fa7cb172a8`
- `tests/fixtures/composite/cli-composite-multiply.json`: `f42fbc6efca667fec2912ed954141da0c6ae5831f02e7c14e72ad4d252d702d3`
- `tests/fixtures/composite/cli-composite-replace.json`: `151dceba94c1218b29d34f6849dbdfd5e6136535f0c8120b0c0885fc5665ff6f`
- `tests/fixtures/composite/cli-composite-screen.json`: `65d31cf02558b216918950ab57c14dedb7c155025d7beea75a85ebbd2b765028`
- `tests/fixtures/composite/cli-composite-source_over.json`: `88d37ff48b9c97cf2511553881d964cb5204798f6c38661137fddce9b324a4b8`
