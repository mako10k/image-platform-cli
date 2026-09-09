import base64
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from image_platform_cli.common.errors import ApiError, CliError
from image_platform_cli.v4.api import V4ApiClient
from image_platform_cli.v4.cli import main, parser
from image_platform_cli.v4.program_cli import prepare_cli_program, run_cli_program
from image_platform_cli.v4.program_schema import normalize_program

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "fixture",
    sorted(
        str(p.relative_to(FIXTURES))
        for p in FIXTURES.rglob("*.json")
        if "program" in json.loads(p.read_text()).get("request", {})
    ),
)
def test_normalization_preserves_api_programs(fixture: str) -> None:
    program = json.loads((FIXTURES / fixture).read_text())["request"]["program"]
    assert normalize_program(program) == program


@pytest.mark.parametrize("mode", ["run", "verify"])
def test_generic_program_execution_and_verification(tmp_path: Path, mode: str) -> None:
    wire = json.loads((FIXTURES / "composite/cli-composite-masked-crop.json").read_text())
    program_path = tmp_path / "program.json"
    program_path.write_text(json.dumps(wire["request"]["program"]))
    args = ["edit", mode, "--program", str(program_path)]
    for name, value in wire["request"]["inputs"].items():
        path = tmp_path / f"{name}.png"
        path.write_bytes(base64.b64decode(value["data_base64"]))
        args.extend(["--mask" if name == "mask" else "--input", f"{name}={path}"])
    output = tmp_path / "output.png"
    if mode == "run":
        args.extend(["-o", str(output)])
    parsed = parser().parse_args(args)
    assert not prepare_cli_program(parsed)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert json.loads(request.content) == wire["request"]
        return httpx.Response(200, json=wire["body"], headers=wire["headers"])

    auth = Mock()
    auth.access_token.return_value = "dummy"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        run_cli_program(parsed, auth, V4ApiClient(http, "https://api.invalid"))
    assert len(calls) == (1 if mode == "run" else 2)
    assert output.exists() == (mode == "run")


def test_generic_reproducibility_mismatch_is_rejected(tmp_path: Path) -> None:
    from decimal import Decimal

    from image_platform_cli.common.models import DeterministicEditResult

    args = parser().parse_args(["edit", "verify", "--program", "unused.json"])
    args.prepared_program = {}
    args.prepared_paths = {}
    api = Mock()
    api.run_program.side_effect = [
        DeterministicEditResult(b"a", "image/png", "a", 1, 1, "p", Decimal(0)),
        DeterministicEditResult(b"b", "image/png", "b", 1, 1, "p", Decimal(0)),
    ]
    with pytest.raises(CliError, match="reproducibility"):
        run_cli_program(args, Mock(), api)


def test_schema_defaults_and_decimal_bounds() -> None:
    program = {
        "inputs": {"source": "image"},
        "source_input": "source",
        "commands": [{"id": "tone", "op": "tone", "contrast": 2}],
    }
    normalized = normalize_program(program)
    assert normalized["commands"][0]["contrast"] == "2"
    assert normalized["commands"][0]["coverage"] is None
    assert normalized["encoding"]["quality"] == 90
    invalid = copy.deepcopy(program)
    invalid["commands"][0]["contrast"] = "5"
    with pytest.raises(ApiError):
        normalize_program(invalid)


def test_program_dry_run_is_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "program.json"
    path.write_text(
        json.dumps(
            {
                "revision": "deterministic-edit-v1",
                "inputs": {"custom": "image"},
                "source_input": "custom",
                "commands": [{"id": "convert", "op": "convert"}],
                "encoding": {"format": "png"},
            }
        )
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("offline preview attempted transport/config")

    monkeypatch.setattr("image_platform_cli.v4.cli.Config.staging", forbidden)
    assert (
        main(["edit", "run", "--program", str(path), "--input", "custom=absent.png", "--dry-run"])
        == 0
    )


def test_generic_split_receipt_keeps_logical_identity(tmp_path: Path) -> None:
    from image_platform_cli.v4.single_edits import canonical_hash

    wire = json.loads((FIXTURES / "composite/cli-composite-masked-crop.json").read_text())
    program = wire["request"]["program"]
    data = wire["body"]["data"]
    original_commands = data["receipt"]["commands"]
    nodes = []
    for index, command in enumerate(program["commands"]):
        physical = {**program, "commands": [command]}
        nodes.append(
            {
                "step_id": f"image_ops_{index + 1}",
                "width": 8,
                "height": 8,
                "color_sample_work": 0,
                "command_ids": [command["id"]],
                "fused_command_groups": [],
                "program_sha256": canonical_hash(physical),
            }
        )
    data["planner_receipt"]["nodes"] = nodes
    data["receipt"]["commands"] = original_commands[-1:]
    data["receipt"]["program_sha256"] = nodes[-1]["program_sha256"]
    # A split execution consumes an intermediate source, which the response does not expose.
    data["receipt"]["input_sha256s"]["source"] = "a" * 64
    wire["headers"]["x-image-program-sha256"] = nodes[-1]["program_sha256"]
    paths = {}
    for name, value in wire["request"]["inputs"].items():
        path = tmp_path / f"{name}.png"
        path.write_bytes(base64.b64decode(value["data_base64"]))
        paths[name] = path
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=wire["body"], headers=wire["headers"])
        )
    ) as http:
        result = V4ApiClient(http, "https://api.invalid").run_program(
            "dummy", program=program, paths=paths
        )
    assert result.program_sha256 == canonical_hash(program)
    assert result.command_receipts[0][0] == "crop-result"
