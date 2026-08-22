import argparse
import json
import re
import sys
import webbrowser
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError

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

HELP_GUIDANCE = {
    (): ("Use `image help GROUP [COMMAND]` for detailed help.", ("image help edit",)),
    ("edit",): (
        "Discover editing primitives, deterministic programs, and model-backed operations.",
        ("image help edit run", "image capabilities --json"),
    ),
    ("edit", "run"): (
        "Validate or execute one deterministic-edit-v1 JSON program with named local inputs.",
        (
            "image edit run --program edit.json --input scene=scene.png --dry-run",
            "image edit run --program edit.json --input scene=scene.png -o result.png",
        ),
    ),
    ("edit", "replace-object"): (
        "Replace only selected mask coverage; pixels outside coverage remain from the base image.",
        (
            "image edit replace-object --base scene.png --replacement new.png --mask object.png -o result.png",
        ),
    ),
    ("edit", "replace-background"): (
        "Invert one foreground mask and replace only its background coverage.",
        (
            "image edit replace-background --base scene.png --replacement bg.png --mask foreground.png --feather 2 -o result.png",
        ),
    ),
    ("edit", "raster"): (
        "Build deterministic CPU raster recipes; inspect a child topic for exact controls.",
        ("image help edit raster crop", "image help edit raster adjust"),
    ),
    ("edit", "raster", "crop"): (
        "Crop with an exact top-left-origin x,y,width,height rectangle.",
        ("image edit raster crop --input scene.png --rect 10,20,512,512 -o crop.png",),
    ),
    ("edit", "raster", "filter"): (
        "Apply a bounded deterministic blur or unsharp-mask filter.",
        ("image edit raster filter --input scene.png --kind gaussian_blur --radius 2 -o blur.png",),
    ),
    ("edit", "raster", "adjust"): (
        "Compose hue/saturation, white-balance, and tone commands in stable order.",
        (
            "image edit raster adjust --input scene.png --hue 15 --saturation 1.1 --contrast 1.05 -o adjusted.png",
        ),
    ),
    ("edit", "raster", "grayscale"): (
        "Convert visible pixels to exact equal RGB channels using frozen Rec. 709 luminance.",
        ("image edit raster grayscale --input scene.png -o grayscale.png",),
    ),
    ("edit", "verify"): (
        "Execute the same deterministic program twice and compare every receipt and output hash.",
        ("image edit verify --program edit.json --input scene=scene.png",),
    ),
    ("edit", "matte-portrait"): (
        "Refine a person mask into bounded fractional alpha without changing source RGB.",
        (
            "image edit matte-portrait --input portrait.png --person-mask person.png --uncertainty-radius 16 -o matte.png",
        ),
    ),
    ("artifact", "delete"): (
        "Tombstone an unreferenced Artifact; shared content bytes are retained by the server.",
        (
            "image artifact delete art_123",
            "image artifact delete art_123 --force --json",
        ),
    ),
    ("batch",): (
        "Plan, launch, inspect, and download bounded generation Campaigns.",
        ("image help batch iterate", "image help batch evaluate", "image batch results ID"),
    ),
    ("batch", "iterate"): (
        "Use the server-owned rubric to evaluate and revise at most four candidates for three rounds.",
        ("image batch iterate bplan_1 --max-cost 0.24 --threshold 0.8 --wait 60 --json",),
    ),
    ("batch", "evaluate"): (
        "Show immutable round scores, reasons, cost evidence, and the Campaign stop reason.",
        ("image batch evaluate campaign_1 --json", "image batch results campaign_1 --json"),
    ),
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="image")
    groups = root.add_subparsers(dest="group", required=True)
    help_command = groups.add_parser("help", help="browse command help and examples")
    help_command.add_argument("topic", nargs="*")
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
    artifact_upload = artifact_commands.add_parser("upload")
    artifact_upload.add_argument("input", type=Path)
    artifact_upload.add_argument("--namespace", default="default")
    artifact_upload.add_argument("--kind", choices=("image", "mask"), default="image")
    artifact_upload.add_argument("--json", action="store_true")
    artifact_delete = artifact_commands.add_parser(
        "delete", help="tombstone one unreferenced Artifact"
    )
    artifact_delete.add_argument("artifact_id")
    artifact_delete.add_argument(
        "--force", action="store_true", help="skip typing the Artifact ID for confirmation"
    )
    artifact_delete.add_argument("--json", action="store_true")
    search = groups.add_parser("search")
    search_query = search.add_mutually_exclusive_group(required=True)
    search_query.add_argument("query", nargs="?")
    search_query.add_argument("--image", type=Path)
    search_query.add_argument("--artifact")
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
    batch_iterate = batch_commands.add_parser("iterate")
    batch_iterate.add_argument("plan_id")
    batch_iterate.add_argument("--max-cost", type=Decimal, required=True)
    batch_iterate.add_argument("--threshold", type=Decimal, default=Decimal("0.8"))
    batch_iterate.add_argument("--max-rounds", type=int, default=3)
    batch_iterate.add_argument("--allow-partial", action="store_true")
    batch_iterate.add_argument("--wait", type=int, default=0)
    batch_iterate.add_argument("--allow-long-wait", action="store_true")
    batch_iterate.add_argument("--json", action="store_true")
    batch_evaluate = batch_commands.add_parser("evaluate")
    batch_evaluate.add_argument("campaign_id")
    batch_evaluate.add_argument("--json", action="store_true")
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
    image_to_image_input = image_to_image.add_mutually_exclusive_group(required=True)
    image_to_image_input.add_argument("--input", type=Path)
    image_to_image_input.add_argument("--artifact")
    image_to_image.add_argument(
        "--capture-input",
        action="store_true",
        help="upload --input as an Artifact and use that immutable reference",
    )
    image_to_image.add_argument("--capture-namespace", default="default")
    image_to_image.add_argument("--output", "-o", type=Path, required=True)
    image_to_image.add_argument("--profile", default="i2i-stable-diffusion-v1-5")
    image_to_image.add_argument("--negative-prompt")
    image_to_image.add_argument("--strength", type=Decimal, default=Decimal("0.75"))
    image_to_image.add_argument("--guidance-scale", type=Decimal, default=Decimal("7.5"))
    image_to_image.add_argument("--steps", type=int, default=25)
    image_to_image.add_argument("--seed", type=int)
    image_to_image.add_argument("--width", type=int)
    image_to_image.add_argument("--height", type=int)
    caption = groups.add_parser("caption", help="caption a local or Artifact image")
    caption_input = caption.add_mutually_exclusive_group(required=True)
    caption_input.add_argument("--input", type=Path)
    caption_input.add_argument("--artifact")
    caption.add_argument(
        "--capture-input",
        action="store_true",
        help="upload --input as an Artifact and caption that immutable reference",
    )
    caption.add_argument("--capture-namespace", default="default")
    caption.add_argument("--instruction", default="Describe this image concisely.")
    caption.add_argument("--max-output-tokens", type=int, default=128)
    caption.add_argument("--json", action="store_true")
    convert = edit_commands.add_parser(
        "convert", help="deterministically convert PNG, JPEG, or WebP"
    )
    convert.add_argument("--input", type=Path, required=True)
    convert.add_argument("--output", "-o", type=Path, required=True)
    convert.add_argument("--format", choices=("png", "jpeg", "webp"), required=True)
    convert.add_argument("--quality", type=int, default=90)
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
    matte = edit_commands.add_parser(
        "matte-portrait", help="refine a person mask with registry-pinned portrait matting"
    )
    matte.add_argument("--input", type=Path, required=True)
    matte.add_argument("--person-mask", type=Path, required=True)
    matte.add_argument("--uncertainty-radius", type=int, default=16)
    matte.add_argument("--output", "-o", type=Path, required=True)
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
    composite.add_argument(
        "--composite",
        choices=("source_over", "replace", "multiply", "screen"),
        default="source_over",
    )
    composite.add_argument("--crop", type=_coordinates(4, "crop"))
    run_program = edit_commands.add_parser("run")
    run_program.add_argument("--program", type=Path, required=True)
    run_program.add_argument("--input", action="append", default=[], metavar="NAME=PATH")
    run_program.add_argument("--mask", action="append", default=[], metavar="NAME=PATH")
    run_program.add_argument("--output", "-o", type=Path)
    run_program.add_argument("--dry-run", action="store_true")
    verify_program = edit_commands.add_parser("verify")
    verify_program.add_argument("--program", type=Path, required=True)
    verify_program.add_argument("--input", action="append", default=[], metavar="NAME=PATH")
    verify_program.add_argument("--mask", action="append", default=[], metavar="NAME=PATH")
    for name in ("replace-object", "replace-background"):
        replacement = edit_commands.add_parser(name)
        replacement.add_argument("--base", type=Path, required=True)
        replacement.add_argument("--replacement", type=Path, required=True)
        replacement.add_argument("--mask", type=Path, action="append", required=True)
        replacement.add_argument(
            "--combine", choices=("union", "intersection", "subtract"), default="union"
        )
        replacement.add_argument("--threshold", type=Decimal)
        replacement.add_argument("--invert", action="store_true")
        morphology = replacement.add_mutually_exclusive_group()
        morphology.add_argument("--dilate", type=int)
        morphology.add_argument("--erode", type=int)
        replacement.add_argument("--padding", type=int, help="alias for mask dilation")
        replacement.add_argument("--feather", type=Decimal)
        replacement.add_argument("--output", "-o", type=Path)
        replacement.add_argument("--dry-run", action="store_true")
    raster = edit_commands.add_parser("raster")
    raster_commands = raster.add_subparsers(dest="raster_command", required=True)
    raster_crop = raster_commands.add_parser("crop")
    raster_crop.add_argument("--rect", type=_coordinates(4, "rect"), required=True)
    raster_filter = raster_commands.add_parser("filter")
    raster_filter.add_argument(
        "--kind", choices=("gaussian_blur", "box_blur", "unsharp_mask"), required=True
    )
    raster_filter.add_argument("--radius", type=Decimal, required=True)
    raster_filter.add_argument("--amount", type=Decimal, default=Decimal(1))
    raster_adjust = raster_commands.add_parser("adjust")
    raster_grayscale = raster_commands.add_parser("grayscale")
    raster_adjust.add_argument("--hue", type=Decimal)
    raster_adjust.add_argument("--saturation", type=Decimal)
    raster_adjust.add_argument("--temperature", type=int)
    raster_adjust.add_argument("--tint", type=Decimal, default=Decimal(0))
    raster_adjust.add_argument("--exposure", type=Decimal)
    raster_adjust.add_argument("--brightness", type=Decimal)
    raster_adjust.add_argument("--contrast", type=Decimal)
    raster_auto_crop = raster_commands.add_parser("auto-crop")
    raster_auto_crop.add_argument("--mask", type=Path, required=True)
    raster_auto_crop.add_argument("--threshold", type=Decimal, default=Decimal("0.01"))
    raster_auto_crop.add_argument("--padding", type=int, default=0)
    raster_shape = raster_commands.add_parser("shape")
    raster_shape.add_argument("--kind", choices=("rectangle", "ellipse"), required=True)
    raster_shape.add_argument("--rect", type=_coordinates(4, "rect"), required=True)
    raster_shape.add_argument("--fill", type=_rgba)
    raster_shape.add_argument("--stroke", type=_rgba)
    raster_shape.add_argument("--stroke-width", type=int, default=1)
    raster_text = raster_commands.add_parser("text")
    raster_text.add_argument("text")
    raster_text.add_argument("--position", type=_coordinates(2, "position"), required=True)
    raster_text.add_argument("--font-id", required=True)
    raster_text.add_argument("--font-sha256", required=True)
    raster_text.add_argument("--font-size", type=int, required=True)
    raster_text.add_argument("--fill", type=_rgba, required=True)
    raster_text.add_argument("--stroke", type=_rgba)
    raster_text.add_argument("--stroke-width", type=int, default=0)
    raster_color_match = raster_commands.add_parser("color-match")
    raster_color_match.add_argument("--reference", type=Path, required=True)
    raster_color_match.add_argument(
        "--algorithm",
        choices=("lab_mean_std_v1", "lab_histogram_256_v1"),
        default="lab_mean_std_v1",
    )
    raster_color_match.add_argument("--strength", type=Decimal, default=Decimal(1))
    raster_color_match.add_argument("--preserve-luminance", action="store_true")
    raster_resize = raster_commands.add_parser("resize")
    raster_resize.add_argument("--width", type=int, required=True)
    raster_resize.add_argument("--height", type=int, required=True)
    raster_resize.add_argument("--fit", action="store_true", help="contain within a canvas")
    raster_flip = raster_commands.add_parser("flip")
    raster_flip.add_argument("--axis", choices=("horizontal", "vertical"), required=True)
    raster_rotate = raster_commands.add_parser("rotate")
    raster_rotate.add_argument("--degrees", type=int, choices=(90, 180, 270), required=True)
    raster_canvas = raster_commands.add_parser("canvas")
    raster_canvas.add_argument("--width", type=int, required=True)
    raster_canvas.add_argument("--height", type=int, required=True)
    raster_canvas.add_argument("--x", type=int, default=0)
    raster_canvas.add_argument("--y", type=int, default=0)
    raster_canvas.add_argument("--background", type=_rgba, default={"r": 0, "g": 0, "b": 0, "a": 0})
    raster_project = raster_commands.add_parser("project-quad")
    raster_project.add_argument("--texture", type=Path, required=True)
    raster_project.add_argument("--destination", type=_coordinates(8, "destination"), required=True)
    raster_project.add_argument(
        "--composite",
        choices=("source_over", "replace", "multiply", "screen"),
        default="source_over",
    )
    raster_mesh = raster_commands.add_parser("mesh")
    raster_mesh.add_argument("--texture", type=Path, required=True)
    raster_mesh.add_argument("--mesh-spec", type=Path, required=True)
    for raster_command in (
        raster_crop,
        raster_filter,
        raster_adjust,
        raster_grayscale,
        raster_auto_crop,
        raster_shape,
        raster_text,
        raster_color_match,
        raster_resize,
        raster_flip,
        raster_rotate,
        raster_canvas,
        raster_project,
        raster_mesh,
    ):
        raster_command.add_argument("--input", type=Path, required=True)
        raster_command.add_argument("--output", "-o", type=Path)
        raster_command.add_argument("--dry-run", action="store_true")
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


def _rgba(value: str) -> dict[str, int]:
    coordinates = _coordinates(4, "color")(value)
    if any(channel < 0 or channel > 255 for channel in coordinates):
        raise argparse.ArgumentTypeError("color channels must be from 0 through 255")
    return dict(zip(("r", "g", "b", "a"), coordinates, strict=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.group == "help":
        return _show_help(tuple(args.topic))
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
                    image_path=args.image,
                    artifact_id=args.artifact,
                    namespace=args.namespace,
                    mime_types=args.mime_type,
                    created_after=args.created_after,
                    limit=args.limit,
                )
                _emit(result, args.json)
            elif args.group == "caption":
                scopes = {"images:understand"}
                if args.artifact is not None or args.capture_input:
                    scopes.add("artifacts:read")
                if args.capture_input:
                    scopes.add("batches:execute")
                access_token = service.access_token(frozenset(scopes))
                input_path, artifact_id = _captured_input(
                    args,
                    api=ImageApiClient(http, config.api_base_url),
                    access_token=access_token,
                )
                result = ImageApiClient(http, config.api_base_url).caption(
                    access_token,
                    input_path=input_path,
                    artifact_id=artifact_id,
                    instruction=args.instruction,
                    max_output_tokens=args.max_output_tokens,
                )
                if args.capture_input:
                    result["input_artifact_id"] = artifact_id
                _emit(result, args.json)
            elif args.group == "batch":
                _run_batch_command(args, service, ImageApiClient(http, config.api_base_url))
            elif args.group == "capabilities":
                access_token = service.access_token(frozenset())
                result = ImageApiClient(http, config.api_base_url).capabilities(access_token)
                _emit(result, args.json)
            elif args.group == "edit":
                _run_edit_command(args, service, ImageApiClient(http, config.api_base_url))
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


def _show_help(topic: tuple[str, ...]) -> int:
    selected = parser()
    traversed: list[str] = []
    for name in topic:
        choices = _subparser_choices(selected)
        if name not in choices:
            available = ", ".join(sorted(choices)) or "none"
            print(
                f"error: unknown help topic {' '.join((*traversed, name))}; available: {available}",
                file=sys.stderr,
            )
            return 2
        selected = choices[name]
        traversed.append(name)
    print(selected.format_help().rstrip())
    guidance, examples = HELP_GUIDANCE.get(
        tuple(traversed),
        (
            "Review the bounded options below; use --dry-run when the command offers it.",
            (f"{selected.prog} --help",),
        ),
    )
    if guidance:
        print(f"\nGUIDANCE\n{guidance}")
    if examples:
        print("\nEXAMPLES")
        for example in examples:
            print(f"  {example}")
    choices = _subparser_choices(selected)
    if choices:
        print("\nTOPICS")
        for name, child in sorted(choices.items()):
            print(f"  {name:<20} {child.description or child.prog}")
    if traversed:
        parent = " ".join(traversed[:-1])
        suffix = f" {parent}" if parent else ""
        print(f"\nRELATED\n  image help{suffix}")
    return 0


def _subparser_choices(command: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in command._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


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


def _run_edit_command(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    handlers = {
        "image-to-image": _run_image_to_image,
        "i2i": _run_image_to_image,
        "convert": _run_convert,
        "segment": _run_segmentation,
        "matte-portrait": _run_portrait_matting,
        "composite": _run_composite,
        "run": _run_deterministic_program,
        "replace-object": _run_replacement,
        "replace-background": _run_replacement,
        "raster": _run_raster,
        "verify": _run_reproducibility_check,
        "inpaint": _run_inpaint,
    }
    handlers[args.command](args, service, api)


def _run_image_to_image(
    args: argparse.Namespace, service: AuthService, api: ImageApiClient
) -> None:
    require_available_output(args.output)
    scopes = {"images:edit"}
    if args.artifact is not None or args.capture_input:
        scopes.add("artifacts:read")
    if args.capture_input:
        scopes.add("batches:execute")
    token = service.access_token(frozenset(scopes))
    input_path, artifact_id = _captured_input(args, api=api, access_token=token)
    image = api.image_to_image(
        token,
        prompt=args.prompt,
        input_path=input_path,
        artifact_id=artifact_id,
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
    if args.capture_input:
        print(f"Input Artifact: {artifact_id}")


def _run_convert(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    require_available_output(args.output)
    if args.format == "png" and args.quality != 90:
        raise CliError("--quality is not configurable for PNG")
    if not 1 <= args.quality <= 100:
        raise CliError("--quality must be from 1 through 100")
    program = {
        "revision": "deterministic-edit-v1",
        "inputs": {"source": "image"},
        "source_input": "source",
        "commands": [{"id": "convert", "op": "convert"}],
        "encoding": {
            "format": args.format,
            "quality": args.quality,
            "alpha_policy": "preserve_or_flatten_white_v1",
        },
    }
    result = api.run_deterministic_program(
        service.access_token(frozenset({"images:edit"})),
        program=program,
        input_paths={"source": args.input},
        mask_paths={},
    )
    save_deterministic_edit(result, args.output)
    _print_deterministic_result(result, args.output)


def _captured_input(
    args: argparse.Namespace,
    *,
    api: ImageApiClient,
    access_token: str,
) -> tuple[Path | None, str | None]:
    if not args.capture_input:
        return args.input, args.artifact
    if args.input is None or args.artifact is not None:
        raise CliError("--capture-input requires --input and cannot be used with --artifact")
    uploaded = api.upload_artifact(
        access_token,
        args.input,
        namespace=args.capture_namespace,
        kind="image",
    )
    artifact_id = uploaded.get("artifact_id")
    if not isinstance(artifact_id, str):
        raise CliError("Artifact upload response omitted artifact_id")
    return None, artifact_id


def _run_segmentation(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    selected_outputs = tuple(
        output
        for output in (args.mask_output, args.foreground_output, args.background_output)
        if output is not None
    )
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
    print(f"Compute cost USD: {segmented.measured_compute_cost_usd}")


def _run_portrait_matting(
    args: argparse.Namespace, service: AuthService, api: ImageApiClient
) -> None:
    require_available_output(args.output)
    result = api.portrait_matting(
        service.access_token(frozenset({"images:edit"})),
        input_path=args.input,
        person_mask_path=args.person_mask,
        uncertainty_radius=args.uncertainty_radius,
    )
    args.output.write_bytes(result.data)
    print(f"Saved {result.width}x{result.height} RGBA PNG to {args.output}.")
    print(f"SHA-256: {result.sha256}")
    print(f"Model: {result.model_id}@{result.model_revision}")
    print(f"Compute cost USD: {result.measured_compute_cost_usd}")


def _run_composite(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    require_available_output(args.output)
    result = api.composite(
        service.access_token(frozenset({"images:edit"})),
        background_path=args.background,
        overlay_path=args.overlay,
        mask_path=args.mask,
        transform=tuple(args.matrix),
        opacity=args.opacity,
        composite=args.composite,
        crop=tuple(args.crop) if args.crop is not None else None,
    )
    save_deterministic_edit(result, args.output)
    _print_deterministic_result(result, args.output)


def _run_deterministic_program(
    args: argparse.Namespace, service: AuthService, api: ImageApiClient
) -> None:
    program, inputs, masks = api.load_deterministic_program(
        args.program, input_bindings=args.input, mask_bindings=args.mask
    )
    if args.dry_run:
        print(json.dumps(program, sort_keys=True, separators=(",", ":")))
        return
    if args.output is None:
        raise CliError("--output is required unless --dry-run is used")
    require_available_output(args.output)
    result = api.run_deterministic_program(
        service.access_token(frozenset({"images:edit"})),
        program=program,
        input_paths=inputs,
        mask_paths=masks,
    )
    save_deterministic_edit(result, args.output)
    _print_deterministic_result(result, args.output)
    for command_id, operation, normalized_sha, pixel_sha in result.command_receipts:
        print(f"Command {command_id} ({operation}): normalized={normalized_sha} pixels={pixel_sha}")


def _print_deterministic_result(result: object, output: Path) -> None:
    from .models import DeterministicEditResult

    assert isinstance(result, DeterministicEditResult)
    format_name = {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WebP",
    }.get(result.mime_type, result.mime_type)
    print(f"Saved {result.width}x{result.height} {format_name} to {output}.")
    print(f"SHA-256: {result.sha256}")
    print(f"Program SHA-256: {result.program_sha256}")
    print(f"Compute cost USD: {result.actual_cost_usd}")


def _run_reproducibility_check(
    args: argparse.Namespace, service: AuthService, api: ImageApiClient
) -> None:
    program, inputs, masks = api.load_deterministic_program(
        args.program, input_bindings=args.input, mask_bindings=args.mask
    )
    token = service.access_token(frozenset({"images:edit"}))
    results = tuple(
        api.run_deterministic_program(token, program=program, input_paths=inputs, mask_paths=masks)
        for _ in range(2)
    )
    first, second = results
    first_evidence = (
        first.data,
        first.sha256,
        first.program_sha256,
        first.width,
        first.height,
        first.command_receipts,
    )
    second_evidence = (
        second.data,
        second.sha256,
        second.program_sha256,
        second.width,
        second.height,
        second.command_receipts,
    )
    if first_evidence != second_evidence:
        raise CliError("deterministic reproducibility verification failed")
    print("Reproducibility: verified across 2 executions")
    print(f"SHA-256: {first.sha256}")
    print(f"Program SHA-256: {first.program_sha256}")
    for command_id, operation, normalized_sha, pixel_sha in first.command_receipts:
        print(f"Command {command_id} ({operation}): normalized={normalized_sha} pixels={pixel_sha}")


def _run_inpaint(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    require_available_output(args.output)
    image = api.inpaint(
        service.access_token(frozenset({"images:edit"})),
        prompt=args.prompt,
        input_path=args.input,
        mask_path=args.mask,
        profile=args.profile,
        seed=args.seed,
        safety_filter=args.safety_filter,
    )
    save_image(image, args.output)
    print(f"Saved {image.width}x{image.height} PNG to {args.output}.")
    print(f"SHA-256: {image.sha256}")
    print(f"Seed: {image.seed}")
    print(f"Model: {image.model_id}@{image.model_revision}")
    print(f"Compute cost USD: {image.measured_compute_cost_usd}")
    print(
        "Safety filter: "
        f"requested={image.safety_filter_requested} "
        f"effective={image.safety_filter_effective} "
        f"outcome={image.safety_filter_outcome}"
    )


def _run_replacement(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    background = args.command == "replace-background"
    _validate_replacement_controls(args)
    if background and len(args.mask) != 1:
        raise CliError("replace-background currently requires exactly one foreground mask")
    if args.padding is not None and (args.dilate is not None or args.erode is not None):
        raise CliError("--padding cannot be combined with --dilate or --erode")
    transforms: list[dict[str, object]] = []
    if args.threshold is not None:
        transforms.append({"op": "threshold", "cutoff": str(args.threshold)})
    radius = args.padding if args.padding is not None else args.dilate
    if radius is not None:
        transforms.append({"op": "dilate", "radius": radius, "shape": "disk"})
    if args.erode is not None:
        transforms.append({"op": "erode", "radius": args.erode, "shape": "disk"})
    if background or args.invert:
        transforms.append({"op": "invert"})
    if args.feather is not None:
        transforms.append({"op": "feather", "radius": str(args.feather), "border": "transparent"})
    coverage = _replacement_coverage(args.mask, args.combine, transforms)
    program = {
        "revision": "deterministic-edit-v1",
        "inputs": {
            "base": "image",
            "replacement": "image",
            **{f"mask{index}": "mask" for index in range(len(args.mask))},
        },
        "source_input": "base",
        "commands": [
            {
                "id": "replace-background" if background else "replace-object",
                "op": "paste_image",
                "input": "replacement",
                "composite": "replace",
                "coverage": coverage,
            }
        ],
        "encoding": {"format": "png"},
    }
    if args.dry_run:
        print(json.dumps(program, sort_keys=True, separators=(",", ":")))
        return
    if args.output is None:
        raise CliError("--output is required unless --dry-run is used")
    require_available_output(args.output)
    result = api.run_deterministic_program(
        service.access_token(frozenset({"images:edit"})),
        program=program,
        input_paths={"base": args.base, "replacement": args.replacement},
        mask_paths={f"mask{index}": path for index, path in enumerate(args.mask)},
    )
    save_deterministic_edit(result, args.output)
    _print_deterministic_result(result, args.output)


def _replacement_coverage(
    masks: Sequence[Path], combine: str, transforms: list[dict[str, object]]
) -> dict[str, object]:
    def layer(index: int) -> dict[str, object]:
        return {
            "source": {"kind": "mask_input", "input": f"mask{index}"},
            "transforms": transforms,
        }

    return {
        "base": layer(0),
        "combine": [{"mode": combine, "layer": layer(index)} for index in range(1, len(masks))],
    }


def _validate_replacement_controls(args: argparse.Namespace) -> None:
    if args.command == "replace-background" and args.invert:
        raise CliError("replace-background already inverts its foreground mask")
    if args.threshold is not None and not Decimal(0) <= args.threshold <= Decimal(1):
        raise CliError("--threshold must be from 0 through 1")
    for name in ("dilate", "erode", "padding"):
        value = getattr(args, name)
        if value is not None and not 1 <= value <= 64:
            raise CliError(f"--{name} must be from 1 through 64")
    if args.feather is not None and not Decimal(0) < args.feather <= Decimal(64):
        raise CliError("--feather must be greater than 0 and at most 64")


def _run_raster(args: argparse.Namespace, service: AuthService, api: ImageApiClient) -> None:
    commands = _raster_commands(args)
    input_paths, mask_paths = _raster_input_paths(args)
    program = {
        "revision": "deterministic-edit-v1",
        "inputs": {
            **{name: "image" for name in input_paths},
            **{name: "mask" for name in mask_paths},
        },
        "source_input": "source",
        "commands": commands,
        "encoding": {"format": "png"},
    }
    if args.dry_run:
        print(json.dumps(program, sort_keys=True, separators=(",", ":")))
        return
    if args.output is None:
        raise CliError("--output is required unless --dry-run is used")
    require_available_output(args.output)
    result = api.run_deterministic_program(
        service.access_token(frozenset({"images:edit"})),
        program=program,
        input_paths=input_paths,
        mask_paths=mask_paths,
    )
    save_deterministic_edit(result, args.output)
    _print_deterministic_result(result, args.output)


def _raster_commands(args: argparse.Namespace) -> list[dict[str, object]]:
    if args.raster_command == "grayscale":
        return [
            {
                "id": "grayscale",
                "op": "grayscale",
                "luminance": "rec709_linear_srgb_v1",
            }
        ]
    if args.raster_command == "crop":
        x, y, width, height = args.rect
        if width <= 0 or height <= 0:
            raise CliError("crop width and height must be positive")
        return [
            {
                "id": "crop",
                "op": "crop",
                "rect": {"x": x, "y": y, "width": width, "height": height},
            }
        ]
    if args.raster_command == "filter":
        if not Decimal(0) < args.radius <= Decimal(64):
            raise CliError("filter radius must be greater than 0 and at most 64")
        if not Decimal(0) <= args.amount <= Decimal(16):
            raise CliError("filter amount must be from 0 through 16")
        return [
            {
                "id": "filter",
                "op": "filter",
                "filter": args.kind,
                "radius": str(args.radius),
                "amount": str(args.amount),
            }
        ]
    if args.raster_command == "auto-crop":
        _validate_optional_decimal(args.threshold, "threshold", Decimal(0), Decimal(1))
        if not 0 <= args.padding <= 8_192:
            raise CliError("padding must be from 0 through 8192")
        return [
            {
                "id": "auto-crop",
                "op": "auto_crop",
                "coverage": {"base": {"source": {"kind": "mask_input", "input": "selection"}}},
                "threshold": str(args.threshold),
                "padding": args.padding,
            }
        ]
    if args.raster_command == "shape":
        if args.fill is None and args.stroke is None:
            raise CliError("shape requires --fill or --stroke")
        if not 1 <= args.stroke_width <= 1_024:
            raise CliError("stroke-width must be from 1 through 1024")
        x, y, width, height = args.rect
        return [
            {
                "id": "draw-shape",
                "op": "draw_shape",
                "shape": args.kind,
                "rect": {"x": x, "y": y, "width": width, "height": height},
                "fill": args.fill,
                "stroke": args.stroke,
                "stroke_width": args.stroke_width,
            }
        ]
    if args.raster_command == "text":
        if not args.text or len(args.text) > 4_096:
            raise CliError("text must contain 1 to 4096 characters")
        if not re.fullmatch(r"[0-9a-f]{64}", args.font_sha256):
            raise CliError("font-sha256 must contain 64 lowercase hexadecimal characters")
        if not 1 <= args.font_size <= 2_048 or not 0 <= args.stroke_width <= 128:
            raise CliError("font-size or stroke-width is outside the supported bounds")
        x, y = args.position
        return [
            {
                "id": "draw-text",
                "op": "draw_text",
                "text": args.text,
                "position": {"x": x, "y": y},
                "font": {"id": args.font_id, "sha256": args.font_sha256},
                "font_size_px": args.font_size,
                "fill": args.fill,
                "stroke": args.stroke,
                "stroke_width": args.stroke_width,
            }
        ]
    if args.raster_command == "color-match":
        _validate_optional_decimal(args.strength, "strength", Decimal(0), Decimal(1))
        return [
            {
                "id": "color-match",
                "op": "color_match",
                "reference_input": "reference",
                "algorithm": args.algorithm,
                "strength": str(args.strength),
                "preserve_luminance": args.preserve_luminance,
            }
        ]
    if args.raster_command in {"resize", "flip", "rotate", "canvas"}:
        return [_geometry_command(args)]
    if args.raster_command == "project-quad":
        coordinates = iter(args.destination)
        points = [{"x": x, "y": y} for x, y in zip(coordinates, coordinates, strict=True)]
        return [
            {
                "id": "project-quad",
                "op": "project_quad",
                "texture_input": "texture",
                "destination": points,
                "composite": args.composite,
            }
        ]
    if args.raster_command == "mesh":
        spec = _read_json_object(args.mesh_spec, "mesh spec")
        forbidden = {"id", "op", "texture_input"} & set(spec)
        if forbidden:
            raise CliError("mesh spec must not override id, op, or texture_input")
        return [{"id": "render-mesh", "op": "render_mesh", "texture_input": "texture", **spec}]
    return _adjustment_commands(args)


def _geometry_command(args: argparse.Namespace) -> dict[str, object]:
    source_width, source_height = _image_dimensions(args.input)
    width, height = source_width, source_height
    matrix = (Decimal(1), Decimal(0), Decimal(0), Decimal(1), Decimal(0), Decimal(0))
    background = {"r": 0, "g": 0, "b": 0, "a": 0}
    if args.raster_command == "resize":
        _validate_canvas(args.width, args.height)
        width, height = args.width, args.height
        if args.fit:
            scale = min(Decimal(width) / source_width, Decimal(height) / source_height)
            x = (Decimal(width) - Decimal(source_width) * scale) / 2
            y = (Decimal(height) - Decimal(source_height) * scale) / 2
            matrix = (scale, Decimal(0), Decimal(0), scale, x, y)
        else:
            matrix = (
                Decimal(width) / source_width,
                Decimal(0),
                Decimal(0),
                Decimal(height) / source_height,
                Decimal(0),
                Decimal(0),
            )
    elif args.raster_command == "flip":
        matrix = (
            (Decimal(-1), Decimal(0), Decimal(0), Decimal(1), Decimal(width), Decimal(0))
            if args.axis == "horizontal"
            else (Decimal(1), Decimal(0), Decimal(0), Decimal(-1), Decimal(0), Decimal(height))
        )
    elif args.raster_command == "rotate":
        matrix, width, height = _rotation_geometry(args.degrees, source_width, source_height)
    else:
        _validate_canvas(args.width, args.height)
        width, height = args.width, args.height
        matrix = (Decimal(1), Decimal(0), Decimal(0), Decimal(1), Decimal(args.x), Decimal(args.y))
        background = args.background
    return {
        "id": args.raster_command,
        "op": "affine",
        "transform": dict(zip(("a", "b", "c", "d", "e", "f"), map(str, matrix), strict=True)),
        "output_width": width,
        "output_height": height,
        "interpolation": "lanczos" if args.raster_command == "resize" else "bicubic",
        "border": "constant",
        "background": background,
    }


def _rotation_geometry(
    degrees: int, width: int, height: int
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal], int, int]:
    if degrees == 90:
        return (
            (Decimal(0), Decimal(1), Decimal(-1), Decimal(0), Decimal(height), Decimal(0)),
            height,
            width,
        )
    if degrees == 180:
        return (
            (Decimal(-1), Decimal(0), Decimal(0), Decimal(-1), Decimal(width), Decimal(height)),
            width,
            height,
        )
    return (
        (Decimal(0), Decimal(-1), Decimal(1), Decimal(0), Decimal(0), Decimal(width)),
        height,
        width,
    )


def _image_dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except (OSError, UnidentifiedImageError) as error:
        raise CliError(f"input image is not readable: {path}") from error


def _validate_canvas(width: int, height: int) -> None:
    if not 1 <= width <= 8_192 or not 1 <= height <= 8_192:
        raise CliError("canvas width and height must be from 1 through 8192")
    if width * height > 4_194_304:
        raise CliError("canvas exceeds the 4194304 pixel limit")


def _raster_input_paths(args: argparse.Namespace) -> tuple[dict[str, Path], dict[str, Path]]:
    inputs = {"source": args.input}
    masks: dict[str, Path] = {}
    if args.raster_command == "auto-crop":
        masks["selection"] = args.mask
    if args.raster_command == "color-match":
        inputs["reference"] = args.reference
    if args.raster_command in {"project-quad", "mesh"}:
        inputs["texture"] = args.texture
    return inputs, masks


def _adjustment_commands(args: argparse.Namespace) -> list[dict[str, object]]:
    _validate_optional_decimal(args.hue, "hue", Decimal(-180), Decimal(180))
    _validate_optional_decimal(args.saturation, "saturation", Decimal(0), Decimal(4))
    _validate_optional_decimal(args.tint, "tint", Decimal(-1), Decimal(1))
    _validate_optional_decimal(args.exposure, "exposure", Decimal(-10), Decimal(10))
    _validate_optional_decimal(args.brightness, "brightness", Decimal(-1), Decimal(1))
    _validate_optional_decimal(args.contrast, "contrast", Decimal(0), Decimal(4))
    if args.temperature is not None and not 1_000 <= args.temperature <= 40_000:
        raise CliError("temperature must be from 1000 through 40000")
    commands: list[dict[str, object]] = []
    if args.hue is not None or args.saturation is not None:
        commands.append(
            {
                "id": "hue-saturation",
                "op": "hue_saturation",
                "hue_degrees": str(args.hue if args.hue is not None else 0),
                "saturation_scale": str(args.saturation if args.saturation is not None else 1),
            }
        )
    if args.temperature is not None:
        commands.append(
            {
                "id": "white-balance",
                "op": "white_balance",
                "temperature_kelvin": args.temperature,
                "tint": str(args.tint),
            }
        )
    if any(value is not None for value in (args.exposure, args.brightness, args.contrast)):
        commands.append(
            {
                "id": "tone",
                "op": "tone",
                "exposure_stops": str(args.exposure if args.exposure is not None else 0),
                "brightness": str(args.brightness if args.brightness is not None else 0),
                "contrast": str(args.contrast if args.contrast is not None else 1),
            }
        )
    if not commands:
        raise CliError("raster adjust requires at least one adjustment")
    return commands


def _validate_optional_decimal(
    value: Decimal | None, name: str, minimum: Decimal, maximum: Decimal
) -> None:
    if value is not None and (not value.is_finite() or not minimum <= value <= maximum):
        raise CliError(f"{name} must be from {minimum} through {maximum}")


def _read_json_object(path: Path, name: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliError(f"{name} must be a readable UTF-8 JSON file") from error
    if not isinstance(value, dict):
        raise CliError(f"{name} must contain one JSON object")
    return value


def _run_artifact_command(
    args: argparse.Namespace, service: AuthService, api: ImageApiClient
) -> None:
    required_scopes = (
        frozenset({"batches:execute", "artifacts:read"})
        if args.command in {"upload", "delete"}
        else frozenset({"artifacts:read"})
    )
    token = service.access_token(required_scopes)
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
    elif args.command == "download":
        result = api.download_artifact(token, args.artifact_id, args.output)
        artifact = result.get("result", {}).get("artifact", {})
        print(f"Saved Artifact {args.artifact_id} to {args.output}.")
        if isinstance(artifact, dict) and isinstance(artifact.get("sha256"), str):
            print(f"SHA-256: {artifact['sha256']}")
    elif args.command == "delete":
        if not args.force:
            confirmation = input(f"Type Artifact ID {args.artifact_id} to confirm tombstoning: ")
            if confirmation != args.artifact_id:
                raise CliError("Artifact deletion confirmation did not match")
        result = api.delete_artifact(token, args.artifact_id)
        _emit(result, args.json)
    else:
        result = api.upload_artifact(token, args.input, namespace=args.namespace, kind=args.kind)
        _emit(result, args.json)


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
    elif args.command == "iterate":
        token = service.access_token(
            frozenset({"batches:plan", "batches:execute", "campaigns:write", "campaigns:read"})
        )
        result = api.create_iterative_campaign(
            token,
            plan_id=args.plan_id,
            max_cost_usd=args.max_cost,
            score_threshold=args.threshold,
            max_rounds=args.max_rounds,
            allow_partial=args.allow_partial,
            wait_seconds=args.wait,
            allow_long_wait=args.allow_long_wait,
        )
    elif args.command == "evaluate":
        token = service.access_token(frozenset({"campaigns:read"}))
        result = api.campaign_evaluation(token, args.campaign_id)
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
