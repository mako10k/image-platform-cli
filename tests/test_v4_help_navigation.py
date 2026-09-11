"""Exercise every public help path without credentials, files or network access."""

import argparse
import json
import shlex
from collections.abc import Iterator
from typing import Any

import pytest

from image_platform_cli.common.errors import CliError
from image_platform_cli.v4.cli import _error_help_topic, main, parser
from image_platform_cli.v4.help_navigation import GUIDES, TOPICS, children


def paths(
    command: argparse.ArgumentParser, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    yield prefix, command
    for name, child in children(command).items():
        yield from paths(child, (*prefix, name))


HELP_PATHS = list(paths(parser()))


@pytest.mark.parametrize(("path", "command"), HELP_PATHS)
def test_all_help_paths_are_offline_and_navigable(
    path: tuple[str, ...], command: argparse.ArgumentParser, monkeypatch: Any, capsys: Any
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("help must not construct HTTP or credential clients")

    monkeypatch.setattr("image_platform_cli.v4.cli.httpx.Client", forbidden)
    monkeypatch.setattr("image_platform_cli.v4.cli.KeyringCredentialStore", forbidden)
    assert main(["help", *path]) == 0
    rendered = capsys.readouterr().out
    assert command.format_help().rstrip() in rendered
    assert "GUIDANCE\n" in rendered
    assert "EXAMPLES" in rendered
    for child in children(command):
        assert f"image help {' '.join((*path, child))}" in rendered
    if path:
        assert "RELATED\n  " + " ".join(("image", "help", *path[:-1])) in rendered


def test_guidance_covers_actual_tree_without_obsolete_commands() -> None:
    actual = {" ".join(path) for path, _ in HELP_PATHS}
    actual.remove("edit i2i")
    assert set(TOPICS) == actual


@pytest.mark.parametrize("topic", TOPICS)
def test_every_example_parses_using_v4_flags(topic: str) -> None:
    # Parse only: files, IDs and registered font values are user-supplied placeholders.
    parser().parse_args(shlex.split(TOPICS[topic][1]))


@pytest.mark.parametrize("topic", GUIDES)
def test_every_help_only_guide_is_reachable_and_has_a_parsable_example(
    topic: str, capsys: Any
) -> None:
    assert main(["help", *topic.split()]) == 0
    rendered = capsys.readouterr().out
    assert f"Help topic: {topic}" in rendered
    assert "DETAILS\n" in rendered
    parser().parse_args(shlex.split(GUIDES[topic].example))


def test_job_submit_advertises_guided_profile_and_recovery_topics(capsys: Any) -> None:
    assert main(["help", "job", "submit"]) == 0
    rendered = capsys.readouterr().out
    for child in ("controlnet-canny", "guided-edit", "ip-adapter-plus", "recovery"):
        assert f"image help job submit {child}" in rendered


@pytest.mark.parametrize(
    ("argv", "destination"),
    (
        (("--help",), "image help"),
        (("job", "--help"), "image help job"),
        (("job", "submit", "--help"), "image help job submit"),
        (("artifact", "upload", "--help"), "image help artifact upload recovery"),
    ),
)
def test_standard_argparse_help_links_to_guided_navigation(
    argv: tuple[str, ...], destination: str, capsys: Any
) -> None:
    with pytest.raises(SystemExit) as stopped:
        parser().parse_args(argv)
    assert stopped.value.code == 0
    assert destination in capsys.readouterr().out


@pytest.mark.parametrize("topic", ("job submit controlnet-canny", "job submit ip-adapter-plus"))
def test_guided_profile_help_contains_valid_complete_job_json(topic: str, capsys: Any) -> None:
    assert main(["help", *topic.split()]) == 0
    rendered = capsys.readouterr().out
    request, _ = json.JSONDecoder().raw_decode(rendered[rendered.index("{\n") :])
    assert request["pipeline"]["steps"][0]["params"]["profile"] in {
        "i2i-controlnet-canny-sd15",
        "i2i-ip-adapter-plus-sd15",
    }
    assert request["policy"]["result_mode"] == "atomic"


def test_job_submit_error_points_to_recovery_help(monkeypatch: Any, capsys: Any) -> None:
    def fail(_: argparse.Namespace) -> bool:
        raise CliError("invalid request")

    monkeypatch.setattr("image_platform_cli.v4.cli._prepare_output", fail)
    assert main(["job", "submit", "--request", "job.json"]) == 2
    assert (
        "help: Run `image help job submit recovery` for recovery guidance."
        in capsys.readouterr().err
    )


def test_error_help_selects_artifact_upload_recovery() -> None:
    args = parser().parse_args(["artifact", "upload", "scene.png"])
    assert _error_help_topic(args) == "artifact upload recovery"


def test_i2i_alias_has_same_guidance(capsys: Any) -> None:
    main(["help", "edit", "i2i"])
    assert TOPICS["edit image-to-image"][0] in capsys.readouterr().out


@pytest.mark.parametrize("topic", [("missing",), ("edit", "missing"), ("auth", "login", "missing")])
def test_unknown_topics_report_valid_children(topic: tuple[str, ...], capsys: Any) -> None:
    assert main(["help", *topic]) == 2
    result = capsys.readouterr()
    assert not result.out
    assert "unknown help topic" in result.err
    assert "available:" in result.err


def test_unknown_job_submit_topic_lists_help_only_children(capsys: Any) -> None:
    assert main(["help", "job", "submit", "missing"]) == 2
    result = capsys.readouterr()
    assert "controlnet-canny" in result.err
    assert "recovery" in result.err
