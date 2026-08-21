from decimal import Decimal
from pathlib import Path

from image_platform_cli.cli import DEFAULT_LOGIN_SCOPES, parser


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
    artifact = parser().parse_args(["artifact", "download", "art_1", "--output", "result.png"])
    search = parser().parse_args(["search", "blue cup", "--mime-type", "image/png", "--limit", "5"])

    assert jobs.group == "job" and jobs.command == "list"
    assert jobs.all_pages is True and jobs.max_items == 200
    assert artifact.output == Path("result.png")
    assert search.mime_type == ["image/png"] and search.limit == 5


def test_batch_workflow_surface_is_server_owned_and_bounded() -> None:
    plan = parser().parse_args(
        ["batch", "plan", "blue cup", "--count", "4", "--seed", "42", "--json"]
    )
    run = parser().parse_args(
        [
            "batch",
            "run",
            "bplan_1",
            "--max-cost",
            "0.16",
            "--wait",
            "90",
            "--allow-long-wait",
            "--json",
        ]
    )
    results = parser().parse_args(["batch", "results", "campaign_1", "--json"])

    assert plan.intent == "blue cup" and plan.count == 4 and plan.seed == 42
    assert run.max_cost == Decimal("0.16") and run.wait == 90
    assert run.allow_long_wait is True
    assert results.campaign_id == "campaign_1"


def test_default_login_scopes_cover_batch_workflow() -> None:
    assert {
        "batches:plan",
        "batches:execute",
        "campaigns:write",
        "campaigns:read",
        "jobs:cancel",
    } <= set(DEFAULT_LOGIN_SCOPES)


def test_capabilities_surface_and_default_editing_scopes() -> None:
    arguments = parser().parse_args(["capabilities", "--json"])

    assert arguments.group == "capabilities"
    assert arguments.json is True
    assert {"images:edit", "images:understand"} <= set(DEFAULT_LOGIN_SCOPES)


def test_image_to_image_surface_exposes_bounded_native_controls() -> None:
    arguments = parser().parse_args(
        [
            "edit",
            "image-to-image",
            "paint this as watercolor",
            "--input",
            "rough.png",
            "--output",
            "finished.png",
            "--negative-prompt",
            "text",
            "--strength",
            "0.6",
            "--guidance-scale",
            "8",
            "--steps",
            "30",
            "--seed",
            "42",
            "--width",
            "512",
            "--height",
            "640",
        ]
    )

    assert arguments.group == "edit" and arguments.command == "image-to-image"
    assert arguments.input == Path("rough.png")
    assert arguments.output == Path("finished.png")
    assert arguments.strength == Decimal("0.6")
    assert arguments.guidance_scale == Decimal(8)
    assert arguments.steps == 30 and arguments.seed == 42
    assert arguments.width == 512 and arguments.height == 640


def test_segment_surface_supports_text_point_box_and_explicit_outputs() -> None:
    text = parser().parse_args(
        [
            "edit",
            "segment",
            "--input",
            "scene.png",
            "--text",
            "girl",
            "--mask-output",
            "mask.png",
        ]
    )
    points = parser().parse_args(
        [
            "edit",
            "segment",
            "--input",
            "scene.png",
            "--point",
            "10,20",
            "--negative-point",
            "30,40",
            "--foreground-output",
            "foreground.png",
        ]
    )
    box = parser().parse_args(
        [
            "edit",
            "segment",
            "--input",
            "scene.png",
            "--box",
            "1,2,100,200",
            "--background-output",
            "background.png",
        ]
    )

    assert text.text == "girl" and text.mask_output == Path("mask.png")
    assert points.point == [(10, 20)] and points.negative_point == [(30, 40)]
    assert points.foreground_output == Path("foreground.png")
    assert box.box == (1, 2, 100, 200)
    assert box.background_output == Path("background.png")


def test_composite_surface_exposes_crop_affine_alpha_and_mask() -> None:
    arguments = parser().parse_args(
        [
            "edit",
            "composite",
            "--background",
            "background.png",
            "--overlay",
            "foreground.png",
            "--mask",
            "mask.png",
            "--matrix",
            "1,0,0,1,20,30",
            "--opacity",
            "0.8",
            "--crop",
            "0,0,512,512",
            "--output",
            "composite.png",
        ]
    )

    assert arguments.group == "edit" and arguments.command == "composite"
    assert arguments.background == Path("background.png")
    assert arguments.overlay == Path("foreground.png")
    assert arguments.mask == Path("mask.png")
    assert arguments.matrix == tuple(Decimal(value) for value in (1, 0, 0, 1, 20, 30))
    assert arguments.opacity == Decimal("0.8")
    assert arguments.crop == (0, 0, 512, 512)
    assert arguments.output == Path("composite.png")


def test_inpaint_surface_requires_explicit_mask_and_exposes_seed_profile() -> None:
    arguments = parser().parse_args(
        [
            "edit",
            "inpaint",
            "remove the object",
            "--input",
            "scene.png",
            "--mask",
            "mask.png",
            "--output",
            "repaired.png",
            "--profile",
            "inpaint-stable-diffusion-v1-5",
            "--seed",
            "42",
        ]
    )

    assert arguments.group == "edit" and arguments.command == "inpaint"
    assert arguments.prompt == "remove the object"
    assert arguments.input == Path("scene.png") and arguments.mask == Path("mask.png")
    assert arguments.output == Path("repaired.png")
    assert arguments.profile == "inpaint-stable-diffusion-v1-5"
    assert arguments.seed == 42
