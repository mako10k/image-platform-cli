import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import httpx

from ..common.arguments import add_batch_plan_arguments, add_generation_arguments
from ..common.auth_cli import run_auth_command
from ..common.config import Config
from ..common.credentials import KeyringCredentialStore
from ..common.errors import CliError
from ..common.files import require_available_output, save_bytes_exclusive
from ..common.oauth import DeviceFlowClient
from ..common.service import AuthService
from ..common.tokens import TokenValidator
from .api import QueryScalar, V4ApiClient
from .edit_cli import add_edit_commands, load_json_object, raster_program, run_edit
from .help_navigation import GUIDES, TOPICS, show_help
from .profile_guidance import show_profiles
from .program_cli import prepare_cli_program
from .segment_cli import validate_segment_outputs

DEFAULT_LOGIN_SCOPES = (
    "images:generate",
    "images:edit",
    "images:understand",
    "batches:plan",
    "batches:execute",
    "campaigns:read",
    "campaigns:write",
    "jobs:submit",
    "jobs:read",
    "jobs:cancel",
    "artifacts:read",
    "artifacts:write",
    "artifacts:access",
    "artifacts:delete",
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="image4",
        epilog="Use `image help` to browse task guidance, examples, and recovery steps.",
    )
    groups = root.add_subparsers(dest="group", required=True)
    add_edit_commands(groups)
    help_command = groups.add_parser("help")
    help_command.add_argument("topic", nargs="*")
    auth = groups.add_parser("auth")
    auth_commands = auth.add_subparsers(dest="command", required=True)
    login = auth_commands.add_parser("login")
    login.add_argument("--scope", action="append", default=[])
    auth_commands.add_parser("status")
    auth_commands.add_parser("logout")
    capabilities = groups.add_parser("capabilities")
    capabilities.add_argument("--json", action="store_true")
    profiles = groups.add_parser("model-profiles")
    profiles.add_argument("--json", action="store_true")
    profiles.add_argument("--profile", help="Select an exact registered profile ID.")
    profiles.add_argument(
        "--details", action="store_true", help="Fetch server-owned plain text usage guidance."
    )
    prompt = groups.add_parser("prompt")
    prompts = prompt.add_subparsers(dest="command", required=True)
    optimize = prompts.add_parser("optimize")
    optimize.add_argument("prompt")
    optimize.add_argument("--width", type=int)
    optimize.add_argument("--height", type=int)
    optimize.add_argument("--seed", type=int)
    optimize.add_argument("--json", action="store_true")
    generate = groups.add_parser("generate")
    add_generation_arguments(generate)
    job = groups.add_parser(
        "job", epilog="Continue with `image help job` for examples and guided workflows."
    )
    jobs = job.add_subparsers(dest="command", required=True)
    job_list = jobs.add_parser("list")
    job_list.add_argument("--status", action="append", default=[])
    job_list.add_argument("--operation", action="append", default=[])
    _add_page_arguments(job_list)
    job_submit = jobs.add_parser(
        "submit",
        epilog=(
            "Run `image help job submit` to discover ControlNet, IP-Adapter, request, "
            "and recovery guides."
        ),
    )
    job_submit.add_argument("--request", type=Path, required=True)
    for command in ("show", "cancel", "previews"):
        selected = jobs.add_parser(command)
        selected.add_argument("job_id")
    preview_access = jobs.add_parser("preview-access")
    preview_access.add_argument("job_id")
    preview_access.add_argument("step_id")
    preview_access.add_argument("output")
    artifact = groups.add_parser("artifact")
    artifacts = artifact.add_subparsers(dest="command", required=True)
    artifact_list = artifacts.add_parser("list")
    artifact_list.add_argument("--state", action="append", default=[])
    artifact_list.add_argument("--kind", action="append", default=[])
    artifact_list.add_argument("--namespace")
    _add_page_arguments(artifact_list)
    for command in ("show", "delete"):
        selected = artifacts.add_parser(command)
        selected.add_argument("artifact_id")
        if command == "delete":
            selected.add_argument("--force", action="store_true")
    artifact_download = artifacts.add_parser("download")
    artifact_download.add_argument("artifact_id")
    artifact_download.add_argument("--output", "-o", type=Path, required=True)
    artifact_upload = artifacts.add_parser(
        "upload",
        epilog="For upload recovery, run `image help artifact upload recovery`.",
    )
    artifact_upload.add_argument("input", type=Path)
    artifact_upload.add_argument("--namespace", default="default")
    artifact_upload.add_argument("--kind", choices=("image", "mask"), default="image")
    search = groups.add_parser("search")
    search_source = search.add_mutually_exclusive_group(required=True)
    search_source.add_argument("query", nargs="?")
    search_source.add_argument("--image", type=Path)
    search_source.add_argument("--artifact")
    search.add_argument("--namespace", default="default")
    search.add_argument("--mime-type", action="append", default=[])
    search.add_argument("--created-after")
    search.add_argument("--limit", type=int, default=20)
    caption = groups.add_parser("caption")
    caption_source = caption.add_mutually_exclusive_group(required=True)
    caption_source.add_argument("input", nargs="?", type=Path)
    caption_source.add_argument("--artifact")
    caption.add_argument("--capture-input", action="store_true")
    caption.add_argument("--capture-namespace", default="default")
    caption.add_argument("--instruction", default="Describe this image concisely.")
    caption.add_argument("--max-output-tokens", type=int, default=128)
    caption.add_argument("--json", action="store_true")
    batch = groups.add_parser("batch")
    batches = batch.add_subparsers(dest="command", required=True)
    batch_plan = batches.add_parser("plan")
    add_batch_plan_arguments(batch_plan)
    for action in ("run", "iterate"):
        batch_command = batches.add_parser(action)
        batch_command.add_argument("plan_id")
        batch_command.add_argument("--max-cost", type=Decimal, required=True)
        batch_command.add_argument("--allow-partial", action="store_true")
        batch_command.add_argument("--wait", type=int, default=0)
        batch_command.add_argument("--allow-long-wait", action="store_true")
        if action == "iterate":
            batch_command.add_argument("--threshold", type=Decimal, default=Decimal("0.8"))
            batch_command.add_argument("--max-rounds", type=int, default=3)
    for action in ("status", "evaluate", "results", "cancel"):
        batches.add_parser(action).add_argument("campaign_id")
    batch_list = batches.add_parser("list")
    batch_list.add_argument("--cursor")
    batch_list.add_argument("--limit", type=int, default=20)
    return root


def _prepare_output(args: argparse.Namespace) -> bool:
    if (
        args.group == "edit"
        and args.command in {"run", "verify", "replace-object", "replace-background"}
        and prepare_cli_program(args)
    ):
        return True
    if args.group == "edit" and args.command == "raster":
        program = raster_program(args)
        if args.dry_run:
            print(json.dumps(program, sort_keys=True))
            return True
        if args.output is None:
            raise CliError("--output is required unless --dry-run is used")
    if args.group == "edit" and args.command == "segment":
        validate_segment_outputs(args)
    elif args.group in {"generate", "edit"} and getattr(args, "command", None) not in {
        "run",
        "verify",
        "replace-object",
        "replace-background",
        "plan",
        "batch",
    }:
        require_available_output(args.output)
    return False


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.group == "help":
        return _show_help(args.topic)
    try:
        if _prepare_output(args):
            return 0
        config = Config.staging()
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as http:
            service = AuthService(
                config,
                DeviceFlowClient(http, config.issuer, config.client_id),
                TokenValidator(http, config.issuer, config.audience),
                KeyringCredentialStore(),
            )
            api = V4ApiClient(http, config.api_base_url)
            if args.group == "model-profiles":
                token = service.access_token(frozenset())
                result = api.model_profiles(token, details=args.details)
                show_profiles(
                    result, profile_id=args.profile, details=args.details, as_json=args.json
                )
            elif args.group == "capabilities":
                result = api.capabilities(service.access_token(frozenset()))
                print(
                    json.dumps(result, indent=2, sort_keys=True)
                    if args.json
                    else _summary(args.group, result)
                )
            elif args.group == "job":
                _run_job(args, service, api)
            elif args.group == "artifact":
                _run_artifact(args, service, api)
            elif args.group == "prompt":
                result = api.optimize_prompt(
                    service.access_token(frozenset({"batches:plan"})),
                    prompt=args.prompt,
                    width=args.width,
                    height=args.height,
                    seed=args.seed,
                )
                print(
                    json.dumps(result, indent=2, sort_keys=True) if args.json else result["prompt"]
                )
            elif args.group == "search":
                _emit(
                    api.search(
                        service.access_token(frozenset({"artifacts:read"})),
                        query=args.query,
                        image_path=args.image,
                        artifact_id=args.artifact,
                        namespace=args.namespace,
                        mime_types=args.mime_type,
                        created_after=args.created_after,
                        limit=args.limit,
                    )
                )
            elif args.group == "caption":
                if args.capture_input and args.input is None:
                    raise CliError("--capture-input requires a local input image")
                required_scopes = {"images:understand"}
                if args.capture_input:
                    required_scopes.add("artifacts:write")
                token = service.access_token(frozenset(required_scopes))
                artifact_id = args.artifact
                input_path = args.input
                if args.capture_input:
                    uploaded = api.upload_artifact(
                        token, args.input, namespace=args.capture_namespace, kind="image"
                    )
                    artifact_id = uploaded["artifact_id"]
                    input_path = None
                result = api.caption(
                    token,
                    input_path=input_path,
                    artifact_id=artifact_id,
                    instruction=args.instruction,
                    max_output_tokens=args.max_output_tokens,
                )
                print(
                    json.dumps(result, indent=2, sort_keys=True) if args.json else result["caption"]
                )
            elif args.group == "generate":
                image = api.generate(
                    service.access_token(
                        frozenset(
                            {"images:generate", "jobs:read", "artifacts:read", "artifacts:access"}
                        )
                    ),
                    prompt=args.prompt,
                    width=args.width,
                    height=args.height,
                    seed=args.seed,
                    optimize=args.optimize,
                    wait_seconds=args.wait,
                    allow_long_wait=args.allow_long_wait,
                )
                save_bytes_exclusive(image.data, args.output)
                print(f"Saved {image.width}x{image.height} image to {args.output}.")
            elif args.group == "edit":
                run_edit(args, service, api)
            elif args.group == "batch":
                _run_batch(args, service, api)
            else:
                return run_auth_command(args, service, DEFAULT_LOGIN_SCOPES, _announce)
        return 0
    except CliError as error:
        print(f"error: {error}", file=sys.stderr)
        if help_topic := _error_help_topic(args):
            print(f"help: Run `image help {help_topic}` for recovery guidance.", file=sys.stderr)
        return 2


def _announce(user_code: str, verification_uri_complete: str) -> None:
    print(f"Open {verification_uri_complete}")
    print(f"Code: {user_code}")


def _show_help(topic: Sequence[str]) -> int:
    return show_help(parser(), topic)


def _error_help_topic(args: argparse.Namespace) -> str | None:
    group = getattr(args, "group", None)
    command = getattr(args, "command", None)
    if (group, command) == ("job", "submit"):
        return "job submit recovery"
    if (group, command) == ("artifact", "upload"):
        return "artifact upload recovery"
    candidates = tuple(
        candidate
        for candidate in (
            " ".join(value for value in (group, command) if isinstance(value, str)),
            group,
        )
        if isinstance(candidate, str) and candidate
    )
    return next(
        (candidate for candidate in candidates if candidate in TOPICS or candidate in GUIDES),
        None,
    )


def _summary(group: str, result: dict[str, object]) -> str:
    items = result.get("items")
    count = len(items) if isinstance(items, list) else 0
    revision = result.get("catalog_revision", "unknown")
    label = "capabilities" if group == "capabilities" else "model profiles"
    return f"Native API V4 {label}: {count} (catalog {revision})"


def _add_page_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--created-after")
    command.add_argument("--created-before")
    command.add_argument("--cursor")
    command.add_argument("--limit", type=int, default=20)


def _page_params(
    args: argparse.Namespace, repeated: tuple[str, ...]
) -> list[tuple[str, QueryScalar]]:
    params = [(name, value) for name in repeated for value in getattr(args, name)]
    params.extend(
        (name, value)
        for name in ("created_after", "created_before", "cursor", "limit")
        if (value := getattr(args, name)) is not None
    )
    return params


def _run_job(args: argparse.Namespace, service: AuthService, api: V4ApiClient) -> None:
    if args.command == "submit":
        result = api.submit_job(
            service.access_token(frozenset({"jobs:submit"})),
            request=load_json_object(args.request),
        )
    elif args.command == "cancel":
        result = api.cancel_job(service.access_token(frozenset({"jobs:cancel"})), args.job_id)
    else:
        token = service.access_token(frozenset({"jobs:read"}))
        if args.command == "list":
            result = api.list_jobs(token, params=_page_params(args, ("status", "operation")))
        elif args.command == "show":
            result = api.get_job(token, args.job_id)
        elif args.command == "previews":
            result = api.job_previews(token, args.job_id)
        else:
            result = api.job_preview_access(token, args.job_id, args.step_id, args.output)
    _emit(result)


def _run_artifact(args: argparse.Namespace, service: AuthService, api: V4ApiClient) -> None:
    scopes = {
        "delete": frozenset({"artifacts:delete"}),
        "download": frozenset({"artifacts:read", "artifacts:access"}),
        "upload": frozenset({"artifacts:write"}),
    }.get(args.command, frozenset({"artifacts:read"}))
    token = service.access_token(scopes)
    if args.command == "list":
        params = _page_params(args, ("state", "kind"))
        if args.namespace is not None:
            params.append(("namespace", args.namespace))
        result = api.list_artifacts(token, params=params)
    elif args.command == "show":
        result = api.get_artifact(token, args.artifact_id)
    elif args.command == "download":
        result = api.download_artifact(token, args.artifact_id, args.output)
    elif args.command == "upload":
        result = api.upload_artifact(token, args.input, namespace=args.namespace, kind=args.kind)
    else:
        if not args.force:
            confirmation = input(f"Type Artifact ID {args.artifact_id} to confirm tombstoning: ")
            if confirmation != args.artifact_id:
                raise CliError("Artifact deletion confirmation did not match")
        result = api.delete_artifact(token, args.artifact_id)
    _emit(result)


def _emit(result: object) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))


def _run_batch(args: argparse.Namespace, service: AuthService, api: V4ApiClient) -> None:
    read_scopes = {"batches:execute", "campaigns:read", "jobs:cancel"}
    if args.command == "list":
        params: list[tuple[str, QueryScalar]] = [("limit", args.limit)]
        if args.cursor is not None:
            params.insert(0, ("cursor", args.cursor))
        result = api.list_campaigns(service.access_token(frozenset(read_scopes)), params=params)
    elif args.command == "plan":
        result = api.create_batch_plan(
            service.access_token(frozenset({"batches:plan"})),
            intent=args.intent,
            width=args.width,
            height=args.height,
            candidate_count=args.count,
            root_seed=args.seed,
            optimize=not args.no_optimize,
        )
    elif args.command in {"run", "iterate"}:
        scopes = {"batches:execute", "campaigns:write"}
        if args.wait:
            scopes.update(read_scopes)
        if args.command == "iterate":
            scopes.update({"batches:plan", "campaigns:read"})
        result = api.create_campaign(
            service.access_token(frozenset(scopes)),
            plan_id=args.plan_id,
            max_cost_usd=args.max_cost,
            allow_partial=args.allow_partial,
            wait_seconds=args.wait,
            allow_long_wait=args.allow_long_wait,
            score_threshold=getattr(args, "threshold", None),
            max_rounds=getattr(args, "max_rounds", 3),
        )
    else:
        if args.command == "cancel":
            scopes = {"jobs:cancel"}
        else:
            scopes = read_scopes | ({"jobs:read"} if args.command == "results" else set())
        handler = {
            "status": api.get_campaign,
            "cancel": api.cancel_campaign,
            "evaluate": api.campaign_evaluation,
            "results": api.campaign_results,
        }[args.command]
        result = handler(service.access_token(frozenset(scopes)), args.campaign_id)
    _emit(result)
