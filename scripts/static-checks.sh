#!/usr/bin/env bash
set -euo pipefail

uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run xenon --max-absolute D --max-modules C --max-average B src
uv run pylint src tests \
  --disable=all \
  --enable=duplicate-code \
  --min-similarity-lines=8 \
  --ignore-comments=yes \
  --ignore-docstrings=yes \
  --ignore-imports=yes
