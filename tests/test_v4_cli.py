from typing import Any

from image_platform_cli.v4.cli import _page_params, main, parser


def test_v4_parser_exposes_discovery_job_and_artifact_capabilities() -> None:
    parse = parser().parse_args

    assert parse(["capabilities"]).group == "capabilities"
    assert parse(["model-profiles"]).group == "model-profiles"
    assert parse(["job", "show", "job_1"]).job_id == "job_1"
    preview = parse(["job", "preview-access", "job_1", "step_1", "output_1"])
    assert (preview.job_id, preview.step_id, preview.output) == (
        "job_1",
        "step_1",
        "output_1",
    )
    assert parse(["artifact", "show", "art_1"]).artifact_id == "art_1"
    assert parse(["artifact", "download", "art_1", "-o", "out.png"]).output.name == "out.png"
    assert parse(["artifact", "upload", "in.png"]).input.name == "in.png"
    assert parse(["prompt", "optimize", "a cup", "--seed", "7"]).seed == 7
    assert parse(["search", "red cup", "--limit", "5"]).query == "red cup"
    assert parse(["caption", "in.png", "--max-output-tokens", "64"]).input.name == "in.png"
    assert parse(["caption", "in.png", "--capture-input"]).capture_input is True
    assert parse(["generate", "a cup", "-o", "out.png", "--wait", "60"]).wait == 60
    assert parse(["batch", "plan", "two cups", "--count", "2"]).count == 2


def test_v4_job_collection_preserves_repeated_filters() -> None:
    args: Any = parser().parse_args(
        [
            "job",
            "list",
            "--status",
            "queued",
            "--status",
            "running",
            "--operation",
            "generate",
            "--created-after",
            "2026-09-01T00:00:00Z",
            "--created-before",
            "2026-09-02T00:00:00Z",
            "--cursor",
            "next_1",
            "--limit",
            "50",
        ]
    )

    assert _page_params(args, ("status", "operation")) == [
        ("status", "queued"),
        ("status", "running"),
        ("operation", "generate"),
        ("created_after", "2026-09-01T00:00:00Z"),
        ("created_before", "2026-09-02T00:00:00Z"),
        ("cursor", "next_1"),
        ("limit", 50),
    ]


def test_v4_artifact_collection_preserves_semantic_filters() -> None:
    args: Any = parser().parse_args(
        [
            "artifact",
            "list",
            "--state",
            "ready",
            "--kind",
            "image",
            "--namespace",
            "campaign",
        ]
    )

    assert _page_params(args, ("state", "kind")) == [
        ("state", "ready"),
        ("kind", "image"),
        ("limit", 20),
    ]


def test_v4_help_topic_is_local_and_reachable(capsys: Any) -> None:
    assert main(["help", "job"]) == 0
    assert "usage: image4 job" in capsys.readouterr().out
