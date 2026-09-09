# CLI Native API V4 default cutover, revision 20

- Date: 2026-09-09
- Predecessor: `docs/design/cli-v4-functional-coverage.v19.md`
- Requirement: `docs/requirements/cli-native-api-v4-alignment.v6.md`
- Requirement SHA-256: `711a4db7b98b14739f73bd5ce4d9fc6f7f450c7de708f38dc115a113acfaed5e`
- Status: local default cutover implemented and validated

Revision 19 contains the complete 49-leaf functional matrix: two local/common rows,
35 V4-bound rows, and no missing rows. The stable `image` dispatcher now delegates wholly to
`image4`; `image1` remains directly callable as the former implementation. No mutable runtime
selector was introduced.

Before the binding change, the complete suite passed with 485 tests and the standard Ruff,
formatting, strict Mypy, Xenon, and Pylint duplicate-code checks passed. The same complete checks
are required after the binding change. A wheel built from the cutover commit must demonstrate from
outside the checkout that `image` and `image4` expose the V4 command tree while `image1` remains
callable. The exact wheel is then installed as the local `uv` tool and read back.

Authenticated public smoke evidence precedes this cutover: capabilities and deterministic crop
returned r8 success, and one real generation completed and downloaded a verified 1024x1024 image.
Those calls do not replace local package validation. This cutover does not release a registry
package, merge a branch, change the deployed API, or remove image1.
