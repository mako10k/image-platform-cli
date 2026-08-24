#!/usr/bin/env bash
set -euo pipefail

unset TMP TEMP

uv lock --check
./scripts/static-checks.sh
uv run pytest -q

cli_build_root=$(mktemp -d)
cleanup_cli_build_root() {
  rm -rf -- "${cli_build_root:?}"
}
trap cleanup_cli_build_root EXIT

SOURCE_DATE_EPOCH=0 uv build --wheel --out-dir "$cli_build_root/first"
SOURCE_DATE_EPOCH=0 uv build --wheel --out-dir "$cli_build_root/second"

cli_first_wheels=("$cli_build_root"/first/*.whl)
cli_second_wheels=("$cli_build_root"/second/*.whl)
if [[ ${#cli_first_wheels[@]} -ne 1 || ${#cli_second_wheels[@]} -ne 1 ]]; then
  echo "expected exactly one wheel from each build" >&2
  exit 1
fi

cmp -- "${cli_first_wheels[0]}" "${cli_second_wheels[0]}"
sha256sum "${cli_first_wheels[0]}"
