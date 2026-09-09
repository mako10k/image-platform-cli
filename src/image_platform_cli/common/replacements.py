"""Shared object/background replacement program construction."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from .errors import CliError


def add_replacement_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for name in ("replace-object", "replace-background"):
        replacement = commands.add_parser(name)
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


def replacement_program(args: argparse.Namespace) -> dict[str, object]:
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
    program: dict[str, object] = {
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
    return program


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
    if args.threshold is not None and (
        not args.threshold.is_finite() or not Decimal(0) <= args.threshold <= Decimal(1)
    ):
        raise CliError("--threshold must be from 0 through 1")
    for name in ("dilate", "erode", "padding"):
        value = getattr(args, name)
        if value is not None and not 1 <= value <= 64:
            raise CliError(f"--{name} must be from 1 through 64")
    if args.feather is not None and (
        not args.feather.is_finite() or not Decimal(0) < args.feather <= Decimal(64)
    ):
        raise CliError("--feather must be greater than 0 and at most 64")
