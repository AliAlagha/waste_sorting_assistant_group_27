"""
ImageValidator - first stage of the pipeline (FR-01, FR-02, NFR-07).

Checks, in this order (cheapest first):
  1. input is real, non-empty ``bytes``
  2. file size <= limit
  3. data can be opened as an image (header readable)
  4. format is allowed (JPEG / PNG by default)
  5. resolution >= minimum
  6. pixel data is fully decodable (detects truncated files)

Security note (NFR-07): the uploaded bytes are ONLY ever decoded by Pillow as
image data. They are never executed, never written to disk, and never used to
build a file path.
"""
from __future__ import annotations

import io
from typing import Iterable

from PIL import Image, ImageOps, UnidentifiedImageError

from .exceptions import (
    CorruptedImageError,
    FileTooLargeError,
    ImageTooSmallError,
    InvalidImageError,
    UnsupportedFormatError,
)


class ImageValidator:
    """Validates raw upload bytes and returns a clean RGB ``PIL.Image``."""

    def __init__(
        self,
        max_file_size_mb: float = 5,
        min_resolution: int = 64,
        allowed_formats: Iterable[str] = ("JPEG", "PNG"),
    ) -> None:
        self.max_bytes = int(max_file_size_mb * 1024 * 1024)
        self.min_resolution = min_resolution
        self.allowed_formats = tuple(f.upper() for f in allowed_formats)

    def validate(self, data: bytes) -> Image.Image:
        """Return an RGB image or raise a subclass of ``InvalidImageError``."""
        # 1) type / emptiness ------------------------------------------------
        if not isinstance(data, (bytes, bytearray)):
            raise InvalidImageError("Image data must be given as bytes")
        if len(data) == 0:
            raise CorruptedImageError("The uploaded file is empty")

        # 2) size limit ------------------------------------------------------
        if len(data) > self.max_bytes:
            limit_mb = self.max_bytes / (1024 * 1024)
            raise FileTooLargeError(f"File is larger than {limit_mb:g} MB")

        # 3) open (lazy: only the header is parsed here) ---------------------
        try:
            image = Image.open(io.BytesIO(data))
        except Image.DecompressionBombError as exc:  # absurdly large pixel count
            raise InvalidImageError("Image dimensions are unreasonably large") from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise CorruptedImageError("File is not a readable image") from exc

        # 4) format ----------------------------------------------------------
        if (image.format or "").upper() not in self.allowed_formats:
            raise UnsupportedFormatError(
                f"Unsupported format '{image.format}'. "
                f"Allowed: {', '.join(self.allowed_formats)}")

        # 5) resolution ------------------------------------------------------
        if min(image.size) < self.min_resolution:
            raise ImageTooSmallError(
                f"Image is {image.width}x{image.height}px; the shorter side must be "
                f"at least {self.min_resolution}px")

        # 6) full decode (catches truncated / damaged files) -----------------
        try:
            image.load()
        except (OSError, ValueError, SyntaxError) as exc:
            raise CorruptedImageError("Image data is damaged or truncated") from exc

        # Phone photos store rotation in EXIF metadata; apply it so the model
        # sees the picture upright, then normalise the colour mode to RGB.
        image = ImageOps.exif_transpose(image)
        return image.convert("RGB")
