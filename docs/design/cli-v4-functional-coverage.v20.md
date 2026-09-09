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

## Cutover validation result

The post-switch complete suite passed 485 tests. Ruff lint, Ruff formatting, strict Mypy,
Xenon complexity limits, and the Pylint duplicate-code check also passed. Commit `1ae8d3e` was
built as `image_platform_cli-0.1.0-py3-none-any.whl`; its SHA-256 was
`f0e68d61741948f86a97b08708e6d9d57752bcee96cf4ecd9747ba9ab23e6909`, and the archive integrity
check passed.

That exact wheel replaced the existing local `uv` tool installation. Readback found all three
executables in `/home/katsumata-m/.local/bin`. From outside the checkout, `image --help` and
`image4 --help` were byte-identical, while `image1 --help` remained distinct. `image auth status`
successfully read the existing user, expected organization, and all fourteen V4 API scopes without
printing credential values.
