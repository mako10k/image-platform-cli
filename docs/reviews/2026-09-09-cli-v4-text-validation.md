# V4 text drawing focused validation

Date: 2026-09-09. Authority: accepted CLI requirement v6 and owner continuation, explicitly limited
this increment to impact-focused tests rather than a full-suite run. Starting CLI commit: e5be022.
API contract and fixture source: local API commit 5d053dd.

Implemented image4 edit raster text through POST /v4/image-operations. Supports text, position,
registered font ID/SHA-256/size, RGBA fill, optional stroke and stroke width. The normalized command
includes coverage=null and preserves PNG output and source geometry. Local checks reject invalid
text length, font identity, position, size, stroke width and color before input-file reading or HTTP.
The existing V4 receipt verification binds command and program hashes to those requested controls.
Offline preview executes before configuration, authentication, HTTP or input reading.

Two response fixtures were generated through the real local CPU API, using DejaVuSans and font
SHA-256 ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280. They exercise fill and
stroke drawing; the font binary is not included. Unicode preservation is verified in request preview,
not as a claim of glyph coverage for this font.

## Focused checks

41 tests passed from:
- tests/test_v4_text_drawing.py (16 new cases)
- tests/test_v4_shapes.py (shared RGBA validation and sibling routing)
- tests/test_v4_cli.py (shared parser composition)
- tests/test_v4_crop.py::test_crop_dry_run_has_no_configuration_network_or_input_read
- tests/test_v4_grayscale.py::test_grayscale_offline_preview_and_required_output
- tests/test_v4_filtering.py::test_filter_offline_preview

Ruff passed for the changed API, edit CLI, text drawing and test files. Strict Mypy passed for
three changed source files with --follow-imports=silent. git diff --check passed.
No full-suite, repository-wide static/duplicate-code or built-wheel checks were rerun, as requested.
Earlier full-suite results are historical evidence and are not presented as results for this commit.
Broader integration and package verification remain for eventual cutover acceptance.

Image remains image1. Coverage matrix v11 retains 12 missing capability rows. No public request,
paid provider call, push, release, deployment or default switch occurred.

## Fixture hashes

- `tests/fixtures/text/cli-text-fill.json`: `52fb03d803e273b3f47f2296a6fc7e2e0a5bb57d1bcbd1ce5ea494f41cd1c1a7`
- `tests/fixtures/text/cli-text-stroke.json`: `75d25eb503ec51281a49f239befc183b368ac398af22685fc81346fd20535938`
