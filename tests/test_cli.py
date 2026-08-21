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
        ["prompt", "optimize", "blue cup", "--width", "512", "--height", "768"]
    )

    assert arguments.group == "prompt"
    assert arguments.command == "optimize"
    assert arguments.prompt == "blue cup"
    assert arguments.width == 512
    assert arguments.height == 768
