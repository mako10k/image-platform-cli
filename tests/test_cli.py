from pathlib import Path

from image_platform_cli.cli import parser


def test_generate_exposes_safe_bounded_wait_controls_without_no_polling() -> None:
    arguments = parser().parse_args(
        [
            "generate",
            "blue cup",
            "--output",
            "result.png",
            "--wait",
            "90",
            "--allow-long-wait",
        ]
    )

    assert arguments.wait == 90
    assert arguments.allow_long_wait is True
    assert arguments.seed is None
    assert "--no-polling" not in parser().format_help()


def test_explicit_seed_is_preserved_by_parser() -> None:
    arguments = parser().parse_args(
        ["generate", "blue cup", "--output", "result.png", "--seed", "42"]
    )

    assert arguments.seed == 42


def test_prompt_optimize_is_a_native_prompt_plan_command() -> None:
    arguments = parser().parse_args(
        [
            "prompt",
            "optimize",
            "blue cup",
            "--width",
            "512",
            "--height",
            "768",
            "--seed",
            "42",
        ]
    )

    assert arguments.group == "prompt"
    assert arguments.command == "optimize"
    assert arguments.prompt == "blue cup"
    assert arguments.width == 512
    assert arguments.height == 768
    assert arguments.seed == 42


def test_durable_resource_command_surface_is_bounded() -> None:
    jobs = parser().parse_args(
        [
            "job",
            "list",
            "--status",
            "completed",
            "--page-size",
            "50",
            "--all",
            "--max-items",
            "200",
            "--json",
        ]
    )
    artifact = parser().parse_args(
        ["artifact", "download", "art_1", "--output", "result.png"]
    )
    search = parser().parse_args(
        ["search", "blue cup", "--mime-type", "image/png", "--limit", "5"]
    )

    assert jobs.group == "job" and jobs.command == "list"
    assert jobs.all_pages is True and jobs.max_items == 200
    assert artifact.output == Path("result.png")
    assert search.mime_type == ["image/png"] and search.limit == 5
