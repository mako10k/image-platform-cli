import hashlib
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from image_platform_cli.common.errors import ApiError
from image_platform_cli.v4.api import V4ApiClient

REQUEST_ID = "req_0123456789abcdef0123456789abcdef"
ARTIFACT_ID = "art_12345678"
NOW = "2026-09-09T10:00:00Z"
SHA = "a" * 64


def response(
    data: object,
    *,
    request_id: str = REQUEST_ID,
    status_code: int = 200,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "X-Request-ID": request_id,
            **(extra_headers or {}),
        },
        json={
            "data": data,
            "meta": {
                "request_id": request_id,
                "api_version": "4",
                "contract_revision": "2026-09-09-r8",
            },
        },
    )


def test_capabilities_uses_only_v4_and_unwraps_verified_envelope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response({"catalog_revision": "2026-09-07-v4-r7", "items": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = V4ApiClient(http, "https://api.example").capabilities("secret-token")

    assert result == {"catalog_revision": "2026-09-07-v4-r7", "items": []}
    assert requests[0].url == "https://api.example/v4/capabilities"
    assert requests[0].headers["Authorization"] == "Bearer secret-token"


def test_prompt_optimization_uses_v4_and_validates_seed() -> None:
    requests: list[httpx.Request] = []
    plan = {
        "profile": "generation-standard",
        "optimizer_version": "optimizer-v1",
        "intent": {
            "subject": "a cup",
            "environment": None,
            "composition": None,
            "style": None,
            "lighting": None,
            "text_requirements": None,
            "preservation_constraints": [],
            "exclusions": [],
        },
        "prompt": "A carefully planned image prompt",
        "negative_prompt": None,
        "width": 512,
        "height": 768,
        "cache_hit": False,
        "seed": 7,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response(plan)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = V4ApiClient(http, "https://api.example").optimize_prompt(
            "token", prompt="a cup", width=512, height=768, seed=7
        )

    assert result == plan
    assert requests[0].url.path == "/v4/prompt-plans"
    assert requests[0].method == "POST"
    assert requests[0].read() == (
        b'{"query":"a cup","profile":"generation-standard","seed":7,"width":512,"height":768}'
    )


def test_generation_uses_v4_completion_access_and_verified_bytes() -> None:
    data = png_bytes(512, 512)
    descriptor = artifact_descriptor(
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        width=512,
        height=512,
    )
    metadata = artifact_metadata(descriptor=descriptor)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "objects.example":
            return httpx.Response(200, headers={"Content-Type": "image/png"}, content=data)
        if request.url.path.endswith("/access"):
            return response(
                {"artifact": descriptor, "url": "https://objects.example/result", "expires_at": NOW}
            )
        return response(
            {
                "job_id": "job_12345678",
                "status": "completed",
                "result": metadata,
                "prompt_plan": None,
                "seed": 7,
            },
            extra_headers={"Idempotent-Replay": "false", "X-Image-SHA256": descriptor["sha256"]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        image = V4ApiClient(http, "https://api.example").generate(
            "token", prompt="a red cup", width=512, height=512, seed=7
        )

    assert image.data == data
    assert image.seed == 7
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v4/generations"),
        ("POST", f"/v4/artifacts/{ARTIFACT_ID}/access"),
        ("GET", "/result"),
    ]


def test_generation_follows_valid_v4_accepted_job_to_completion() -> None:
    data = png_bytes(512, 512)
    descriptor = artifact_descriptor(
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        width=512,
        height=512,
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "objects.example":
            return httpx.Response(200, headers={"Content-Type": "image/png"}, content=data)
        if request.url.path == "/v4/generations":
            return response(
                {
                    "job_id": "job_12345678",
                    "status": "queued",
                    "status_url": "https://api.example/v4/jobs/job_12345678",
                    "cancel_url": "https://api.example/v4/jobs/job_12345678/cancel",
                    "submitted_at": NOW,
                    "execution": {
                        "wait_seconds": 30,
                        "allow_long_wait": False,
                        "accept_async": True,
                    },
                },
                status_code=202,
                extra_headers={
                    "Idempotent-Replay": "false",
                    "Location": "https://api.example/v4/jobs/job_12345678",
                    "Retry-After": "1",
                },
            )
        if request.url.path == "/v4/jobs/job_12345678":
            job = job_view()
            job["status"] = "completed"
            job["steps"] = [
                {
                    "id": "generate",
                    "status": "completed",
                    "attempt": 1,
                    "value_outputs": {"seed": 7},
                    "error_code": None,
                    "error_detail": None,
                }
            ]
            job["outputs"] = [descriptor]
            return response(job)
        if request.url.path.endswith("/access"):
            return response(
                {"artifact": descriptor, "url": "https://objects.example/result", "expires_at": NOW}
            )
        return response(artifact_metadata(descriptor=descriptor))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        image = V4ApiClient(http, "https://api.example", sleeper=lambda _seconds: None).generate(
            "token", prompt="a red cup", width=512, height=512, seed=7
        )

    assert image.data == data
    assert [request.url.path for request in requests] == [
        "/v4/generations",
        "/v4/jobs/job_12345678",
        f"/v4/artifacts/{ARTIFACT_ID}",
        f"/v4/artifacts/{ARTIFACT_ID}/access",
        "/result",
    ]


def test_search_uses_v4_artifact_route_and_validates_hits() -> None:
    requests: list[httpx.Request] = []
    result = {
        "embedding_profile": "clip-vit-base-patch32-v1",
        "model": "clip",
        "model_revision": "revision-1",
        "dimension": 512,
        "results": [
            {
                "artifact": artifact_descriptor(),
                "namespace": "default",
                "score": 0.75,
                "created_at": NOW,
                "indexed_at": NOW,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response(result)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        actual = V4ApiClient(http, "https://api.example").search(
            "token",
            query="red cup",
            namespace="default",
            mime_types=("image/png",),
            created_after=NOW,
            limit=5,
        )

    assert actual == result
    assert requests[0].url.path == "/v4/artifacts/search"
    assert requests[0].method == "POST"


def test_caption_uses_v4_and_validates_public_result() -> None:
    requests: list[httpx.Request] = []
    result = {
        "caption": "A red cup.",
        "model": "vision-model",
        "image": {"sha256": SHA, "width": 2, "height": 3},
        "cold_start": False,
        "model_load_seconds": "0",
        "inference_seconds": "0.25",
        "measured_compute_cost_usd": "0.01",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response(result)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        actual = V4ApiClient(http, "https://api.example").caption(
            "token", artifact_id=ARTIFACT_ID, instruction="Describe it", max_output_tokens=64
        )

    assert actual == result
    assert requests[0].url.path == "/v4/captions"
    assert requests[0].method == "POST"


def test_batch_plan_uses_v4_and_validates_candidate_count_and_seed() -> None:
    requests: list[httpx.Request] = []
    result = {
        "plan_id": "bplan_1",
        "created_at": NOW,
        "profile": "generation-standard",
        "model_revision": "model-r1",
        "width": 512,
        "height": 512,
        "root_seed": 7,
        "items": [
            {"index": 0, "prompt": "first prompt", "seed": 7},
            {"index": 1, "prompt": "second prompt", "seed": 8},
        ],
        "estimated_cost_usd": "0.02",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response(result, status_code=201, extra_headers={"Idempotent-Replay": "false"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        actual = V4ApiClient(http, "https://api.example").create_batch_plan(
            "token", intent="two cups", width=512, height=512, candidate_count=2, root_seed=7
        )

    assert actual == result
    assert requests[0].url.path == "/v4/batch-plans"
    assert requests[0].headers["Idempotency-Key"]


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        (
            {"Content-Type": "application/json", "X-Request-ID": REQUEST_ID},
            {"data": {}, "meta": {}},
        ),
        (
            {
                "Content-Type": "application/json",
                "Cache-Control": "no-store",
                "X-Request-ID": REQUEST_ID,
            },
            {
                "data": {},
                "meta": {
                    "request_id": "req_ffffffffffffffffffffffffffffffff",
                    "api_version": "4",
                    "contract_revision": "2026-09-09-r8",
                },
            },
        ),
    ],
)
def test_capabilities_rejects_unverified_common_response(
    headers: dict[str, str], body: dict[str, object]
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, headers=headers, json=body)
    )
    with httpx.Client(transport=transport) as http, pytest.raises(ApiError):
        V4ApiClient(http, "https://api.example").capabilities("token")


def test_capabilities_validate_closed_sorted_binding_projection() -> None:
    item = {
        "id": "image.generate",
        "kind": "user_capability",
        "family": "image.generation",
        "availability_domain": "v4_callable",
        "semantic_authorization_scopes": ["images:generate"],
        "bindings": [
            {
                "route_id": "v4.generations.create",
                "method": "POST",
                "path_template": "/v4/generations",
                "required_oauth_scopes": ["images:generate"],
                "configured": True,
                "authorized": False,
                "reason": "insufficient_scope",
            }
        ],
    }
    transport = httpx.MockTransport(
        lambda _request: response({"catalog_revision": "2026-09-07-v4-r7", "items": [item]})
    )

    with httpx.Client(transport=transport) as http:
        result = V4ApiClient(http, "https://api.example").capabilities("token")

    assert result["items"] == [item]


@pytest.mark.parametrize(
    "data",
    [
        {"catalog_revision": "wrong", "items": []},
        {
            "catalog_revision": "2026-09-07-v4-r7",
            "items": [
                {
                    "id": "z",
                    "kind": "resource_protocol",
                    "family": "discovery",
                    "availability_domain": "v4_callable",
                    "semantic_authorization_scopes": [],
                    "bindings": [],
                },
                {
                    "id": "a",
                    "kind": "resource_protocol",
                    "family": "discovery",
                    "availability_domain": "v4_callable",
                    "semantic_authorization_scopes": [],
                    "bindings": [],
                },
            ],
        },
    ],
)
def test_capabilities_reject_invalid_closed_projection(data: dict[str, object]) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _request: response(data))) as http,
        pytest.raises(ApiError, match="capability data|response schema"),
    ):
        V4ApiClient(http, "https://api.example").capabilities("token")


def test_safe_v4_error_uses_only_public_code_and_message() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-store",
                "X-Request-ID": REQUEST_ID,
                "WWW-Authenticate": 'Bearer error="insufficient_scope", scope=""',
            },
            json={
                "error": {
                    "code": "insufficient_scope",
                    "message": "permission denied",
                    "retryable": False,
                },
                "meta": {
                    "request_id": REQUEST_ID,
                    "api_version": "4",
                    "contract_revision": "2026-09-09-r8",
                },
            },
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ApiError, match="insufficient_scope: permission denied"),
    ):
        V4ApiClient(http, "https://api.example").capabilities("token")


@pytest.mark.parametrize(
    ("invoke", "method", "path"),
    [
        (lambda api: api.model_profiles("token"), "GET", "/v4/model-profiles"),
        (lambda api: api.get_job("token", "job_12345678"), "GET", "/v4/jobs/job_12345678"),
        (
            lambda api: api.cancel_job("token", "job_12345678"),
            "POST",
            "/v4/jobs/job_12345678/cancel",
        ),
        (
            lambda api: api.job_previews("token", "job_12345678"),
            "GET",
            "/v4/jobs/job_12345678/previews",
        ),
        (
            lambda api: api.job_preview_access("token", "job_12345678", "step_1", "output_1"),
            "POST",
            "/v4/jobs/job_12345678/previews/step_1/output_1/access",
        ),
    ],
)
def test_resource_methods_use_exact_v4_binding(
    invoke: Callable[[V4ApiClient], dict[str, object]], method: str, path: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "/jobs/" in request.url.path:
            if request.url.path.endswith("/access"):
                return response(preview_access())
            if request.url.path.endswith("/previews"):
                return response({"job_id": "job_12345678", "previews": []})
            return response(job_view())
        return response({"revision": "r1", "items": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        invoke(V4ApiClient(http, "https://api.example"))

    assert requests[0].method == method
    assert requests[0].url.path == path


def test_collection_methods_preserve_repeated_v4_query_values() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response({"data": [], "next_cursor": None, "has_more": False})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = V4ApiClient(http, "https://api.example")
        api.list_jobs("token", params=(("status", "queued"), ("status", "running")))
        api.list_artifacts("token", params=(("state", "ready"), ("kind", "image")))

    assert requests[0].url.path == "/v4/jobs"
    assert requests[0].url.params.get_list("status") == ["queued", "running"]
    assert requests[1].url.path == "/v4/artifacts"
    assert str(requests[1].url.params) == "state=ready&kind=image"


def test_job_collection_validates_closed_item_projection() -> None:
    item = {
        "job_id": "job_12345678",
        "status": "running",
        "source_api": "native-v4",
        "submitted_at": NOW,
        "operations": ["generate"],
        "estimated_cost_usd": "0.10",
        "actual_cost_usd": "0.05",
        "outputs": [],
    }
    transport = httpx.MockTransport(
        lambda _request: response({"data": [item], "next_cursor": None, "has_more": False})
    )

    with httpx.Client(transport=transport) as http:
        result = V4ApiClient(http, "https://api.example").list_jobs("token")

    assert result["data"] == [item]


def test_job_previews_validate_closed_projection() -> None:
    preview = {
        "step_id": "step_1",
        "output": "output_1",
        "status": "ready",
        "renderer_revision": "renderer_1",
        "artifact": artifact_descriptor(),
        "expires_at": NOW,
        "error_code": None,
    }
    transport = httpx.MockTransport(
        lambda _request: response({"job_id": "job_12345678", "previews": [preview]})
    )

    with httpx.Client(transport=transport) as http:
        result = V4ApiClient(http, "https://api.example").job_previews("token", "job_12345678")

    assert result["previews"] == [preview]


def test_artifact_collection_validates_ready_item_lifecycle() -> None:
    item = {
        "artifact_id": ARTIFACT_ID,
        "namespace": "default",
        "kind": "image",
        "state": "ready",
        "created_at": NOW,
        "ready_at": NOW,
        "sha256": SHA,
        "mime_type": "image/png",
        "size_bytes": 10,
        "width": 1,
        "height": 1,
    }
    transport = httpx.MockTransport(
        lambda _request: response({"data": [item], "next_cursor": "next", "has_more": True})
    )

    with httpx.Client(transport=transport) as http:
        result = V4ApiClient(http, "https://api.example").list_artifacts("token")

    assert result["data"] == [item]


def artifact_descriptor(
    *, sha256: str = SHA, size_bytes: int = 10, width: int = 1, height: int = 1
) -> dict[str, object]:
    return {
        "artifact_id": ARTIFACT_ID,
        "kind": "image",
        "sha256": sha256,
        "mime_type": "image/png",
        "size_bytes": size_bytes,
        "width": width,
        "height": height,
    }


def artifact_metadata(*, descriptor: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "artifact_id": ARTIFACT_ID,
        "namespace": "default",
        "kind": "image",
        "state": "ready",
        "created_at": NOW,
        "upload_expires_at": NOW,
        "ready_at": NOW,
        "content": descriptor or artifact_descriptor(),
    }


def job_view() -> dict[str, object]:
    return {
        "job_id": "job_12345678",
        "status": "queued",
        "graph_sha256": None,
        "steps": [],
        "outputs": [],
        "result_manifest": {},
        "cost": {"estimated_usd": "0.10", "actual_usd": "0"},
    }


def preview_access() -> dict[str, object]:
    return {
        "step_id": "step_1",
        "output": "output_1",
        "renderer_revision": "renderer_1",
        "artifact": artifact_descriptor(),
        "url": "https://objects.example/preview",
        "url_expires_at": NOW,
        "preview_expires_at": NOW,
    }


def test_artifact_methods_validate_exact_v4_projections() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "DELETE":
            return response({"artifact_id": ARTIFACT_ID, "deleted_at": NOW})
        if request.url.path.endswith("/access"):
            return response(
                {
                    "artifact": artifact_descriptor(),
                    "url": "https://objects.example/artifact",
                    "expires_at": NOW,
                }
            )
        return response(artifact_metadata())

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = V4ApiClient(http, "https://api.example")
        api.get_artifact("token", ARTIFACT_ID)
        api.access_artifact("token", ARTIFACT_ID)
        api.delete_artifact("token", ARTIFACT_ID)

    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", f"/v4/artifacts/{ARTIFACT_ID}"),
        ("POST", f"/v4/artifacts/{ARTIFACT_ID}/access"),
        ("DELETE", f"/v4/artifacts/{ARTIFACT_ID}"),
    ]


def png_bytes(width: int = 2, height: int = 3) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def test_artifact_download_uses_explicit_access_and_verifies_bytes(tmp_path: Path) -> None:
    data = png_bytes()
    descriptor = artifact_descriptor(
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        width=2,
        height=3,
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "objects.example":
            return httpx.Response(200, headers={"Content-Type": "image/png"}, content=data)
        if request.url.path.endswith("/access"):
            return response(
                {
                    "artifact": descriptor,
                    "url": "https://objects.example/artifact",
                    "expires_at": NOW,
                }
            )
        return response(artifact_metadata(descriptor=descriptor))

    output = tmp_path / "artifact.png"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        V4ApiClient(http, "https://api.example").download_artifact("token", ARTIFACT_ID, output)

    assert output.read_bytes() == data
    assert [request.url.path for request in requests] == [
        f"/v4/artifacts/{ARTIFACT_ID}",
        f"/v4/artifacts/{ARTIFACT_ID}/access",
        "/artifact",
    ]


def test_artifact_upload_uses_v4_reserve_put_complete_sequence(tmp_path: Path) -> None:
    data = png_bytes()
    input_path = tmp_path / "input.png"
    input_path.write_bytes(data)
    descriptor = artifact_descriptor(
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        width=2,
        height=3,
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "objects.example":
            return httpx.Response(200)
        if request.url.path == "/v4/artifacts/uploads":
            return response(
                {
                    "artifact_id": ARTIFACT_ID,
                    "state": "reserved",
                    "upload": {
                        "method": "PUT",
                        "url": "https://objects.example/upload",
                        "headers": {"Content-Type": "image/png"},
                        "expires_at": NOW,
                    },
                },
                status_code=201,
            )
        return response(artifact_metadata(descriptor=descriptor))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = V4ApiClient(http, "https://api.example").upload_artifact("token", input_path)

    assert result["content"] == descriptor
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v4/artifacts/uploads"),
        ("PUT", "/upload"),
        ("POST", f"/v4/artifacts/{ARTIFACT_ID}/upload-completion"),
    ]


@pytest.mark.parametrize("resource_id", ["", ".", "..", "bad/id"])
def test_resource_methods_reject_unsafe_path_ids(resource_id: str) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _request: response({}))) as http,
        pytest.raises(ApiError, match="resource ID"),
    ):
        V4ApiClient(http, "https://api.example").get_job("token", resource_id)
