"""Normalize public deterministic programs against the pinned API contract schema."""

import copy
import json
import operator
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from ..common.errors import ApiError

SCHEMA: dict[str, Any] = json.loads(
    files("image_platform_cli.v4").joinpath("program_schema.json").read_text()
)


def normalize_program(value: dict[str, Any]) -> dict[str, Any]:
    try:
        result: dict[str, Any] = normalize(value, SCHEMA)
        Draft202012Validator(SCHEMA).validate(result)
    except (ValidationError, ValueError, KeyError, TypeError, InvalidOperation) as error:
        raise ApiError("program does not satisfy the deterministic editing contract") from error
    ids = [command["id"] for command in result["commands"]]
    if len(ids) != len(set(ids)) or result["inputs"].get(result["source_input"]) != "image":
        raise ApiError("program requires unique command IDs and an image source")
    return result


def normalize(value: Any, schema: dict[str, Any]) -> Any:
    if "$ref" in schema:
        schema = SCHEMA["$defs"][schema["$ref"].rsplit("/", 1)[-1]]
    variants = schema.get("anyOf", schema.get("oneOf"))
    if variants:
        numeric = next((part for part in variants if part.get("type") == "number"), None)
        if numeric is not None and any(part.get("type") == "string" for part in variants):
            decimal = Decimal(str(value))
            if not decimal.is_finite():
                raise ValueError("nonfinite decimal")
            comparisons: dict[str, Callable[[Decimal, Decimal], bool]] = {
                "minimum": operator.lt,
                "maximum": operator.gt,
                "exclusiveMinimum": operator.le,
                "exclusiveMaximum": operator.ge,
            }
            for key, compare in comparisons.items():
                if key in numeric and compare(decimal, Decimal(str(numeric[key]))):
                    raise ValueError("decimal outside bounds")
            return str(decimal)
        for branch in variants:
            if Draft202012Validator({**branch, "$defs": SCHEMA["$defs"]}).is_valid(value):
                return normalize(value, branch)
        raise ValueError("no schema branch")
    if schema.get("type") == "object":
        if not isinstance(value, dict):
            raise ValueError("expected object")
        result = copy.deepcopy(value)
        for name, field in schema.get("properties", {}).items():
            if name not in result:
                if "default" in field:
                    result[name] = copy.deepcopy(field["default"])
                elif name not in schema.get("required", []):
                    # Four default factories in the pinned public schema.
                    result[name] = {"r": 0, "g": 0, "b": 0, "a": 0} if name == "background" else {}
            if name in result:
                result[name] = normalize(result[name], field)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            for name in result:
                if name not in schema.get("properties", {}):
                    result[name] = normalize(result[name], extra)
        return result
    if schema.get("type") == "array":
        if "prefixItems" in schema:
            return [
                normalize(item, sub) for item, sub in zip(value, schema["prefixItems"], strict=True)
            ]
        return [normalize(item, schema.get("items", {})) for item in value]
    return value
