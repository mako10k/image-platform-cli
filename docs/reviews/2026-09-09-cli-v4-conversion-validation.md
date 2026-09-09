# V4 conversion increment validation

Date: 2026-09-09. Authority: accepted CLI requirement v6 and owner continuation instruction.
Starting CLI commit: e39c1ed. API contract and fixture source: local API commit 5d053dd.

Implemented image4 edit convert through POST /v4/image-operations. Supports PNG, JPEG and WebP,
quality 1 through 100 for JPEG/WebP, and fixed PNG quality 90. The normalized conversion program
is exported from DeterministicEditProgram with its explicit raster and encoding defaults. The CLI
ships that small data snapshot and changes only the requested format/quality. No private API or
worker dependency is introduced.

Verification binds the source hash, requested normalized program/command hashes, output bytes,
MIME and geometry to the execution receipt and required headers. When the optional planner receipt
is present, its logical identity, single node geometry/command/program and graph header must agree.
The graph hash is cross-checked with its header; the CLI does not re-execute the server planner or
prove intermediate pixels from a lossy encoded result. No generic edit/run coverage is claimed.

Validation: 235 tests passed, including 27 added conversion cases; Ruff, strict Mypy, Xenon and
Pylint duplicate-code passed. Seven fixtures were generated through the real local CPU API,
covering default encoding for all formats and JPEG/WebP quality boundaries. The negative-cost
case initially exposed string-serialized decimals bypassing schema numeric constraints. The client
now explicitly validates finite nonnegative actual and estimated costs with the existing numeric
validator; negative and nonfinite regression cases pass before output creation.

Built /tmp/cli-convert-package/image_platform_cli-0.1.0-py3-none-any.whl and installed it offline
into /tmp/cli-v6-package/venv. Outside the checkout, verified installed package origin, parsed each
format, matched the V4 request to its fixture and saved/opened all three output formats. Image
continues to delegate to image1. Coverage matrix v6 retains 17 missing rows.

No public request, paid provider call, push, release, deployment or default switch occurred.
Fixture verification establishes local CPU/client behavior, not public-edge behavior.

## Snapshot hashes

- `src/image_platform_cli/v4/conversion_program.json`: `b7538e60daffe0b29c97ecc3742d155bdb3923d24eeaf8310ad0a4d28dda99c6`
- `tests/fixtures/conversion/cli-convert-jpeg-1.json`: `41f9a4ff5ebd50cf9c9ff9cf49e6f961caa4d5bbf07395c701c01e2cdfe12071`
- `tests/fixtures/conversion/cli-convert-jpeg-100.json`: `21784a4b10de1bc497b96831a47331b781e28b55c8252b7f0b175751a8e1001f`
- `tests/fixtures/conversion/cli-convert-jpeg-90.json`: `aa08953a936dc1f28d9fe42acf0a76e9f544dfa56483c355a27ff63c55cd5bde`
- `tests/fixtures/conversion/cli-convert-png-90.json`: `75390be8f4fd65384b62ecb17e3abea2017e3e4e0e90be26ce8f5276be30f1ac`
- `tests/fixtures/conversion/cli-convert-webp-1.json`: `a5ccd6149e1f98d06694ba7183e50ddc1048b11d03dfc91f865f717e2957635b`
- `tests/fixtures/conversion/cli-convert-webp-100.json`: `64dc2b1711ca87e9ffee200abca474b2e8013573d8193b1d49c0ef014b5cba6e`
- `tests/fixtures/conversion/cli-convert-webp-90.json`: `39f0a5d5b33804a8a5c610f6d558adbe6bf45ea40e599bf811074127a4bed06f`
