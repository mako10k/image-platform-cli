import json
from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from test_v4_api import NOW, response

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.campaigns import validate_campaign
from image_platform_cli.v4.cli import _run_batch, parser


def campaign(**changes: Any) -> dict[str, Any]:
    return {
        "campaign_id": "campaign_123",
        "plan_id": "bplan_123",
        "status": "queued",
        "created_at": NOW,
        "child_job_ids": [],
        "estimated_cost_usd": "0.01",
        "actual_cost_usd": "0",
        "max_cost_usd": "0.2",
        "allow_partial": False,
        "iteration_policy": None,
        "rounds": [],
        "stop_reason": None,
        **changes,
    }


def test_campaign_create_polls_only_v4_and_returns_terminal_state() -> None:
    calls: list[httpx.Request] = []
    tick = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            assert json.loads(request.content) == {
                "plan_id": "bplan_123",
                "max_cost_usd": "0.2",
                "allow_partial": False,
            }
            assert request.headers["Idempotency-Key"]
            return response(
                campaign(), status_code=202, extra_headers={"Idempotent-Replay": "false"}
            )
        return response(campaign(status="completed"))

    def sleep(seconds: float) -> None:
        tick[0] += seconds

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = V4ApiClient(http, "https://api.example", sleeper=sleep, clock=lambda: tick[0])
        result = api.create_campaign(
            "token", plan_id="bplan_123", max_cost_usd=Decimal("0.2"), wait_seconds=5
        )
    assert result["status"] == "completed"
    assert [(r.method, r.url.path) for r in calls] == [
        ("POST", "/v4/campaigns"),
        ("GET", "/v4/campaigns/campaign_123"),
    ]


def test_iteration_uses_discovered_pinned_rubric_and_plan_count() -> None:
    discovered = {
        "rubric_id": "default",
        "rubric_revision": "b" * 64,
        "evaluator_model_revision": "evaluator-pinned",
        "max_rounds": 3,
        "max_candidates_per_round": 4,
    }
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v4/batch-plans/bplan_123":
            return response(
                {
                    "plan_id": "bplan_123",
                    "created_at": NOW,
                    "profile": "generation-standard",
                    "model_revision": "fixed",
                    "width": 512,
                    "height": 512,
                    "root_seed": 7,
                    "items": [{"index": 0, "prompt": "cat", "seed": 7}],
                    "estimated_cost_usd": "0.01",
                }
            )
        if request.url.path == "/v4/evaluation-rubrics":
            return response([discovered])
        payload = json.loads(request.content)
        policy = payload["iteration_policy"]
        assert policy == {
            "rubric_id": "default",
            "rubric_revision": "b" * 64,
            "evaluator_model_revision": "evaluator-pinned",
            "max_rounds": 2,
            "score_threshold": "0.75",
            "candidates_per_round": 1,
        }
        return response(
            campaign(
                iteration_policy=policy,
                child_job_ids=["job_12345678"],
                rounds=[
                    {
                        "round_index": 0,
                        "child_job_ids": ["job_12345678"],
                        "artifact_ids": [],
                        "evaluation": None,
                        "seeds": [7],
                        "provider_cost_usd": "0",
                    }
                ],
            ),
            status_code=202,
            extra_headers={"Idempotent-Replay": "false"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        V4ApiClient(http, "https://api.example").create_campaign(
            "token",
            plan_id="bplan_123",
            max_cost_usd=Decimal("0.2"),
            score_threshold=Decimal("0.75"),
            max_rounds=2,
        )
    assert paths == ["/v4/batch-plans/bplan_123", "/v4/evaluation-rubrics", "/v4/campaigns"]


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_principal_id": "private"},
        {"max_cost_usd": "NaN"},
        {"status": "unknown"},
        {"rounds": [{}]},
        {"stop_reason": "threshold_reached"},
    ],
)
def test_campaign_rejects_private_fields_and_invalid_history(changes: dict[str, Any]) -> None:
    with pytest.raises(ApiError):
        validate_campaign(campaign(**changes))


@pytest.mark.parametrize("headers,status", [({}, 202), ({"Idempotent-Replay": "false"}, 200)])
def test_create_rejects_incorrect_acceptance(headers: dict[str, str], status: int) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: response(campaign(), status_code=status, extra_headers=headers)
            )
        ) as http,
        pytest.raises(ApiError, match="contract headers|success status"),
    ):
        V4ApiClient(http, "https://api.example").create_campaign(
            "token", plan_id="bplan_123", max_cost_usd=Decimal("0.2")
        )


@pytest.mark.parametrize("identifier", ["x?override=1", "x#fragment", "x%2fadmin", "../x"])
def test_campaign_id_cannot_change_request_target(identifier: str) -> None:
    def no_network(_: httpx.Request) -> httpx.Response:
        pytest.fail("invalid ID must fail before HTTP")

    with httpx.Client(transport=httpx.MockTransport(no_network)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.example").get_campaign("token", identifier)


@pytest.mark.parametrize(
    "command,scopes",
    [
        (["status", "campaign_123"], {"batches:execute", "campaigns:read", "jobs:cancel"}),
        (
            ["results", "campaign_123"],
            {"batches:execute", "campaigns:read", "jobs:cancel", "jobs:read"},
        ),
        (["cancel", "campaign_123"], {"jobs:cancel"}),
        (["run", "bplan_123", "--max-cost", "0.2"], {"batches:execute", "campaigns:write"}),
        (
            ["run", "bplan_123", "--max-cost", "0.2", "--wait", "5"],
            {"batches:execute", "campaigns:write", "campaigns:read", "jobs:cancel"},
        ),
    ],
)
def test_campaign_cli_requires_exact_effectful_scopes(command: list[str], scopes: set[str]) -> None:
    service, api = Mock(), Mock()
    for name in ("get_campaign", "campaign_results", "cancel_campaign", "create_campaign"):
        getattr(api, name).return_value = {}
    _run_batch(parser().parse_args(["batch", *command]), service, api)
    service.access_token.assert_called_once_with(frozenset(scopes))
