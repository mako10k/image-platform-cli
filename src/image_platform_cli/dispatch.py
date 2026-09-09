from collections.abc import Sequence

from .v4.cli import main as _image4_main


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate the stable command to the implementation fixed by this package."""
    return _image4_main(argv)
