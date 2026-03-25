"""Tests for coordinate conversion utilities.

# WHY: Coordinate conversion is a pure math concern with well-known expected
# outputs.  Writing tests first ensures the conversion formulas are correct
# before any renderer depends on them.  Wrong coordinate transforms would
# silently produce bounding boxes that don't align with the text on the page,
# making the entire ground-truth corpus unreliable.
"""
from __future__ import annotations

import math

import pytest

from planproof.datagen.rendering.coord_utils import (
    CANONICAL_DPI,
    PDF_POINTS_PER_INCH,
    SCALE_FACTOR,
    PixelCoord,
    PdfCoord,
    pdf_points_to_pixels,
    pixels_to_pdf_points,
)


class TestConstants:
    def test_canonical_dpi(self) -> None:
        assert CANONICAL_DPI == 300

    def test_pdf_points_per_inch(self) -> None:
        assert PDF_POINTS_PER_INCH == 72

    def test_scale_factor(self) -> None:
        # WHY: The scale factor must be exactly 300/72 so that a length of 72
        # points (= 1 inch) converts to exactly 300 pixels (1 inch at 300 DPI).
        assert SCALE_FACTOR == pytest.approx(300 / 72)


class TestScaleFactor:
    def test_72pt_equals_300px(self) -> None:
        """72 PDF points (= 1 inch) should equal 300 pixels at 300 DPI."""
        # WHY: This is the fundamental calibration check for the coordinate
        # system.  If this fails, every bounding box in the corpus is wrong.
        page_height_pt = 841.0  # A4 height in points
        result = pdf_points_to_pixels(
            x_pt=72.0,
            y_pt=0.0,  # y doesn't affect x output
            page_height_pt=page_height_pt,
        )
        assert result.x == pytest.approx(300.0)


class TestPdfToPixelOriginFlip:
    def test_origin_flip(self) -> None:
        """PDF origin is bottom-left; pixel origin is top-left — Y must flip."""
        # WHY: PDF coordinate (0, 0) is the bottom-left corner of the page, but
        # our canonical pixel system has (0, 0) at the top-left.  A point at the
        # very bottom of a PDF page should map to the maximum Y pixel value.
        page_height_pt = 100.0  # simple round number for easy hand-calculation
        result = pdf_points_to_pixels(
            x_pt=0.0,
            y_pt=0.0,  # bottom of page in PDF coords
            page_height_pt=page_height_pt,
        )
        # bottom of PDF (y=0) → top of pixel space is page_height_pt * SCALE_FACTOR
        expected_y_px = page_height_pt * SCALE_FACTOR
        assert result.y == pytest.approx(expected_y_px)

    def test_top_of_page_maps_to_zero_pixels(self) -> None:
        """Top of PDF page (y = page_height_pt) should map to y_px = 0."""
        page_height_pt = 100.0
        result = pdf_points_to_pixels(
            x_pt=0.0,
            y_pt=page_height_pt,  # top of page in PDF coords
            page_height_pt=page_height_pt,
        )
        assert result.y == pytest.approx(0.0)

    def test_midpoint_maps_to_half_page_height(self) -> None:
        """Mid-page Y in PDF coords should map to mid-page Y in pixel coords."""
        page_height_pt = 100.0
        result = pdf_points_to_pixels(
            x_pt=0.0,
            y_pt=50.0,
            page_height_pt=page_height_pt,
        )
        expected_y_px = (page_height_pt - 50.0) * SCALE_FACTOR
        assert result.y == pytest.approx(expected_y_px)


class TestRoundTrip:
    def test_round_trip_origin(self) -> None:
        """Converting PDF→pixel→PDF should recover the original coordinates."""
        page_height_pt = 841.89  # A4 exact
        x_orig, y_orig = 72.0, 200.0

        pixel = pdf_points_to_pixels(x_orig, y_orig, page_height_pt)
        recovered = pixels_to_pdf_points(pixel.x, pixel.y, page_height_pt)

        assert recovered.x == pytest.approx(x_orig, rel=1e-6)
        assert recovered.y == pytest.approx(y_orig, rel=1e-6)

    def test_round_trip_arbitrary_point(self) -> None:
        """Round-trip for an arbitrary interior point."""
        page_height_pt = 792.0  # US Letter height
        x_orig, y_orig = 300.5, 612.3

        pixel = pdf_points_to_pixels(x_orig, y_orig, page_height_pt)
        recovered = pixels_to_pdf_points(pixel.x, pixel.y, page_height_pt)

        assert recovered.x == pytest.approx(x_orig, rel=1e-6)
        assert recovered.y == pytest.approx(y_orig, rel=1e-6)

    def test_round_trip_preserves_type(self) -> None:
        """Return types must be NamedTuples with named fields."""
        page_height_pt = 841.0
        pixel = pdf_points_to_pixels(36.0, 100.0, page_height_pt)
        assert isinstance(pixel, PixelCoord)
        assert hasattr(pixel, "x") and hasattr(pixel, "y")

        pdf = pixels_to_pdf_points(pixel.x, pixel.y, page_height_pt)
        assert isinstance(pdf, PdfCoord)
        assert hasattr(pdf, "x") and hasattr(pdf, "y")
