import hashlib
import os
import secrets
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .errors import ApiError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_194_304


def require_available_output(output: Path) -> None:
    if not output.parent.is_dir():
        raise ApiError("output directory does not exist")
    if output.exists():
        raise ApiError("output file already exists")


def read_image(path: Path) -> tuple[bytes, str, int, int]:
    if not path.is_file():
        raise ApiError("input image does not exist or is not a regular file")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ApiError("input image could not be read") from error
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ApiError("input image must contain at most 10 MiB")
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ApiError("input image is invalid") from error
    mime_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(
        image_format or ""
    )
    if mime_type is None:
        raise ApiError("input image must be PNG, JPEG, or WebP")
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ApiError("input image exceeds the supported pixel limit")
    return data, mime_type, width, height


def save_bytes_exclusive(data: bytes, output: Path) -> None:
    require_available_output(output)
    temporary = output.with_name(f".{output.name}.{secrets.token_hex(8)}.part")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as error:
            raise ApiError("output file already exists") from error
        except OSError as error:
            raise ApiError("output file could not be written") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def verify_artifact(
    data: bytes, response_content_type: str | None, metadata: dict[str, object]
) -> None:
    expected_sha = _required(metadata, "sha256", str)
    expected_size = _required(metadata, "size_bytes", int)
    expected_mime = _required(metadata, "mime_type", str)
    actual_content_type = (
        response_content_type.split(";", 1)[0].strip() if response_content_type else None
    )
    if (
        not data
        or hashlib.sha256(data).hexdigest() != expected_sha
        or len(data) != expected_size
        or actual_content_type != expected_mime
    ):
        raise ApiError("Artifact download integrity check failed")
    width = metadata.get("width")
    height = metadata.get("height")
    if width is None and height is None:
        return
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
    ):
        raise ApiError("image API returned malformed Artifact metadata")
    expected_format = {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(expected_mime)
    if expected_format is None:
        raise ApiError("Artifact image MIME type cannot be verified")
    try:
        with Image.open(BytesIO(data)) as image:
            actual_format = image.format
            dimensions = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise ApiError("Artifact download integrity check failed") from error
    if actual_format != expected_format or dimensions != (width, height):
        raise ApiError("Artifact download integrity check failed")


def _required[T](body: dict[str, object], name: str, type_: type[T]) -> T:
    value = body.get(name)
    if not isinstance(value, type_) or isinstance(value, bool):
        raise ApiError("image API returned malformed Artifact metadata")
    return value
