# CLI v6 / API r8 implementation increment

Date: 2026-09-09. Task: T_CLI_V4_ALIGNMENT, resumed under accepted CLI requirement v6.
Scope completed here: r8 contract alignment and the image-to-image capability. The full CLI task
remains active with 21 missing capability rows; default cutover is not ready.

## Changes

- Common response metadata requires 2026-09-09-r8. The static catalog stays 2026-09-07-v4-r7.
- The packaged image-edits success schema uses ImageToImageReceipt; inpaint retains its own schema.
  Exact source pins and fixture provenance are in `docs/design/cli-v4-r8-route-contract-provenance.md`.
- `image4 edit image-to-image` (alias `i2i`) supports local or Artifact input, optional capture
  upload, profile, positive/negative prompt, strength, guidance, steps, seed and target dimensions.
- The V4 adapter checks requested controls, fixed producer identity, input/output metadata, image
  bytes, cost and required headers before the command creates its exclusive output file.
- Preserved image1 code and the image-to-image producer were not changed by this increment.

## Validation

- 162 tests passed, including 19 new image-to-image cases.
- Static entrypoint passed: Ruff, format, strict Mypy, Xenon and Pylint duplicate-code.
- The new tests accept real local API-generated r8 fixtures for image-to-image and inpaint,
  reject r7 and malformed/mismatched receipt/header/image evidence, and demonstrate no output
  creation on rejection. Local input, Artifact metadata lookup and capture sequencing are covered.
- Old response shape rejection uses the distinct real inpaint receipt, not a hand-written model.
- Wheel built and installed offline in `/tmp/cli-v6-package/venv`. From outside the checkout,
  image, image1 and image4 help entrypoints succeeded, the packaged schema selected the new result
  only for image-edits, and the actual image entrypoint delegated wholly to image1.
- `git diff --check` passed. Accepted v5/v6 bytes and prior coverage matrix v1 remain unchanged.

No live inference, API deployment, package release, push or default cutover was performed.
Functional coverage is tracked by `docs/design/cli-v4-functional-coverage.v2.md`.
