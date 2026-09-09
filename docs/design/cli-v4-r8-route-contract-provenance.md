# CLI V4 r8 route-contract provenance

Date: 2026-09-09. Accepted CLI requirement v6:
`711a4db7b98b14739f73bd5ce4d9fc6f7f450c7de708f38dc115a113acfaed5e`.
API authority: r8 design `5e12c6c2280bfcd32490c02b70b1ddbf372c000d25477e74402501c3df588115`
and its owner-direction record, both pinned by v6.

The existing 33-route snapshot was compared before and after replacing only the successful
`v4.image_edits.create` data schema with
`TypeAdapter(V4ImageToImageResult).json_schema()` evaluated in the local API project.
The other 32 routes, statuses, headers, scopes and error outcomes are unchanged.
API source `src/image_platform/native_v4.py` SHA-256:
`d03c24f496b733a4bb0712af192ee66b837d6b1b1cb541b64bbcd38ff35d1bed`.
Updated packaged `src/image_platform_cli/v4/route_contracts.json` SHA-256:
`a8803a3389b420a8b906a691004c320942149f054a9996fb2bac1be34431efb2`.

Common response metadata now requires 2026-09-09-r8. Catalog remains 2026-09-07-v4-r7.
Campaign/protocol docstrings identify the current contract, without changing campaign behavior.
The fixed image-to-image profile/model/implementation and control limits come from the accepted
producer definitions in `src/image_platform/editing.py`, SHA-256
`e13333ae488c66604b94601e37bbd3c5bc238d55d7ddc165b5c6e6a442b0a73e`. These version-specific facts remain under v4.
No runtime API-project imports or dependencies were introduced into the CLI package.

`tests/fixtures/native-v4-image-receipts.r8.json` SHA-256:
`d7f7e2bc9b49da3b580455b10bd41d723efb56001760939f08768425acf2c9ae`.
This fixture was generated through the real local API app, ImageEditService and V4 serializer,
using ValidImageToImageProvider and ValidInpaintProvider from the API receipt regression tests.
Both local calls returned 200. It contains request/image/response data only, with no credentials.
It proves the local wire shape, not live inference or deployed service state.

Coverage is recorded in `cli-v4-functional-coverage.v2.md`; v1 is preserved as prior evidence.
The default entrypoint remains image1. Remaining missing capabilities block default cutover.
