"""Tests for image rasterisation utility."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from planproof.ingestion.rasteriser import is_image_file, load_image


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
    img = Image.new("RGB", (200, 100), color="white")
    path = tmp_path / "test.png"
    img.save(path)
    return path


@pytest.fixture
def jpg_file(tmp_path: Path) -> Path:
    img = Image.new("RGB", (200, 100), color="white")
    path = tmp_path / "test.jpg"
    img.save(path)
    return path


def test_load_png_returns_image(png_file: Path) -> None:
    img = load_image(png_file)
    assert img is not None
    assert img.size == (200, 100)


def test_load_jpg_returns_image(jpg_file: Path) -> None:
    img = load_image(jpg_file)
    assert img is not None


def test_load_nonexistent_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_image(Path("/nonexistent.png"))


def test_is_image_file_png(png_file: Path) -> None:
    assert is_image_file(png_file) is True


def test_is_image_file_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert is_image_file(pdf) is False


def test_is_image_file_nonexistent() -> None:
    assert is_image_file(Path("/nonexistent.xyz")) is False
