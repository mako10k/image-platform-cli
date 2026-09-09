"""Command composition for V4 image editing."""

from __future__ import annotations

import argparse
import secrets
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..common.errors import CliError
from ..common.files import read_image, save_bytes_exclusive
from ..common.service import AuthService
from .api import V4ApiClient
from .crop import crop_program
from .filtering import filter_program
from .grayscale import grayscale_program
from .image_edits import ImageToImageOptions
from .segment_cli import add_segment_command, coordinates, run_segment
from .shapes import ShapeOptions
from .text_drawing import TextOptions


def add_edit_commands(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    commands = groups.add_parser("edit").add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert")
    convert.add_argument("--input", type=Path, required=True)
    convert.add_argument("--output", "-o", type=Path, required=True)
    convert.add_argument("--format", choices=("png", "jpeg", "webp"), required=True)
    convert.add_argument("--quality", type=int, default=90)
    raster = commands.add_parser("raster").add_subparsers(dest="raster_command", required=True)
    crop = raster.add_parser("crop")
    crop.add_argument("--rect", type=coordinates(4), required=True)
    grayscale = raster.add_parser("grayscale")
    filtering = raster.add_parser("filter")
    filtering.add_argument(
        "--kind", choices=("gaussian_blur", "box_blur", "unsharp_mask"), required=True
    )
    filtering.add_argument("--radius", type=Decimal, required=True)
    filtering.add_argument("--amount", type=Decimal, default=Decimal(1))
    shape = raster.add_parser("shape")
    shape.add_argument("--kind", choices=("rectangle", "ellipse"), required=True)
    shape.add_argument("--rect", type=coordinates(4), required=True)
    shape.add_argument("--fill", type=coordinates(4))
    shape.add_argument("--stroke", type=coordinates(4))
    shape.add_argument("--stroke-width", type=int, default=1)
    text = raster.add_parser("text")
    text.add_argument("text")
    text.add_argument("--position", type=coordinates(2), required=True)
    text.add_argument("--font-id", required=True)
    text.add_argument("--font-sha256", required=True)
    text.add_argument("--font-size", type=int, required=True)
    text.add_argument("--fill", type=coordinates(4), required=True)
    text.add_argument("--stroke", type=coordinates(4))
    text.add_argument("--stroke-width", type=int, default=0)
    for operation in (crop, grayscale, filtering, shape, text):
        operation.add_argument("--input", type=Path, required=True)
        operation.add_argument("--output", "-o", type=Path)
        operation.add_argument("--dry-run", action="store_true")
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
    if args.command == "raster":
        token = service.access_token(frozenset({"images:edit"}))
        if args.raster_command == "text":
            raster_result = api.draw_text(token, input_path=args.input, options=text_options(args))
        elif args.raster_command == "shape":
            raster_result = api.draw_shape(
                token, input_path=args.input, options=shape_options(args)
            )
        elif args.raster_command == "filter":
            raster_result = api.filter_image(
                token, input_path=args.input, kind=args.kind, radius=args.radius, amount=args.amount
            )
        elif args.raster_command == "grayscale":
            raster_result = api.grayscale_image(token, input_path=args.input)
        else:
            raster_result = api.crop_image(token, input_path=args.input, rect=args.rect)
        save_bytes_exclusive(raster_result.data, args.output)
        print(f"Saved {raster_result.width}x{raster_result.height} image to {args.output}.")
        return
    if args.command == "convert":
        converted = api.convert_image(
            service.access_token(frozenset({"images:edit"})),
            input_path=args.input,
            format_name=args.format,
            quality=args.quality,
        )
        save_bytes_exclusive(converted.data, args.output)
        print(f"Saved {converted.width}x{converted.height} converted image to {args.output}.")
        return
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


def raster_program(args: argparse.Namespace) -> dict[str, Any]:
    if args.raster_command == "text":
        return text_options(args).program()
    if args.raster_command == "shape":
        return shape_options(args).program()
    if args.raster_command == "filter":
        return filter_program(args.kind, args.radius, args.amount)
    if args.raster_command == "grayscale":
        return grayscale_program()
    return crop_program(args.rect)


def shape_options(args: argparse.Namespace) -> ShapeOptions:
    return ShapeOptions(args.kind, args.rect, args.fill, args.stroke, args.stroke_width)


def text_options(args: argparse.Namespace) -> TextOptions:
    return TextOptions(
        args.text,
        args.position,
        args.font_id,
        args.font_sha256,
        args.font_size,
        args.fill,
        args.stroke,
        args.stroke_width,
    )
