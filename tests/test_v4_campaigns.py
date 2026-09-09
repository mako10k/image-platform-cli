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


def evaluated_campaign(*, pending: bool = False) -> dict[str, Any]:
    identity = {
        "rubric_id": "default",
        "rubric_revision": "b" * 64,
        "evaluator_model_revision": "evaluator-pinned",
    }
    return campaign(
        status="running" if pending else "completed",
        child_job_ids=["job_12345678"],
        iteration_policy={
            **identity,
            "score_threshold": "0.8",
            "max_rounds": 3,
            "candidates_per_round": 1,
        },
        rounds=[
            {
                "round_index": 0,
                "child_job_ids": ["job_12345678"],
                "artifact_ids": [] if pending else ["art_12345678"],
                "evaluation": None
                if pending
                else {
                    **identity,
                    "round_index": 0,
                    "candidates": [
                        {
                            "artifact_id": "art_12345678",
                            "score": "0.9",
                            "reason": "Matches requested subject",
                            "measured_compute_cost_usd": "0.001",
                        }
                    ],
                },
                "seeds": [7],
                "provider_cost_usd": "0.01",
            }
        ],
        stop_reason=None if pending else "threshold_reached",
        actual_cost_usd="0.011",
    )


@pytest.mark.parametrize("pending", [False, True])
def test_evaluation_retains_scores_reasons_costs_and_pending_rounds(pending: bool) -> None:
    expected = evaluated_campaign(pending=pending)

    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("GET", "/v4/campaigns/campaign_123")
        return response(expected)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = V4ApiClient(http, "https://api.example").campaign_evaluation(
            "token", "campaign_123"
        )
    assert result == {
        key: expected[key]
        for key in (
            "campaign_id",
            "status",
            "iteration_policy",
            "rounds",
            "stop_reason",
            "actual_cost_usd",
            "max_cost_usd",
        )
    }


def test_results_collect_child_jobs_and_artifact_ids_without_implicit_download() -> None:
    from test_v4_api import artifact_descriptor, job_view

    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.method == "GET"
        if request.url.path == "/v4/campaigns/campaign_123":
            return response(
                campaign(
                    status="partial",
                    child_job_ids=["job_12345678", "job_87654321"],
                    allow_partial=True,
                )
            )
        job = job_view()
        job["job_id"] = request.url.path.rsplit("/", 1)[-1]
        job["status"] = "completed" if job["job_id"] == "job_12345678" else "failed"
        job["outputs"] = [artifact_descriptor()] if job["status"] == "completed" else []
        return response(job)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = V4ApiClient(http, "https://api.example").campaign_results("token", "campaign_123")
    assert result["artifacts"] == [{"job_id": "job_12345678", "artifact_id": "art_12345678"}]
    assert len(result["jobs"]) == 2
    assert paths == ["/v4/campaigns/campaign_123", "/v4/jobs/job_12345678", "/v4/jobs/job_87654321"]


@pytest.mark.parametrize(
    "state", ["queued", "running", "completed", "partial", "failed", "cancelled"]
)
def test_status_and_cancel_validate_the_requested_campaign(state: str) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return response(campaign(status=state if request.method == "GET" else "cancelled"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = V4ApiClient(http, "https://api.example")
        assert api.get_campaign("token", "campaign_123")["status"] == state
        assert api.cancel_campaign("token", "campaign_123")["status"] == "cancelled"
    assert calls == [
        ("GET", "/v4/campaigns/campaign_123"),
        ("POST", "/v4/campaigns/campaign_123/cancel"),
    ]


@pytest.mark.parametrize(
    "method", ["get_campaign", "cancel_campaign", "campaign_results", "campaign_evaluation"]
)
def test_campaign_followups_reject_other_identity(method: str) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: response(campaign(campaign_id="campaign_other"))
            )
        ) as http,
        pytest.raises(ApiError, match="unexpected Campaign"),
    ):
        getattr(V4ApiClient(http, "https://api.example"), method)("token", "campaign_123")


@pytest.mark.parametrize(
    "options",
    [
        {"max_cost_usd": Decimal(0)},
        {"max_cost_usd": Decimal("NaN")},
        {"wait_seconds": 61},
        {"wait_seconds": 1501, "allow_long_wait": True},
        {"score_threshold": Decimal("1.1")},
        {"score_threshold": Decimal(".8"), "max_rounds": 4},
    ],
)
def test_invalid_campaign_controls_do_not_submit(options: dict[str, Any]) -> None:
    def no_network(_: httpx.Request) -> httpx.Response:
        pytest.fail("invalid controls reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(no_network)) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.example").create_campaign(
            "token", plan_id="bplan_123", **{"max_cost_usd": Decimal(".2"), **options}
        )


def test_wait_timeout_returns_current_state_without_duplicate_submission() -> None:
    ticks = [0.0]
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return response(
            campaign(allow_partial=True),
            status_code=202 if request.method == "POST" else 200,
            extra_headers={"Idempotent-Replay": "false"} if request.method == "POST" else {},
        )

    def sleep(seconds: float) -> None:
        ticks[0] += seconds

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = V4ApiClient(
            http, "https://api.example", sleeper=sleep, clock=lambda: ticks[0]
        ).create_campaign(
            "token",
            plan_id="bplan_123",
            max_cost_usd=Decimal(".2"),
            allow_partial=True,
            wait_seconds=2,
        )
    assert result["status"] == "queued"
    assert ticks[0] == 2
    assert methods == ["POST", "GET", "GET"]
