"""Local program loading, execution and repeatability verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..common.errors import CliError
from ..common.files import require_available_output, save_bytes_exclusive
from ..common.programs import load_deterministic_program
from ..common.replacements import replacement_program
from ..common.service import AuthService
from .api import V4ApiClient
from .program_schema import normalize_program


def add_program_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for name in ("run", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--program", type=Path, required=True)
        command.add_argument("--input", action="append", default=[])
        command.add_argument("--mask", action="append", default=[])
        if name == "run":
            command.add_argument("--output", "-o", type=Path)
            command.add_argument("--dry-run", action="store_true")


def prepare_cli_program(args: argparse.Namespace) -> bool:
    if args.command in {"replace-object", "replace-background"}:
        program = replacement_program(args)
        inputs = {"base": args.base, "replacement": args.replacement}
        masks = {f"mask{index}": path for index, path in enumerate(args.mask)}
    else:
        program, inputs, masks = load_deterministic_program(
            args.program, input_bindings=args.input, mask_bindings=args.mask
        )
    args.prepared_program = normalize_program(program)
    args.prepared_paths = {**inputs, **masks}
    if args.command != "verify":
        if args.dry_run:
            print(json.dumps(args.prepared_program, sort_keys=True))
            return True
        if args.output is None:
            raise CliError("--output is required unless --dry-run is used")
        require_available_output(args.output)
    return False


def run_cli_program(args: argparse.Namespace, service: AuthService, api: V4ApiClient) -> None:
    token = service.access_token(frozenset({"images:edit"}))
    first = api.run_program(token, program=args.prepared_program, paths=args.prepared_paths)
    if args.command != "verify":
        save_bytes_exclusive(first.data, args.output)
        print(f"Saved {first.width}x{first.height} image to {args.output}.")
    else:
        second = api.run_program(token, program=args.prepared_program, paths=args.prepared_paths)

        def evidence(result: Any) -> tuple[Any, ...]:
            return (
                result.data,
                result.sha256,
                result.program_sha256,
                result.width,
                result.height,
                result.command_receipts,
            )

        if evidence(first) != evidence(second):
            raise CliError("deterministic reproducibility verification failed")
        print("Reproducibility: verified across 2 executions")
    print(f"Program SHA-256: {first.program_sha256}")
    for command_id, operation, command_hash, pixel_hash in first.command_receipts:
        print(f"Command {command_id} ({operation}): normalized={command_hash} pixels={pixel_hash}")
