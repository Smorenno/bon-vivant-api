from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

_COVER_LIKE_MARKERS = ("_cover", "_preview")
_COVER_MAX_WIDTH = 800
_DEFAULT_MAX_WIDTH = 1600
_JPEG_QUALITY = 90


class ImageCompressionError(Exception):
    def __init__(self, filename: str, reason: str) -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"Failed to compress '{filename}': {reason}")


def is_cover_like(filename: str) -> bool:
    """True for cover/preview slots, which use a smaller max width."""
    name = filename.lower()
    if name == "preview.jpg":
        return True
    return any(marker in name for marker in _COVER_LIKE_MARKERS)


def compress_image(raw_bytes: bytes, filename: str) -> bytes:
    """Resize, fix EXIF rotation and re-encode as quality-90 JPEG.

    Never enlarges an image smaller than the target max width. Raises
    ImageCompressionError (never a bare Exception) if the bytes can't be
    decoded as an image.
    """
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
        image = ImageOps.exif_transpose(image)
    except UnidentifiedImageError as exc:
        raise ImageCompressionError(filename, "unrecognized image format") from exc
    except OSError as exc:
        raise ImageCompressionError(filename, str(exc)) from exc

    if image is None:
        raise ImageCompressionError(filename, "image has no pixel data")

    if image.mode != "RGB":
        image = image.convert("RGB")

    max_width = _COVER_MAX_WIDTH if is_cover_like(filename) else _DEFAULT_MAX_WIDTH
    if image.width > max_width:
        new_height = round(image.height * (max_width / image.width))
        image = image.resize((max_width, new_height), Image.LANCZOS)

    output = io.BytesIO()
    try:
        image.save(output, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    except OSError as exc:
        raise ImageCompressionError(filename, str(exc)) from exc

    return output.getvalue()
