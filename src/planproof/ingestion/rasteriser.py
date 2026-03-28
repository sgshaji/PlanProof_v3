"""Image loading and rasterisation utility."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})


def is_image_file(path: Path) -> bool:
    """Check whether *path* has a recognised image extension."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def load_image(path: Path) -> Image.Image:
    """Open an image file, raising ``FileNotFoundError`` if absent."""
    if not path.exists():
        msg = f"Image not found: {path}"
        raise FileNotFoundError(msg)
    return Image.open(path)
