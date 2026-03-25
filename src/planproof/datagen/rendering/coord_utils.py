"""Pure coordinate conversion utilities for the rendering layer.

All bounding boxes in PlanProof use a single canonical coordinate system:
  - Unit:   pixels
  - DPI:    300 (CANONICAL_DPI)
  - Origin: top-left corner of the page

PDF documents use a different native system:
  - Unit:   points (1 point = 1/72 inch)
  - Origin: bottom-left corner of the page

These pure functions convert between the two systems.  They have no side
effects and carry no state, making them safe to call from any thread or
process in a parallel corpus generation pipeline.

# DESIGN: Using NamedTuples for return values (rather than plain tuples or
# dataclasses) gives callers named attribute access (.x, .y) without the
# overhead of frozen dataclasses.  Because these functions are called once per
# placed value per page, the lightweight NamedTuple representation is preferred
# over Pydantic models here — there is no validation needed for internal math.
"""

from __future__ import annotations

from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# WHY: Fixing the canonical DPI as a module-level constant means every layer
# (rendering, evaluation, cropping) shares the same reference without passing
# it as a parameter.  Changing resolution only requires updating this one value.
CANONICAL_DPI: int = 300

# WHY: PDF uses points as its native length unit (1 point = 1/72 inch).
# This constant is the authoritative source; never hard-code 72 elsewhere.
PDF_POINTS_PER_INCH: int = 72

# WHY: Pre-computing the scale factor avoids repeated division in hot loops
# and makes the relationship between the two coordinate systems explicit.
# 300 pixels/inch ÷ 72 points/inch = pixels per point.
SCALE_FACTOR: float = CANONICAL_DPI / PDF_POINTS_PER_INCH


# ---------------------------------------------------------------------------
# Coordinate NamedTuples
# ---------------------------------------------------------------------------

class PixelCoord(NamedTuple):
    """A 2-D point in the canonical pixel coordinate system (origin top-left)."""

    x: float
    y: float


class PdfCoord(NamedTuple):
    """A 2-D point in PDF point coordinates (origin bottom-left)."""

    x: float
    y: float


# ---------------------------------------------------------------------------
# Conversion functions
# ---------------------------------------------------------------------------

def pdf_points_to_pixels(
    x_pt: float,
    y_pt: float,
    page_height_pt: float,
) -> PixelCoord:
    """Convert a PDF point coordinate to a canonical pixel coordinate.

    PDF origin is the *bottom-left* corner of the page, so Y increases upward.
    Our canonical system has the origin at the *top-left*, so Y increases
    downward.  The conversion requires both a scale and a Y-axis flip.

    Args:
        x_pt:           Horizontal position in PDF points (from left edge).
        y_pt:           Vertical position in PDF points (from bottom edge).
        page_height_pt: Total page height in PDF points — required to flip Y.

    Returns:
        PixelCoord with x and y in pixels at CANONICAL_DPI, origin top-left.

    # WHY: Taking page_height_pt as an argument (rather than assuming A4 or
    # Letter) makes this function work correctly for any page size, including
    # non-standard document formats that appear in planning applications.
    """
    x_px = x_pt * SCALE_FACTOR
    # Flip Y: a point at y_pt from the bottom is (page_height_pt - y_pt) from
    # the top in PDF point space, then scaled to pixels.
    y_px = (page_height_pt - y_pt) * SCALE_FACTOR
    return PixelCoord(x=x_px, y=y_px)


def pixels_to_pdf_points(
    x_px: float,
    y_px: float,
    page_height_pt: float,
) -> PdfCoord:
    """Convert a canonical pixel coordinate back to PDF point coordinates.

    This is the inverse of pdf_points_to_pixels.  Useful when a renderer
    needs to place a pre-computed pixel bounding box into a PDF canvas.

    Args:
        x_px:           Horizontal position in pixels (from left edge).
        y_px:           Vertical position in pixels (from top edge).
        page_height_pt: Total page height in PDF points — required to flip Y.

    Returns:
        PdfCoord with x and y in PDF points (72 DPI), origin bottom-left.

    # WHY: Having an explicit inverse function prevents callers from
    # implementing their own (error-prone) reverse transform.  A single
    # implementation means the round-trip error is bounded to floating-point
    # precision rather than accumulating across ad-hoc implementations.
    """
    x_pt = x_px / SCALE_FACTOR
    # Reverse the Y flip: pixel y_px from top → (page_height_pt - y_px/scale)
    # from bottom in PDF points.
    y_pt = page_height_pt - (y_px / SCALE_FACTOR)
    return PdfCoord(x=x_pt, y=y_pt)
