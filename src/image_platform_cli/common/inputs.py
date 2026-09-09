import base64
from pathlib import Path

from .errors import ApiError
from .files import read_image


def require_one_image_source(
    input_path: Path | None, artifact_id: str | None, *, operation: str
) -> None:
    if (input_path is None) == (artifact_id is None):
        raise ApiError(f"exactly one {operation} input or Artifact is required")


def validate_caption_controls(instruction: str, max_output_tokens: int) -> None:
    if not instruction.strip() or len(instruction) > 2048:
        raise ApiError("caption instruction must contain 1 to 2048 characters")
    if not 1 <= max_output_tokens <= 512:
        raise ApiError("max output tokens must be from 1 through 512")


def inline_image(path: Path) -> dict[str, str]:
    data, mime_type, _, _ = read_image(path)
    return {"mime_type": mime_type, "data_base64": base64.b64encode(data).decode("ascii")}


def generation_execution(wait_seconds: int, allow_long_wait: bool) -> dict[str, object]:
    return {
        "wait_seconds": wait_seconds,
        "allow_long_wait": allow_long_wait,
        "accept_async": True,
    }
