import argparse
from pathlib import Path


def add_generation_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("prompt")
    command.add_argument("--output", "-o", type=Path, required=True)
    command.add_argument("--width", type=int, default=1024)
    command.add_argument("--height", type=int, default=1024)
    command.add_argument("--seed", type=int)
    command.add_argument("--optimize", action="store_true")
    command.add_argument("--wait", type=int, default=30)
    command.add_argument("--allow-long-wait", action="store_true")


def add_batch_plan_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("intent")
    command.add_argument("--width", type=int, default=1024)
    command.add_argument("--height", type=int, default=1024)
    command.add_argument("--count", type=int, default=1)
    command.add_argument("--seed", type=int)
    command.add_argument("--no-optimize", action="store_true")
    command.add_argument("--json", action="store_true")
