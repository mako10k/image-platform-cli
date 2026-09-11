import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from test_v4_api import NOW, response

from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import _run_batch, _run_job, parser


def campaign() -> dict[str, object]:
    return {
        "campaign_id": "campaign_12345678",
        "plan_id": "plan_12345678",
        "status": "queued",
        "created_at": NOW,
        "child_job_ids": [],
        "estimated_cost_usd": "0",
        "actual_cost_usd": "0",
        "max_cost_usd": "1",
        "allow_partial": False,
        "iteration_policy": None,
        "rounds": [],
        "stop_reason": None,
    }


def test_campaign_list_uses_v4_collection_contract() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response({"data": [campaign()], "next_cursor": None, "has_more": False})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        result = V4ApiClient(http, "https://api.invalid").list_campaigns(
            "token", params=[("limit", 10)]
        )

    assert result["data"] == [campaign()]
    assert requests[0].url.path == "/v4/campaigns"
    assert str(requests[0].url.query, "ascii") == "limit=10"


def test_job_submit_uses_v4_idempotent_contract() -> None:
    requests: list[httpx.Request] = []
    accepted = {
        "job_id": "job_12345678",
        "status": "queued",
        "estimated_cost_usd": "0.1",
        "submitted_at": NOW,
        "graph_sha256": "a" * 64,
    }

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response(
            accepted,
            status_code=202,
            extra_headers={"Idempotent-Replay": "false"},
        )

    job_request = {"request_id": "00000000-0000-0000-0000-000000000001"}
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        result = V4ApiClient(http, "https://api.invalid").submit_job("token", request=job_request)

    assert result == accepted
    assert requests[0].url.path == "/v4/jobs"
    assert requests[0].headers["Idempotency-Key"]
    assert json.loads(requests[0].content) == job_request


def test_collection_and_submission_commands_use_exact_scopes_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_path = tmp_path / "job.json"
    request_path.write_text('{"pipeline": {}}', encoding="utf-8")
    service, api = Mock(), Mock()
    service.access_token.return_value = "token"
    api.submit_job.return_value = {"job_id": "job_12345678"}

    _run_job(
        parser().parse_args(["job", "submit", "--request", str(request_path)]),
        service,
        api,
    )

    api.submit_job.assert_called_once_with("token", request={"pipeline": {}})
    service.access_token.assert_called_with(frozenset({"jobs:submit"}))
    assert json.loads(capsys.readouterr().out)["job_id"] == "job_12345678"

    api.list_campaigns.return_value = {"data": [], "next_cursor": None, "has_more": False}
    _run_batch(parser().parse_args(["batch", "list", "--limit", "5"]), service, api)
    api.list_campaigns.assert_called_once_with("token", params=[("limit", 5)])
    service.access_token.assert_called_with(
        frozenset({"batches:execute", "campaigns:read", "jobs:cancel"})
    )
