"""Exercise every public help path without credentials, files or network access."""

import argparse
import shlex
from collections.abc import Iterator
from typing import Any

import pytest

from image_platform_cli.v4.cli import main, parser
from image_platform_cli.v4.help_navigation import TOPICS, children


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
