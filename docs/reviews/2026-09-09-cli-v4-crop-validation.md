# V4 raster crop increment validation

Date: 2026-09-09. Authority: accepted CLI requirement v6 and owner's continuation instruction.
Starting CLI commit: 5a08d20951ace663ae1354381cb29049b775c2ca. API fixture source: 5d053dd.

Implemented image4 edit raster crop through POST /v4/image-operations with exact integer rectangle
coordinates and PNG output. Rectangles may extend outside the source; the existing API's transparent
padding behavior is retained. Coordinates and bounded positive output dimensions are checked locally.
The dry-run prints the program before configuration, authentication, HTTP or input-file reading.
Normal execution requires an available output destination.

Extracted the conversion single-command request/receipt checks into V4 single_edits. Source hashes,
normalized program and command identities, output bytes/MIME/dimensions, costs and execution/planner
headers are checked. Expected output dimensions are now supplied separately from source dimensions;
planner node input dimensions remain those of the source. This is a shared helper for the two
implemented commands, not generic edit/run capability coverage. V1 remains unchanged.

Validation: 250 tests passed, including 15 new crop cases. Ruff, strict Mypy, Xenon and Pylint
 duplicate-code checks passed. Three fixtures were produced via the real local CPU API for inside,
partially outside and wholly outside rectangles. Output pixels match the expected crop/padding.
Conversion's format, quality and malformed-response regression tests remain passing.

Built /tmp/cli-crop-package/image_platform_cli-0.1.0-py3-none-any.whl and installed offline into
/tmp/cli-v6-package/venv. Outside the checkout, verified package origin, parser, offline dry-run,
V4 fixture request and a saved 5x4 PNG with transparent padding. Stable image still delegates to
image1. Coverage matrix v7 retains 16 missing rows.

No public request, paid provider execution, push, release, deployment or default switch occurred.
Local CPU/fixture checks do not establish public-edge behavior.

## Fixture hashes

- `tests/fixtures/crop/cli-crop-inside.json`: `fb9a09357a13227b2e811b57eead03dbe58cdc4cc688e480b4c138d6cc9a846d`
- `tests/fixtures/crop/cli-crop-outside.json`: `b1d3ca7583538d02dc5a93b9e9a34988977652a84484c66e19a59b065ee327b7`
- `tests/fixtures/crop/cli-crop-padding.json`: `bf9448533a8033d27276be7c708ba20ab03e32c63cf9f5e5bcfb142fd9713ee4`
