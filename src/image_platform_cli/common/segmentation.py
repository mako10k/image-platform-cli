"""Local segmentation output rendering shared by CLI implementations."""

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from . import files
from .errors import ApiError
from .models import SegmentationResult


def save_segmentation_outputs(
    result: SegmentationResult,
    *,
    mask_output: Path | None,
    foreground_output: Path | None,
    background_output: Path | None,
) -> None:
    destinations = tuple(
        output
        for output in (mask_output, foreground_output, background_output)
        if output is not None
    )
    if not destinations:
        raise ApiError("at least one segmentation output is required")
    if len(set(destinations)) != len(destinations):
        raise ApiError("segmentation output paths must be distinct")
    for output in destinations:
        files.require_available_output(output)
    if mask_output is not None:
        files.save_bytes_exclusive(result.mask_data, mask_output)
    if foreground_output is None and background_output is None:
        return
    try:
        with Image.open(BytesIO(result.source_data)) as source_image:
            source = source_image.convert("RGBA")
        with Image.open(BytesIO(result.mask_data)) as mask_image:
            mask = mask_image.convert("L")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ApiError("segmentation images could not be decoded") from error
    for rendered_output, alpha in (
        (foreground_output, mask),
        (background_output, mask.point(lambda value: 255 - value)),
    ):
        if rendered_output is None:
            continue
        rendered = source.copy()
        rendered.putalpha(alpha)
        buffer = BytesIO()
        rendered.save(buffer, format="PNG")
        files.save_bytes_exclusive(buffer.getvalue(), rendered_output)
