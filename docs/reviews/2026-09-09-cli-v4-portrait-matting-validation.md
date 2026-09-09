# V4 portrait matting increment validation

Date: 2026-09-09. Authority: accepted CLI requirement v6 and owner's next-implementation instruction.
Starting CLI commit: ddb60128618303ea5f645c9aba28a17fc4e9ebec.
API fixture source commit: 5d053dd (local API worktree).

Implemented image4 edit matte-portrait through POST /v4/portrait-mattings. The source image,
person mask, uncertainty radius (default 16, range 0 through 64) and PNG destination are supported.
Input geometry and radius are checked locally. Before saving, the V4 client checks the r8 envelope
and closed schema, source/mask/output metadata, pinned contract/profile/model/revision, requested
radius, PNG bytes and geometry, and image/model/cost headers. Existing V4 byte/header verification
is reused; no V1 code or default dispatcher changed.

Validation: 208 tests passed, including 18 added cases. Ruff, strict Mypy, Xenon and Pylint
duplicate-code checks passed. The response fixture was generated via the real local V4 API with
the existing fake portrait provider. Radius 0 and 64 responses are derived local test variants.
Fixture: tests/fixtures/native-v4-portrait-matting.r8.json
SHA-256: 743a18e34186f893af47baf3a354bbdc198d4ff7fbf9fd56ad8cac8ad2640e52

Built /tmp/cli-matting-package/image_platform_cli-0.1.0-py3-none-any.whl, installed offline in
/tmp/cli-v6-package/venv, verified installed module origin and exercised parser, V4 request,
fixture consumption and saved RGBA PNG outside the checkout. The stable image entrypoint still
delegates to image1. Coverage matrix v5 retains 18 missing rows.

This establishes local client and contract behavior. Live model quality and public-edge behavior
were not exercised. No live API/provider request, push, release, deployment or default switch occurred.
