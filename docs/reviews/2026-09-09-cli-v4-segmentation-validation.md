# V4 segmentation increment validation

Date: 2026-09-09. Authority: accepted CLI requirement v6 and owner's implementation continuation.

Implemented `image4 edit segment` through POST /v4/segmentations. Text, bounding-box, positive
and negative point selectors are supported, with mask, foreground and background destinations.
Before creating output, the client validates the r8 envelope, source/mask receipts, fixed profile
and both model identities/revisions, output bytes and geometry, image headers and compute cost.
Invalid selector coordinates/counts and unavailable or aliased output paths are rejected locally.

The V1 segmentation renderer was moved into common without changing its function AST. V1 and V4
use that same local renderer, while version-specific transport and receipt validation remain separate.

Evidence: 190 tests passed; Ruff, strict Mypy, Xenon and Pylint duplicate-code checks passed.
Seventeen new test cases cover selectors, output variants and rejection paths. The response fixture
was generated through the real local API with a fake segmentation provider, not a live model.
Fixture: `tests/fixtures/native-v4-segmentation.r8.json`
SHA-256: `37d6389b97bf823c20abdf288818aa1a9df5de0e0a099039000dd937cd9f2459`

Built wheel `/tmp/cli-segment-package/image_platform_cli-0.1.0-py3-none-any.whl`, installed offline
into an isolated environment, and verified package origin, parser, V4 request, fixture consumption
and all three saved outputs outside the checkout. This establishes local client/contract behavior,
not live provider or public-edge behavior. No public API request, provider execution, push, release,
deployment or default switch occurred. Coverage matrix v4 retains 19 missing rows; image remains image1.
