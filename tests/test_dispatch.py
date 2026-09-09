from collections.abc import Sequence

import pytest

from image_platform_cli import dispatch


def test_stable_image_dispatches_wholly_to_image4(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Sequence[str] | None] = []

    def image4(argv: Sequence[str] | None = None) -> int:
        calls.append(argv)
        return 17

    monkeypatch.setattr(dispatch, "_image4_main", image4)

    assert dispatch.main(("capabilities",)) == 17
    assert calls == [("capabilities",)]
