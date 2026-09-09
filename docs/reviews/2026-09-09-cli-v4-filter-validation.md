# V4 raster filter increment validation

Date: 2026-09-09. Authority: accepted CLI requirement v6 and owner's continuation instruction.
Starting CLI commit: 19357cd. API contract and fixture source: local API commit 5d053dd.

Implemented image4 edit raster filter through POST /v4/image-operations. Supports gaussian_blur,
box_blur and unsharp_mask, finite radius greater than zero through 64 and finite amount zero
through 16 (default 1). Programs explicitly normalize reflect border and coverage=null and retain
PNG encoding. Offline dry-run runs before configuration, authentication, HTTP or input reading.
The matrix's missing box_blur wording was corrected against the V1 parser and API enum; this
preserves existing functionality rather than adding an unaccepted capability.

Reused the V4 single-command exchange and input/program/command/output/header/planner verification.
Invalid controls are rejected before input-file reading or HTTP. No V1 or dispatcher change.

Validation: 275 tests passed, including 18 added cases; Ruff, strict Mypy, Xenon and Pylint
 duplicate-code passed. Five fixtures were produced by the real local CPU API, covering all three
kinds with fractional radius, upper radius/amount and zero amount. Malformed receipt, dimensions,
program/header and nonfinite/out-of-range control cases are rejected before saving.

Built /tmp/cli-filter-package/image_platform_cli-0.1.0-py3-none-any.whl and installed offline in
/tmp/cli-v6-package/venv. Outside the checkout, verified installed module origin and each kind's
preview, request and saved fixture bytes. Image remains image1; coverage matrix v9 has 14 missing rows.

No public request, paid provider execution, push, release, deployment or default switch occurred.
These tests establish local CPU/client behavior, not public-edge behavior.

## Fixture hashes

- `tests/fixtures/filter/cli-filter-audit.json`: `c27d83937f9d91d9db7502355be47fd07f7364775be3a03e24589a59e1f95153`
- `tests/fixtures/filter/cli-filter-box_blur-1.5-1.json`: `b8811829671cad36844c63212b29940f271d5bd86d4619a8ec3e28640dabd550`
- `tests/fixtures/filter/cli-filter-gaussian_blur-1.5-1.json`: `d6c67f8dd6db6e1c783f86ed9d84159c10588d64817e88053d800cdd78eb8f38`
- `tests/fixtures/filter/cli-filter-unsharp_mask-0.5-0.json`: `385892f25c38482037b560154ae8214e9548d69b786e5ab86e4cf86139d75a12`
- `tests/fixtures/filter/cli-filter-unsharp_mask-1.5-1.json`: `8a962a638c22db10f6f04e291d9eaa6d689b5ed9504c5bfe16ceb1745c61caa3`
- `tests/fixtures/filter/cli-filter-unsharp_mask-64-16.json`: `1bf7873723a907d460d76acac9c68432bc37d7589c0ea25dd9dba7226229e3d4`
