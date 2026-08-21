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
    assert "--no-polling" not in parser().format_help()
