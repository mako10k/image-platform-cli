# V4 grayscale increment validation

Date: 2026-09-09. Authority: accepted CLI requirement v6 and owner's continuation instruction.
Starting CLI commit: 5226264. API contract and fixture source: local API commit 5d053dd.

Implemented image4 edit raster grayscale through POST /v4/image-operations, with the fixed
rec709_linear_srgb_v1 luminance rule, normalized coverage=null and PNG encoding. The output retains
source dimensions and alpha. Offline dry-run emits the program before configuration, authentication,
HTTP or input reading; ordinary execution requires an output path.

Reused single-command receipt validation and factored the identical V4 image-operation exchange
across conversion, crop and grayscale. Raster program selection now supports both crop and grayscale.
Existing conversion and crop regressions remain passing. No V1 or default dispatcher changes.

Validation: 257 tests passed, including seven new grayscale cases. Ruff, strict Mypy, Xenon and
Pylint duplicate-code passed. RGB and RGBA fixtures were generated with the real local CPU API.
Tests check Rec.709 values for red and green, neutral gray, partial/zero alpha, geometry, offline
preview and receipt rejection before output creation.

Built /tmp/cli-grayscale-package/image_platform_cli-0.1.0-py3-none-any.whl and installed offline
into /tmp/cli-v6-package/venv. Outside the checkout, verified installed package origin, preview,
V4 fixture request and a saved 4x1 PNG with grayscale value 220 and alpha 128. Image remains image1.
Coverage matrix v8 retains 15 missing rows.

No public request, paid provider call, push, release, deployment or default switch occurred.
These are local CPU/client results, not public-edge validation.

## Fixture hashes

- `tests/fixtures/grayscale/cli-grayscale-RGB.json`: `d8b039f93f46e6c8b19678c39015af9e51ed494fe2a578843c30143670d1c72e`
- `tests/fixtures/grayscale/cli-grayscale-RGBA.json`: `b38b452af5a080b279389f018cdfa2f3e57aa3bbb30b0f5132f8f454b97dd08f`
