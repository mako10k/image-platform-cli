import argparse
import json
import sys
import webbrowser
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path

import httpx

from .api import (
    ImageApiClient,
    require_available_output,
    save_deterministic_edit,
    save_image,
    save_segmentation_outputs,
)
from .config import Config
from .credentials import KeyringCredentialStore
from .errors import CliError
from .oauth import DeviceFlowClient
from .service import AuthService
from .tokens import TokenValidator

DEFAULT_LOGIN_SCOPES = (
    "images:generate",
    "campaigns:read",
    "artifacts:read",
    "batches:plan",
    "batches:execute",
    "campaigns:write",
    "jobs:cancel",
    "images:edit",
    "images:understand",
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="image")
    groups = root.add_subparsers(dest="group", required=True)
    auth = groups.add_parser("auth")
    commands = auth.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login")
    login.add_argument("--scope", action="append", default=[])
    commands.add_parser("status")
    commands.add_parser("logout")
    generate = groups.add_parser("generate")
    generate.add_argument("prompt")
    generate.add_argument("--output", "-o", type=Path, required=True)
    generate.add_argument("--width", type=int, default=1024)
    generate.add_argument("--height", type=int, default=1024)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--optimize", action="store_true")
    generate.add_argument("--wait", type=int, default=30)
    generate.add_argument("--allow-long-wait", action="store_true")
    prompt = groups.add_parser("prompt")
    prompt_commands = prompt.add_subparsers(dest="command", required=True)
    optimize = prompt_commands.add_parser("optimize")
    optimize.add_argument("prompt")
    optimize.add_argument("--width", type=int)
    optimize.add_argument("--height", type=int)
    optimize.add_argument("--seed", type=int)
    job = groups.add_parser("job")
    job_commands = job.add_subparsers(dest="command", required=True)
    job_list = job_commands.add_parser("list")
    job_list.add_argument("--status", action="append", default=[])
    job_list.add_argument("--operation", action="append", default=[])
    _add_collection_arguments(job_list)
    job_show = job_commands.add_parser("show")
    job_show.add_argument("job_id")
    job_show.add_argument("--json", action="store_true")
    job_cancel = job_commands.add_parser("cancel")
    job_cancel.add_argument("job_id")
    job_cancel.add_argument("--json", action="store_true")
    job_previews = job_commands.add_parser("previews")
    job_previews.add_argument("job_id")
    job_previews.add_argument("--json", action="store_true")
    artifact = groups.add_parser("artifact")
    artifact_commands = artifact.add_subparsers(dest="command", required=True)
    artifact_list = artifact_commands.add_parser("list")
    artifact_list.add_argument("--state", action="append", default=[])
    artifact_list.add_argument("--kind", action="append", default=[])
    artifact_list.add_argument("--namespace")
    _add_collection_arguments(artifact_list)
    artifact_show = artifact_commands.add_parser("show")
    artifact_show.add_argument("artifact_id")
    artifact_show.add_argument("--json", action="store_true")
    artifact_download = artifact_commands.add_parser("download")
    artifact_download.add_argument("artifact_id")
    artifact_download.add_argument("--output", "-o", type=Path, required=True)
    search = groups.add_parser("search")
    search.add_argument("query")
    search.add_argument("--namespace", default="default")
    search.add_argument("--mime-type", action="append", default=[])
    search.add_argument("--created-after")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--json", action="store_true")
    batch = groups.add_parser("batch")
    batch_commands = batch.add_subparsers(dest="command", required=True)
    batch_plan = batch_commands.add_parser("plan")
    batch_plan.add_argument("intent")
    batch_plan.add_argument("--width", type=int, default=1024)
    batch_plan.add_argument("--height", type=int, default=1024)
    batch_plan.add_argument("--count", type=int, default=1)
    batch_plan.add_argument("--seed", type=int)
    batch_plan.add_argument("--no-optimize", action="store_true")
    batch_plan.add_argument("--json", action="store_true")
    batch_run = batch_commands.add_parser("run")
    batch_run.add_argument("plan_id")
    batch_run.add_argument("--max-cost", type=Decimal, required=True)
    batch_run.add_argument("--allow-partial", action="store_true")
    batch_run.add_argument("--wait", type=int, default=0)
    batch_run.add_argument("--allow-long-wait", action="store_true")
    batch_run.add_argument("--json", action="store_true")
    for command in ("status", "cancel", "results"):
        parser_ = batch_commands.add_parser(command)
        parser_.add_argument("campaign_id")
        parser_.add_argument("--json", action="store_true")
    capabilities = groups.add_parser("capabilities")
    capabilities.add_argument("--json", action="store_true")
    edit = groups.add_parser("edit")
    edit_commands = edit.add_subparsers(dest="command", required=True)
    image_to_image = edit_commands.add_parser(
        "image-to-image",
        aliases=["i2i"],
        description=(
            "Run descriptive Stable Diffusion image-to-image. PROMPT describes the desired "
            "final image; it is not an instruction-edit command."
        ),
    )
    image_to_image.add_argument("prompt", help="description of the desired final image")
    image_to_image.add_argument("--input", type=Path, required=True)
    image_to_image.add_argument("--output", "-o", type=Path, required=True)
    image_to_image.add_argument("--profile", default="i2i-stable-diffusion-v1-5")
    image_to_image.add_argument("--negative-prompt")
    image_to_image.add_argument("--strength", type=Decimal, default=Decimal("0.75"))
    image_to_image.add_argument("--guidance-scale", type=Decimal, default=Decimal("7.5"))
    image_to_image.add_argument("--steps", type=int, default=25)
    image_to_image.add_argument("--seed", type=int)
    image_to_image.add_argument("--width", type=int)
    image_to_image.add_argument("--height", type=int)
    segment = edit_commands.add_parser("segment")
    segment.add_argument("--input", type=Path, required=True)
    selectors = segment.add_mutually_exclusive_group(required=True)
    selectors.add_argument("--text")
    selectors.add_argument("--box", type=_coordinates(4, "box"))
    selectors.add_argument("--point", type=_coordinates(2, "point"), action="append")
    segment.add_argument(
        "--negative-point", type=_coordinates(2, "negative point"), action="append"
    )
    segment.add_argument("--mask-output", type=Path)
    segment.add_argument("--foreground-output", type=Path)
    segment.add_argument("--background-output", type=Path)
    composite = edit_commands.add_parser("composite")
    composite.add_argument("--background", type=Path, required=True)
    composite.add_argument("--overlay", type=Path, required=True)
    composite.add_argument("--mask", type=Path)
    composite.add_argument("--output", "-o", type=Path, required=True)
    composite.add_argument(
        "--matrix",
        type=_decimals(6, "matrix"),
        default=(Decimal(1), Decimal(0), Decimal(0), Decimal(1), Decimal(0), Decimal(0)),
    )
    composite.add_argument("--opacity", type=Decimal, default=Decimal(1))
    composite.add_argument("--crop", type=_coordinates(4, "crop"))
    run_program = edit_commands.add_parser("run")
    run_program.add_argument("--program", type=Path, required=True)
    run_program.add_argument("--input", action="append", default=[], metavar="NAME=PATH")
    run_program.add_argument("--mask", action="append", default=[], metavar="NAME=PATH")
    run_program.add_argument("--output", "-o", type=Path)
    run_program.add_argument("--dry-run", action="store_true")
    inpaint = edit_commands.add_parser("inpaint")
    inpaint.add_argument("prompt")
    inpaint.add_argument("--input", type=Path, required=True)
    inpaint.add_argument("--mask", type=Path, required=True)
    inpaint.add_argument("--output", "-o", type=Path, required=True)
    inpaint.add_argument("--profile", default="inpaint-stable-diffusion-v1-5")
    inpaint.add_argument("--seed", type=int)
    inpaint.add_argument(
        "--safety-filter",
        choices=("default", "enabled", "disabled"),
        default="default",
    )
    return root


def _add_collection_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--created-after")
    command.add_argument("--created-before")
    command.add_argument("--page-size", type=int, default=20)
    command.add_argument("--cursor")
    command.add_argument("--all", dest="all_pages", action="store_true")
    command.add_argument("--max-items", type=int)
    command.add_argument("--json", action="store_true")


def _coordinates(count: int, name: str) -> Callable[[str], tuple[int, ...]]:
    def parse(value: str) -> tuple[int, ...]:
        try:
            coordinates = tuple(int(part) for part in value.split(","))
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                f"{name} must contain comma-separated integers"
            ) from error
        if len(coordinates) != count:
            raise argparse.ArgumentTypeError(f"{name} requires {count} comma-separated integers")
        return coordinates

    return parse


def _decimals(count: int, name: str) -> Callable[[str], tuple[Decimal, ...]]:
    def parse(value: str) -> tuple[Decimal, ...]:
        try:
            values = tuple(Decimal(part) for part in value.split(","))
        except Exception as error:
            raise argparse.ArgumentTypeError(
                f"{name} must contain comma-separated decimals"
            ) from error
        if len(values) != count:
            raise argparse.ArgumentTypeError(f"{name} requires {count} comma-separated decimals")
        return values

    return parse


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = Config.staging()
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as http:
            service = AuthService(
                config,
                DeviceFlowClient(http, config.issuer, config.client_id),
                TokenValidator(http, config.issuer, config.audience),
                KeyringCredentialStore(),
            )
            if args.group == "generate":
                require_available_output(args.output)
                access_token = service.access_token(
                    frozenset({"images:generate", "campaigns:read", "artifacts:read"})
                )
                image = ImageApiClient(http, config.api_base_url).generate(
                    access_token,
                    prompt=args.prompt,
                    width=args.width,
                    height=args.height,
                    seed=args.seed,
                    optimize=args.optimize,
                    wait_seconds=args.wait,
                    allow_long_wait=args.allow_long_wait,
                )
                save_image(image, args.output)
                print(f"Saved {image.width}x{image.height} PNG to {args.output}.")
                print(f"SHA-256: {image.sha256}")
                print(f"Seed: {image.seed}")
            elif args.group == "prompt" and args.command == "optimize":
                access_token = service.access_token(frozenset({"batches:plan"}))
                optimized = ImageApiClient(http, config.api_base_url).optimize_prompt(
                    access_token,
                    prompt=args.prompt,
                    width=args.width,
                    height=args.height,
                    seed=args.seed,
                )
                print(optimized)
            elif args.group == "job":
                _run_job_command(args, service, ImageApiClient(http, config.api_base_url))
            elif args.group == "artifact":
                _run_artifact_command(args, service, ImageApiClient(http, config.api_base_url))
            elif args.group == "search":
                access_token = service.access_token(frozenset({"artifacts:read"}))
                result = ImageApiClient(http, config.api_base_url).search(
                    access_token,
                    query=args.query,
                    namespace=args.namespace,
                    mime_types=args.mime_type,
                    created_after=args.created_after,
                    limit=args.limit,
                )
                _emit(result, args.json)
            elif args.group == "batch":
                _run_batch_command(args, service, ImageApiClient(http, config.api_base_url))
            elif args.group == "capabilities":
                access_token = service.access_token(frozenset())
                result = ImageApiClient(http, config.api_base_url).capabilities(access_token)
                _emit(result, args.json)
            elif args.group == "edit":
                api = ImageApiClient(http, config.api_base_url)
                if args.command in {"image-to-image", "i2i"}:
                    require_available_output(args.output)
                    image = api.image_to_image(
                        service.access_token(frozenset({"images:edit"})),
                        prompt=args.prompt,
                        input_path=args.input,
                        profile=args.profile,
                        negative_prompt=args.negative_prompt,
                        strength=args.strength,
                        guidance_scale=args.guidance_scale,
                        inference_steps=args.steps,
                        seed=args.seed,
                        width=args.width,
                        height=args.height,
                    )
                    save_image(image, args.output)
                    print(f"Saved {image.width}x{image.height} PNG to {args.output}.")
                    print(f"SHA-256: {image.sha256}")
                    print(f"Seed: {image.seed}")
                    print(f"Model: {image.model_id}@{image.model_revision}")
                    print(f"Compute cost USD: {image.measured_compute_cost_usd}")
                elif args.command == "segment":
                    outputs = (args.mask_output, args.foreground_output, args.background_output)
                    selected_outputs = tuple(output for output in outputs if output is not None)
                    if not selected_outputs:
                        raise CliError("at least one segmentation output is required")
                    if len(set(selected_outputs)) != len(selected_outputs):
                        raise CliError("segmentation output paths must be distinct")
                    for output in selected_outputs:
                        require_available_output(output)
                    if args.negative_point and not args.point:
                        raise CliError("negative points require at least one positive --point")
                    positive = [(x, y, True) for x, y in (args.point or [])]
                    negative = [(x, y, False) for x, y in (args.negative_point or [])]
                    segmented = api.segment(
                        service.access_token(frozenset({"images:understand"})),
                        input_path=args.input,
                        text=args.text,
                        points=positive + negative,
                        box=tuple(args.box) if args.box is not None else None,
                    )
                    save_segmentation_outputs(
                        segmented,
                        mask_output=args.mask_output,
                        foreground_output=args.foreground_output,
                        background_output=args.background_output,
                    )
                    print(f"Saved {segmented.width}x{segmented.height} segmentation outputs.")
                    print(f"Mask SHA-256: {segmented.mask_sha256}")
                elif args.command == "composite":
                    require_available_output(args.output)
                    composite_result = api.composite(
                        service.access_token(frozenset({"images:edit"})),
                        background_path=args.background,
                        overlay_path=args.overlay,
                        mask_path=args.mask,
                        transform=tuple(args.matrix),
                        opacity=args.opacity,
                        crop=tuple(args.crop) if args.crop is not None else None,
                    )
                    save_deterministic_edit(composite_result, args.output)
                    print(
                        f"Saved {composite_result.width}x{composite_result.height} PNG "
                        f"to {args.output}."
                    )
                    print(f"SHA-256: {composite_result.sha256}")
                    print(f"Program SHA-256: {composite_result.program_sha256}")
                elif args.command == "run":
                    program, inputs, masks = api.load_deterministic_program(
                        args.program,
                        input_bindings=args.input,
                        mask_bindings=args.mask,
                    )
                    if args.dry_run:
                        print(json.dumps(program, sort_keys=True, separators=(",", ":")))
                    else:
                        if args.output is None:
                            raise CliError("--output is required unless --dry-run is used")
                        require_available_output(args.output)
                        program_result = api.run_deterministic_program(
                            service.access_token(frozenset({"images:edit"})),
                            program=program,
                            input_paths=inputs,
                            mask_paths=masks,
                        )
                        save_deterministic_edit(program_result, args.output)
                        print(
                            f"Saved {program_result.width}x{program_result.height} PNG "
                            f"to {args.output}."
                        )
                        print(f"SHA-256: {program_result.sha256}")
                        print(f"Program SHA-256: {program_result.program_sha256}")
                        for (
                            command_id,
                            operation,
                            normalized_sha,
                            pixel_sha,
                        ) in program_result.command_receipts:
                            print(
                                f"Command {command_id} ({operation}): "
                                f"normalized={normalized_sha} pixels={pixel_sha}"
                            )
                else:
                    require_available_output(args.output)
                    inpainted = api.inpaint(
                        service.access_token(frozenset({"images:edit"})),
                        prompt=args.prompt,
                        input_path=args.input,
                        mask_path=args.mask,
                        profile=args.profile,
                        seed=args.seed,
                        safety_filter=args.safety_filter,
                    )
                    save_image(inpainted, args.output)
                    print(f"Saved {inpainted.width}x{inpainted.height} PNG to {args.output}.")
                    print(f"SHA-256: {inpainted.sha256}")
                    print(f"Seed: {inpainted.seed}")
                    print(f"Model: {inpainted.model_id}@{inpainted.model_revision}")
                    print(f"Compute cost USD: {inpainted.measured_compute_cost_usd}")
                    print(
                        "Safety filter: "
                        f"requested={inpainted.safety_filter_requested} "
                        f"effective={inpainted.safety_filter_effective} "
                        f"outcome={inpainted.safety_filter_outcome}"
                    )
            elif args.command == "login":
                login_credential = service.login(
                    tuple(args.scope or DEFAULT_LOGIN_SCOPES),
                    _announce,
                )
                print(
                    f"Logged in as {login_credential.subject} for organization "
                    f"{login_credential.organization_id}."
                )
            elif args.command == "status":
                status_credential = service.status()
                if status_credential is None:
                    print("Not logged in.")
                    return 1
                print(f"User: {status_credential.subject}")
                print(f"Organization: {status_credential.organization_id}")
                print(f"Scopes: {' '.join(status_credential.scopes)}")
            elif args.command == "logout":
                print("Logged out." if service.logout() else "Not logged in.")
        return 0
    except CliError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _run_job_command(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    if args.command == "cancel":
        token = service.access_token(frozenset({"jobs:cancel"}))
        _emit(api.cancel_job(token, args.job_id), args.json)
        return
    token = service.access_token(frozenset({"campaigns:read"}))
    if args.command == "list":
        max_items = _pagination_limit(args)
        result = api.list_jobs(
            token,
            statuses=args.status,
            operations=args.operation,
            created_after=args.created_after,
            created_before=args.created_before,
            cursor=args.cursor,
            page_size=args.page_size,
            max_items=max_items,
        )
    elif args.command == "show":
        result = api.get_job(token, args.job_id)
    else:
        result = api.get_job_previews(token, args.job_id)
    _emit(result, args.json)


def _run_artifact_command(
    args: argparse.Namespace, service: AuthService, api: ImageApiClient
) -> None:
    token = service.access_token(frozenset({"artifacts:read"}))
    if args.command == "list":
        result = api.list_artifacts(
            token,
            states=args.state,
            kinds=args.kind,
            namespace=args.namespace,
            created_after=args.created_after,
            created_before=args.created_before,
            cursor=args.cursor,
            page_size=args.page_size,
            max_items=_pagination_limit(args),
        )
        _emit(result, args.json)
    elif args.command == "show":
        _emit(api.get_artifact(token, args.artifact_id), args.json)
    else:
        result = api.download_artifact(token, args.artifact_id, args.output)
        artifact = result.get("result", {}).get("artifact", {})
        print(f"Saved Artifact {args.artifact_id} to {args.output}.")
        if isinstance(artifact, dict) and isinstance(artifact.get("sha256"), str):
            print(f"SHA-256: {artifact['sha256']}")


def _run_batch_command(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    if args.command == "plan":
        token = service.access_token(frozenset({"batches:plan"}))
        result = api.create_batch_plan(
            token,
            intent=args.intent,
            width=args.width,
            height=args.height,
            candidate_count=args.count,
            root_seed=args.seed,
            optimize=not args.no_optimize,
        )
    elif args.command == "run":
        token = service.access_token(
            frozenset({"batches:execute", "campaigns:write", "campaigns:read"})
        )
        result = api.create_campaign(
            token,
            plan_id=args.plan_id,
            max_cost_usd=args.max_cost,
            allow_partial=args.allow_partial,
            wait_seconds=args.wait,
            allow_long_wait=args.allow_long_wait,
        )
    elif args.command == "cancel":
        token = service.access_token(frozenset({"jobs:cancel"}))
        result = api.cancel_campaign(token, args.campaign_id)
    elif args.command == "results":
        token = service.access_token(frozenset({"campaigns:read"}))
        result = api.campaign_results(token, args.campaign_id)
    else:
        token = service.access_token(frozenset({"campaigns:read"}))
        result = api.get_campaign(token, args.campaign_id)
    _emit(result, args.json)


def _pagination_limit(args: argparse.Namespace) -> int | None:
    if args.all_pages and args.max_items is None:
        raise CliError("--all requires --max-items")
    if not args.all_pages and args.max_items is not None:
        raise CliError("--max-items requires --all")
    return int(args.max_items) if args.max_items is not None else None


def _emit(value: object, json_output: bool) -> None:
    if json_output:
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def _announce(user_code: str, verification_uri_complete: str) -> None:
    print(f"Open this URL to authorize: {verification_uri_complete}")
    print(f"Code: {user_code}")
    webbrowser.open(verification_uri_complete, new=2)


if __name__ == "__main__":
    raise SystemExit(main())
