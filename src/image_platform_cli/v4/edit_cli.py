"""Command composition for V4 image editing."""

from __future__ import annotations

import argparse
import secrets
from decimal import Decimal
from pathlib import Path

from ..common.errors import CliError
from ..common.files import read_image, save_bytes_exclusive
from ..common.service import AuthService
from .api import V4ApiClient
from .image_edits import ImageToImageOptions
from .segment_cli import add_segment_command, run_segment


def add_edit_commands(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    commands = groups.add_parser("edit").add_subparsers(dest="command", required=True)
    add_segment_command(commands)
    matte = commands.add_parser("matte-portrait")
    matte.add_argument("--input", type=Path, required=True)
    matte.add_argument("--person-mask", type=Path, required=True)
    matte.add_argument("--uncertainty-radius", type=int, default=16)
    matte.add_argument("--output", "-o", type=Path, required=True)
    inpaint = commands.add_parser("inpaint")
    for name in ("input", "mask", "output"):
        inpaint.add_argument(f"--{name}", type=Path, required=True)
    inpaint.add_argument("prompt")
    inpaint.add_argument("--seed", type=int)
    inpaint.add_argument("--profile", default="inpaint-stable-diffusion-v1-5")
    inpaint.add_argument(
        "--safety-filter", choices=("default", "enabled", "disabled"), default="default"
    )
    command = commands.add_parser("image-to-image", aliases=["i2i"])
    command.add_argument("prompt")
    source = command.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--artifact")
    command.add_argument("--output", "-o", type=Path, required=True)
    command.add_argument("--capture-input", action="store_true")
    command.add_argument("--capture-namespace", default="default")
    command.add_argument("--profile", default="i2i-stable-diffusion-v1-5")
    command.add_argument("--negative-prompt")
    command.add_argument("--strength", type=Decimal, default=Decimal("0.75"))
    command.add_argument("--guidance-scale", type=Decimal, default=Decimal("7.5"))
    command.add_argument("--steps", type=int, default=25)
    command.add_argument("--seed", type=int)
    command.add_argument("--width", type=int)
    command.add_argument("--height", type=int)


def run_edit(args: argparse.Namespace, service: AuthService, api: V4ApiClient) -> None:
    if args.command == "matte-portrait":
        matte = api.portrait_matting(
            service.access_token(frozenset({"images:edit"})),
            input_path=args.input,
            person_mask_path=args.person_mask,
            uncertainty_radius=args.uncertainty_radius,
        )
        save_bytes_exclusive(matte.data, args.output)
        print(f"Saved {matte.width}x{matte.height} portrait matte to {args.output}.")
        return
    if args.command == "segment":
        run_segment(args, service, api)
        return
    if args.command == "inpaint":
        result = api.inpaint(
            service.access_token(frozenset({"images:edit"})),
            input_path=args.input,
            mask_path=args.mask,
            prompt=args.prompt,
            seed=args.seed if args.seed is not None else secrets.randbits(63),
            profile=args.profile,
            safety_filter=args.safety_filter,
        )
        save_bytes_exclusive(result.data, args.output)
        print(f"Saved {result.width}x{result.height} image to {args.output}.")
        return
    if args.capture_input and args.input is None:
        raise CliError("--capture-input requires a local input image")
    options = ImageToImageOptions(
        prompt=args.prompt,
        seed=args.seed if args.seed is not None else secrets.randbits(63),
        profile=args.profile,
        negative_prompt=args.negative_prompt,
        strength=args.strength,
        guidance_scale=args.guidance_scale,
        inference_steps=args.steps,
        width=args.width,
        height=args.height,
    )
    scopes = {"images:edit"}
    if args.artifact or args.capture_input:
        scopes.add("artifacts:read")
    if args.capture_input:
        scopes.add("artifacts:write")
        _, _, width, height = read_image(args.input)
        options.payload({"width": width, "height": height})
    token = service.access_token(frozenset(scopes))
    input_path, artifact_id = args.input, args.artifact
    if args.capture_input:
        artifact_id = api.upload_artifact(
            token, input_path, namespace=args.capture_namespace, kind="image"
        )["artifact_id"]
        input_path = None
    result = api.image_to_image(
        token, options=options, input_path=input_path, artifact_id=artifact_id
    )
    save_bytes_exclusive(result.data, args.output)
    print(f"Saved {result.width}x{result.height} image to {args.output}.")
