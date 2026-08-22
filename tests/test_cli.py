from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from image_platform_cli.cli import (
    DEFAULT_LOGIN_SCOPES,
    _run_reproducibility_check,
    _show_help,
    main,
    parser,
)
from image_platform_cli.models import DeterministicEditResult


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


def test_help_navigation_shows_catalog_examples_and_related_topic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _show_help(("edit", "run")) == 0

    output = capsys.readouterr().out
    assert "GUIDANCE" in output
    assert "EXAMPLES" in output
    assert "image edit run --program edit.json" in output
    assert "RELATED\n  image help edit" in output


def test_help_navigation_rejects_unknown_child(capsys: pytest.CaptureFixture[str]) -> None:
    assert _show_help(("edit", "missing")) == 2

    assert "unknown help topic edit missing" in capsys.readouterr().err


def test_replace_object_dry_run_emits_mask_transform_recipe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(
        [
            "edit",
            "replace-object",
            "--base",
            "base.png",
            "--replacement",
            "new.png",
            "--mask",
            "one.png",
            "--mask",
            "two.png",
            "--threshold",
            "0.5",
            "--padding",
            "3",
            "--feather",
            "2",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert '"op":"threshold"' in output
    assert '"op":"dilate"' in output
    assert '"op":"feather"' in output
    assert '"mode":"union"' in output
    assert '"composite":"replace"' in output


def test_replace_background_dry_run_inverts_foreground_mask(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(
        [
            "edit",
            "replace-background",
            "--base",
            "base.png",
            "--replacement",
            "new.png",
            "--mask",
            "foreground.png",
            "--dry-run",
        ]
    )

    assert result == 0
    assert '"op":"invert"' in capsys.readouterr().out


def test_raster_adjust_dry_run_composes_stable_command_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(
        [
            "edit",
            "raster",
            "adjust",
            "--input",
            "scene.png",
            "--hue",
            "15",
            "--temperature",
            "6500",
            "--contrast",
            "1.1",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert output.index('"op":"hue_saturation"') < output.index('"op":"white_balance"')
    assert output.index('"op":"white_balance"') < output.index('"op":"tone"')


def test_raster_resize_fit_dry_run_resolves_exact_affine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (400, 200)).save(source)

    result = main(
        [
            "edit",
            "raster",
            "resize",
            "--input",
            str(source),
            "--width",
            "300",
            "--height",
            "300",
            "--fit",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert '"a":"0.75"' in output and '"d":"0.75"' in output
    assert '"f":"75.00"' in output
    assert '"output_width":300' in output and '"output_height":300' in output


def test_raster_rotate_dry_run_swaps_canvas_dimensions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (320, 180)).save(source)

    assert (
        main(
            [
                "edit",
                "raster",
                "rotate",
                "--input",
                str(source),
                "--degrees",
                "90",
                "--dry-run",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"output_width":180' in output and '"output_height":320' in output


def test_project_quad_dry_run_exposes_composite_and_destination(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "edit",
                "raster",
                "project-quad",
                "--input",
                "canvas.png",
                "--texture",
                "texture.png",
                "--destination",
                "0,0,100,0,100,80,0,80",
                "--composite",
                "screen",
                "--dry-run",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"op":"project_quad"' in output
    assert '"composite":"screen"' in output


def test_mesh_dry_run_wraps_saved_mesh_spec(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mesh = tmp_path / "mesh.json"
    mesh.write_text(
        '{"vertices":[{"x":"0","y":"0","u":"0","v":"0"},'
        '{"x":"10","y":"0","u":"1","v":"0"},'
        '{"x":"0","y":"10","u":"0","v":"1"}],'
        '"triangles":[{"a":0,"b":1,"c":2}]}',
        encoding="utf-8",
    )

    assert (
        main(
            [
                "edit",
                "raster",
                "mesh",
                "--input",
                "canvas.png",
                "--texture",
                "texture.png",
                "--mesh-spec",
                str(mesh),
                "--dry-run",
            ]
        )
        == 0
    )
    assert '"op":"render_mesh"' in capsys.readouterr().out


def test_reproducibility_check_compares_full_receipt_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = DeterministicEditResult(
        b"png",
        "image/png",
        "a" * 64,
        10,
        20,
        "b" * 64,
        (("crop", "crop", "c" * 64, "d" * 64),),
    )

    class FakeService:
        def access_token(self, scopes: frozenset[str]) -> str:
            assert scopes == frozenset({"images:edit"})
            return "token"

    class FakeApi:
        def load_deterministic_program(
            self, *args: object, **kwargs: object
        ) -> tuple[dict[str, object], dict[str, Path], dict[str, Path]]:
            return {"revision": "deterministic-edit-v1"}, {}, {}

        def run_deterministic_program(
            self, *args: object, **kwargs: object
        ) -> DeterministicEditResult:
            return result

    _run_reproducibility_check(
        SimpleNamespace(program=Path("edit.json"), input=[], mask=[]),
        FakeService(),  # type: ignore[arg-type]
        FakeApi(),  # type: ignore[arg-type]
    )

    output = capsys.readouterr().out
    assert "verified across 2 executions" in output
    assert f"normalized={'c' * 64}" in output


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


def test_image_to_image_help_explains_descriptive_prompt_semantics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser().parse_args(["edit", "image-to-image", "--help"])

    assert stopped.value.code == 0
    output = capsys.readouterr().out
    assert "desired final image" in output
    assert "not an instruction-edit command" in output


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
    assert arguments.composite == "source_over"
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
    assert arguments.safety_filter == "default"
    assert arguments.seed == 42


def test_deterministic_program_surface_exposes_named_bindings_and_dry_run() -> None:
    arguments = parser().parse_args(
        [
            "edit",
            "run",
            "--program",
            "edit.json",
            "--input",
            "scene=scene.png",
            "--mask",
            "selection=mask.png",
            "--dry-run",
        ]
    )

    assert arguments.group == "edit" and arguments.command == "run"
    assert arguments.program == Path("edit.json")
    assert arguments.input == ["scene=scene.png"]
    assert arguments.mask == ["selection=mask.png"]
    assert arguments.output is None and arguments.dry_run is True
