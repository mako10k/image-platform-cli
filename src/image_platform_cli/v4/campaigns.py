"""Closed public Campaign projections for Native API V4 revision r8."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..common.errors import ApiError

TERMINAL = frozenset({"completed", "partial", "failed", "cancelled"})
STOP_REASONS = {"threshold_reached", "max_rounds_reached", "cost_ceiling_reached"}
IDENTITY_KEYS = {"rubric_id", "rubric_revision", "evaluator_model_revision"}


def number(
    value: object, *, minimum: Decimal = Decimal(0), maximum: Decimal | None = None
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ApiError("invalid Campaign numeric value")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ApiError("invalid Campaign numeric value") from error
    if not result.is_finite() or result < minimum or (maximum is not None and result > maximum):
        raise ApiError("Campaign numeric value is outside the supported range")
    return result


def integer(value: object, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _identity(value: dict[str, Any]) -> None:
    if (
        not isinstance(value.get("rubric_id"), str)
        or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value["rubric_id"]) is None
        or not isinstance(value.get("rubric_revision"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["rubric_revision"]) is None
        or not isinstance(value.get("evaluator_model_revision"), str)
        or not 1 <= len(value["evaluator_model_revision"]) <= 255
    ):
        raise ApiError("image API returned malformed rubric identity")


def rubric(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != IDENTITY_KEYS | {
        "max_rounds",
        "max_candidates_per_round",
    }:
        raise ApiError("image API returned malformed evaluation rubric")
    _identity(value)
    if not integer(value["max_rounds"], 1, 3) or not integer(
        value["max_candidates_per_round"], 1, 4
    ):
        raise ApiError("image API returned unsupported rubric limits")
    return value


def policy(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != IDENTITY_KEYS | {
        "score_threshold",
        "max_rounds",
        "candidates_per_round",
    }:
        raise ApiError("image API returned malformed iteration policy")
    _identity(value)
    number(value["score_threshold"], maximum=Decimal(1))
    if not integer(value["max_rounds"], 1, 3) or not integer(value["candidates_per_round"], 1, 4):
        raise ApiError("image API returned unsupported iteration limits")
    return value


def _evaluation(value: object, round_: dict[str, Any], selected: dict[str, Any]) -> None:
    if not isinstance(value, dict) or set(value) != IDENTITY_KEYS | {"round_index", "candidates"}:
        raise ApiError("image API returned malformed round evaluation")
    if value["round_index"] != round_["round_index"] or any(
        value[k] != selected[k] for k in IDENTITY_KEYS
    ):
        raise ApiError("image API returned inconsistent evaluation identity")
    candidates = value["candidates"]
    if not isinstance(candidates, list) or len(candidates) != len(round_["artifact_ids"]):
        raise ApiError("image API returned inconsistent evaluation candidates")
    ids = []
    for item in candidates:
        if (
            not isinstance(item, dict)
            or set(item) != {"artifact_id", "score", "reason", "measured_compute_cost_usd"}
            or not isinstance(item["reason"], str)
            or not 1 <= len(item["reason"]) <= 2048
        ):
            raise ApiError("image API returned malformed candidate evaluation")
        ids.append(item["artifact_id"])
        number(item["score"], maximum=Decimal(1))
        number(item["measured_compute_cost_usd"])
    if not _strings(ids) or len(set(ids)) != len(ids) or set(ids) != set(round_["artifact_ids"]):
        raise ApiError("image API returned inconsistent evaluated Artifacts")


def _round(value: object, index: int, selected: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "round_index",
        "child_job_ids",
        "artifact_ids",
        "evaluation",
        "seeds",
        "provider_cost_usd",
    }:
        raise ApiError("image API returned malformed Campaign round")
    jobs, artifacts, seeds = value["child_job_ids"], value["artifact_ids"], value["seeds"]
    if (
        not integer(value["round_index"], 0, 2)
        or value["round_index"] != index
        or not _strings(jobs)
        or len(jobs) != selected["candidates_per_round"]
        or not _strings(artifacts)
        or len(artifacts) not in {0, len(jobs)}
        or not isinstance(seeds, list)
        or len(seeds) != len(jobs)
        or not all(integer(seed, 0, 2**63 - 1) for seed in seeds)
        or (value["evaluation"] is None) != (not artifacts)
    ):
        raise ApiError("image API returned inconsistent Campaign round")
    number(value["provider_cost_usd"])
    if value["evaluation"] is not None:
        _evaluation(value["evaluation"], value, selected)
    return value


def validate_campaign(value: dict[str, Any]) -> None:
    if set(value) != {
        "campaign_id",
        "plan_id",
        "status",
        "created_at",
        "child_job_ids",
        "estimated_cost_usd",
        "actual_cost_usd",
        "max_cost_usd",
        "allow_partial",
        "iteration_policy",
        "rounds",
        "stop_reason",
    }:
        raise ApiError("image API returned malformed Campaign")
    if (
        not all(
            isinstance(value[k], str) and value[k] for k in ("campaign_id", "plan_id", "created_at")
        )
        or not isinstance(value["status"], str)
        or value["status"] not in TERMINAL | {"planned", "queued", "running"}
        or not _strings(value["child_job_ids"])
        or not isinstance(value["allow_partial"], bool)
    ):
        raise ApiError("image API returned malformed Campaign identity or state")
    try:
        created = datetime.fromisoformat(value["created_at"])
        if created.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as error:
        raise ApiError("image API returned an invalid Campaign creation timestamp") from error
    for key in ("estimated_cost_usd", "actual_cost_usd", "max_cost_usd"):
        number(value[key])
    if number(value["max_cost_usd"]) == 0:
        raise ApiError("image API returned invalid Campaign cost ceiling")
    rounds = value["rounds"]
    if not isinstance(rounds, list):
        raise ApiError("image API returned malformed Campaign history")
    if value["iteration_policy"] is None:
        if rounds or value["stop_reason"] is not None:
            raise ApiError("image API returned iteration history without policy")
        return
    selected = policy(value["iteration_policy"])
    if not 1 <= len(rounds) <= selected["max_rounds"]:
        raise ApiError("image API returned invalid Campaign round count")
    validated = [_round(item, index, selected) for index, item in enumerate(rounds)]
    if [job for item in validated for job in item["child_job_ids"]] != value["child_job_ids"]:
        raise ApiError("image API returned inconsistent Campaign child jobs")
    reason = value["stop_reason"]
    if reason is not None and (
        not isinstance(reason, str)
        or reason not in STOP_REASONS
        or validated[-1]["evaluation"] is None
    ):
        raise ApiError("image API returned invalid Campaign stop reason")
