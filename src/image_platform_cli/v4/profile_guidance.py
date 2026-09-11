"""Display server-owned text without interpreting its content or applying settings."""

import json
from typing import Any

from ..common.errors import CliError


def show_profiles(
    result: dict[str, Any], *, profile_id: str | None, details: bool, as_json: bool
) -> None:
    items = result["items"]
    if profile_id is not None:
        items = [item for item in items if item["id"] == profile_id]
        if not items:
            raise CliError("unknown profile; list IDs with image model-profiles --json")
        result = {**result, "items": items}
    if details:
        missing = [item["id"] for item in items if item.get("guidance") is None]
        if missing:
            raise CliError("server guidance is unavailable for: " + ", ".join(missing))
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif details:
        for item in items:
            guidance = item["guidance"]
            print(f"{item['id']} ({guidance['language']}, {result['guidance_revision']})")
            print(guidance["content"], end="" if guidance["content"].endswith("\n") else "\n")
    else:
        print(
            f"Native API V4 model profiles: {len(items)} (catalog {result.get('catalog_revision', 'unknown')})"
        )
