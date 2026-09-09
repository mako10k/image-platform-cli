# V4 color matching focused validation

Date: 2026-09-09. Authority: accepted CLI requirement v6, owner continuation and focused-test limit.
Starting CLI commit: da4d5fb. API contract and fixture source: local API commit 5d053dd.

Implemented image4 edit raster color-match via POST /v4/image-operations with reference image,
lab_mean_std_v1 and lab_histogram_256_v1, finite strength zero through one, preserve-luminance and
offline preview. The normalized command includes coverage=null. Source dimensions, alpha and PNG
output are retained; the reference may have different dimensions.

Extended shared single-command input preparation to explicit extra named inputs, rejecting source
replacement or mismatched program bindings. Receipt verification compares the complete expected
input hash mapping, including reference. It continues to verify program/command identity, output
and headers. No private API dependency, V1 change or default dispatcher change was made.

## Focused checks

62 tests passed from tests/test_v4_color_matching.py (16 new cases), tests/test_v4_conversion.py,
tests/test_v4_crop.py and tests/test_v4_cli.py. These cover the new two-input path, shared preparation
and receipt regressions, changed output geometry and parser composition. Five fixtures were generated
via the real local CPU API, including both algorithms, partial strength with luminance preservation
and zero strength. Missing/swapped/altered input hashes, bad program/geometry and invalid strengths
are rejected before output creation. Offline preview reads neither input nor configuration.

Ruff passed for the changed source/test files. Strict Mypy with --follow-imports=silent passed for
four changed source files. git diff --check passed. Per owner instruction, no full-suite,
repository-wide static/duplicate-code or package verification was rerun. Those broader checks remain
for overall cutover acceptance; historical full-suite results are not current-commit evidence.

Coverage matrix v12 retains 11 missing rows. Image remains image1. No public request, paid provider
call, push, release, deployment or default switch occurred.

## Fixture hashes

- `tests/fixtures/color-match/cli-colormatch-lab_histogram_256_v1-0.5.json`: `e76d442e06b24e456120efffefab29a665bd829f36738ba365ac730951649fa2`
- `tests/fixtures/color-match/cli-colormatch-lab_histogram_256_v1-1.json`: `67a1792c3adcae6b7a60e8116708a32ed5860cc5b98f34a0ab0855c0ea368d7a`
- `tests/fixtures/color-match/cli-colormatch-lab_mean_std_v1-0.5.json`: `feeb90886ae4db6a4735f67334888f67a2f484f27b3e3dd5d2254fb35e6175a7`
- `tests/fixtures/color-match/cli-colormatch-lab_mean_std_v1-0.json`: `b63f38c0aeece5ddb65bdef9e8e99440246d80fc4d34844f159385e548a58b7f`
- `tests/fixtures/color-match/cli-colormatch-lab_mean_std_v1-1.json`: `dfb7413e87f2e39767bd274bcd78ef343c1cab6fc1c960c671774dac98ce30ae`
