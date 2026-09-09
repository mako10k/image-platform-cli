"""CLI input and output selection for image segmentation."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from ..common.errors import CliError
from ..common.files import require_available_output
from ..common.segmentation import save_segmentation_outputs
from ..common.service import AuthService
from .api import V4ApiClient
from .segmentation import SegmentSelector


def coordinates(size: int) -> Callable[[str], tuple[int, ...]]:
    def parse(value: str) -> tuple[int, ...]:
        try:
            result = tuple(int(part) for part in value.split(","))
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                "coordinates must be comma-separated integers"
            ) from error
        if len(result) != size:
            raise argparse.ArgumentTypeError(f"expected {size} coordinates")
        return result

    return parse


def add_segment_command(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    command = commands.add_parser("segment")
    command.add_argument("--input", type=Path, required=True)
    selectors = command.add_mutually_exclusive_group(required=True)
    for name, count in (("text", 0), ("box", 4), ("point", 2)):
        if count == 0:
            selectors.add_argument(f"--{name}")
        else:
            selectors.add_argument(
                f"--{name}",
                type=coordinates(count),
                action="append" if name == "point" else "store",
            )
    command.add_argument("--negative-point", type=coordinates(2), action="append")
    for name in ("mask", "foreground", "background"):
        command.add_argument(f"--{name}-output", type=Path)


def validate_segment_outputs(args: argparse.Namespace) -> None:
    targets = [
        p
        for p in (args.mask_output, args.foreground_output, args.background_output)
        if p is not None
    ]
    if not targets or len({p.resolve() for p in targets}) != len(targets):
        raise CliError("segmentation needs at least one output and distinct destination paths")
    for target in targets:
        require_available_output(target)
    if args.negative_point and not args.point:
        raise CliError("negative points require a positive point selector")


def run_segment(args: argparse.Namespace, service: AuthService, api: V4ApiClient) -> None:
    validate_segment_outputs(args)
    points = [(x, y, True) for x, y in args.point or []]
    points.extend((x, y, False) for x, y in args.negative_point or [])
    selector = SegmentSelector(text=args.text, points=points, box=args.box)
    result = api.segment(
        service.access_token(frozenset({"images:understand"})),
        input_path=args.input,
        selector=selector,
    )
    save_segmentation_outputs(
        result,
        mask_output=args.mask_output,
        foreground_output=args.foreground_output,
        background_output=args.background_output,
    )
    print(f"Saved {result.width}x{result.height} segmentation outputs.")
