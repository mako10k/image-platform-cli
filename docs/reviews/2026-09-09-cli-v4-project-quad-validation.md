# V4 quadrilateral projection focused validation

Date: 2026-09-09. Authority: accepted CLI requirement v6, owner continuation and focused-test limit.
Starting CLI commit: 3963cfb. API contract and fixture source: local API commit 5d053dd.

Implemented image4 edit raster project-quad via POST /v4/image-operations. Supports a texture image,
four destination points, source_over/replace/multiply/screen compositing and offline preview.
Normalized controls retain bilinear interpolation and null coverage. Both winding directions and
negative coordinates are supported; crossed, concave, degenerate or out-of-bound coordinates are
rejected locally before file reading or HTTP. Source canvas dimensions and PNG output remain fixed.

Reused the existing named-input preparation to bind source and texture hashes and the existing
single-command receipt verifier. No shared input/receipt implementation change was needed. No V1
or dispatcher change was made.

## Focused checks

35 tests passed from tests/test_v4_project_quad.py (15 new cases), tests/test_v4_color_matching.py
and tests/test_v4_cli.py. These cover the new projection path, sibling multi-input routing and
parser composition. Four fixtures were produced through the real local CPU API. Tests verify each
mode's request and saved bytes, unchanged outside pixels, geometry, texture/command mismatch rejection,
invalid quadrilaterals and offline preview without configuration, HTTP or input reading.

Ruff passed for the changed source/test files. Strict Mypy with --follow-imports=silent passed for
three changed source files. git diff --check passed. No full-suite, repository-wide static/clone or
package checks were rerun, in accordance with the owner instruction. Broader cutover validation
remains pending; prior full-suite results are historical evidence.

Coverage matrix v13 retains 10 missing rows. Image remains image1. No public request, paid provider
call, push, release, deployment or default switch occurred.

## Fixture hashes

- `tests/fixtures/project-quad/cli-quad-multiply.json`: `6af5798a3ebce4e14c4f1df3da2db2e8c22c3686b72e76fd65ab9bcc4579d3d5`
- `tests/fixtures/project-quad/cli-quad-replace.json`: `dccfc2c4909060a66f86630631ffe8fb8072f31da0343a211e468dc7f82c0d49`
- `tests/fixtures/project-quad/cli-quad-screen.json`: `a30098a496d0e06f8578d521ffd9f89555ca70f9984ecc796ee70986ca5708bc`
- `tests/fixtures/project-quad/cli-quad-source_over.json`: `f76292eafd440710381e375053fb7c4900e3142bb53bef152c5dc1f6b5c515de`
