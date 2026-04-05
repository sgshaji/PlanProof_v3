"""Shared drawing helpers for site plan and floor plan generators.

Provides page layout computation, rich title blocks, legend boxes,
copyright notes, dimension lines, and hatching — all reused by
both SitePlanGenerator and FloorPlanGenerator.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Final

from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas as rl_canvas  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANNO_FONT: Final[str] = "Helvetica"
ANNO_FONT_SIZE: Final[float] = 7.0
TICK_LEN: Final[float] = 3 * mm

_ARCHITECT_FIRMS: Final[tuple[str, ...]] = (
    "KIYANI ARCHITECTURE AND DEVELOPMENTS",
    "STUDIO PLAN DESIGN LTD",
    "HARBORNE DESIGN ASSOCIATES",
    "APEX ARCHITECTURAL SERVICES",
    "CLEARVIEW PLANNING & DESIGN",
    "WESTBURY DESIGN STUDIO",
    "MIDLANDS ARCHITECTURE CO",
)

_ARCHITECT_PHONES: Final[tuple[str, ...]] = (
    "0121 269 7270",
    "0121 456 3890",
    "0117 325 4100",
    "0115 948 2200",
    "0113 245 6700",
)

_ROAD_NAMES: Final[tuple[str, ...]] = (
    "ACACIA AVENUE",
    "CHURCH ROAD",
    "STATION LANE",
    "VICTORIA ROAD",
    "PARK DRIVE",
    "HIGH STREET",
    "RECTORY ROAD",
    "KINGS HEATH ROAD",
    "HARBORNE LANE",
    "SIR HARRYS ROAD",
)

_COPYRIGHT_NOTES: Final[tuple[str, ...]] = (
    "1. Copyright of the architect. Do not reproduce without permission.",
    "2. Only scale from drawings for planning purposes.",
    "3. Use figured dimensions only.",
    "4. All dimensions to be checked on site.",
)


# ---------------------------------------------------------------------------
# PageLayout
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    """A simple rectangle in PDF points."""
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class PageLayout:
    """Zone rectangles for a drawing page."""
    page_w: float
    page_h: float
    drawing_area: Rect      # main area for the plan content
    title_block: Rect       # bottom-right
    legend: Rect            # above title block
    notes: Rect             # bottom-left
    north_arrow: Rect       # top-right panel


def compute_page_layout(
    page_w: float,
    page_h: float,
    margin: float = 15 * mm,
    right_panel_w: float = 85 * mm,
    bottom_panel_h: float = 35 * mm,
) -> PageLayout:
    """Compute zone rectangles for a drawing page."""
    title_block_h = 55 * mm
    legend_h = 40 * mm

    # Drawing area: left portion of the page
    da = Rect(
        x=margin,
        y=margin + bottom_panel_h,
        w=page_w - 2 * margin - right_panel_w,
        h=page_h - 2 * margin - bottom_panel_h,
    )

    # Title block: bottom of right panel
    tb = Rect(
        x=page_w - margin - right_panel_w,
        y=margin,
        w=right_panel_w,
        h=title_block_h,
    )

    # Legend: above title block in right panel
    lg = Rect(
        x=page_w - margin - right_panel_w,
        y=margin + title_block_h + 5 * mm,
        w=right_panel_w,
        h=legend_h,
    )

    # Notes: bottom-left
    nt = Rect(
        x=margin,
        y=margin,
        w=page_w - 2 * margin - right_panel_w - 10 * mm,
        h=bottom_panel_h,
    )

    # North arrow: top of right panel
    na = Rect(
        x=page_w - margin - right_panel_w,
        y=page_h - margin - 40 * mm,
        w=right_panel_w,
        h=40 * mm,
    )

    return PageLayout(
        page_w=page_w,
        page_h=page_h,
        drawing_area=da,
        title_block=tb,
        legend=lg,
        notes=nt,
        north_arrow=na,
    )


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def draw_rich_title_block(
    c: rl_canvas.Canvas,
    rect: Rect,
    rng: random.Random,
    drawing_title: str,
    scale_text: str,
    seed: int,
) -> None:
    """Draw a multi-row title block matching BCC architectural drawing style."""
    c.saveState()
    c.setLineWidth(0.8)
    c.rect(rect.x, rect.y, rect.w, rect.h, fill=0, stroke=1)

    # Internal horizontal lines
    row_h = rect.h / 6
    for i in range(1, 6):
        y = rect.y + i * row_h
        c.setLineWidth(0.3)
        c.line(rect.x, y, rect.x + rect.w, y)

    cx = rect.x + rect.w / 2
    lx = rect.x + 3 * mm

    # Row 6 (top): Architect firm name
    firm = rng.choice(_ARCHITECT_FIRMS)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(cx, rect.y + 5.5 * row_h + 2, firm)

    # Row 5: Phone + email
    phone = rng.choice(_ARCHITECT_PHONES)
    c.setFont("Helvetica", 5.5)
    email = f"info@{firm.split()[0].lower()}arch.co.uk"
    c.drawCentredString(cx, rect.y + 4.5 * row_h + 2, f"{phone}  |  {email}")

    # Row 4: Drawing title
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(cx, rect.y + 3.5 * row_h + 2, drawing_title)

    # Row 3: Drawing number + revision
    dwg_num = f"{seed % 9999:04d}-{rng.randint(100, 999)}-{rng.choice('ABCDE')}"
    c.setFont("Helvetica", 6)
    c.drawString(lx, rect.y + 2.5 * row_h + 2, f"Dwg No: {dwg_num}")
    c.drawRightString(rect.x + rect.w - 3 * mm, rect.y + 2.5 * row_h + 2, "Rev A")

    # Row 2: Scale + date
    c.setFont("Helvetica", 6)
    c.drawString(lx, rect.y + 1.5 * row_h + 2, f"Scale: {scale_text}")
    c.drawRightString(rect.x + rect.w - 3 * mm, rect.y + 1.5 * row_h + 2, "Date: 03/2026")

    # Row 1 (bottom): Client
    c.setFont("Helvetica", 5.5)
    c.drawString(lx, rect.y + 0.5 * row_h + 2, "Client: Householder")

    c.restoreState()


def draw_legend(
    c: rl_canvas.Canvas,
    rect: Rect,
    entries: list[tuple[str, str, str | None]],
) -> None:
    """Draw a legend box. entries = [(label, line_style, fill_colour_hex | None)]."""
    c.saveState()
    c.setLineWidth(0.5)
    c.rect(rect.x, rect.y, rect.w, rect.h, fill=0, stroke=1)

    c.setFont("Helvetica-Bold", 7)
    c.drawString(rect.x + 3 * mm, rect.y + rect.h - 10, "KEY")

    c.setFont("Helvetica", 6)
    swatch_x = rect.x + 5 * mm
    label_x = rect.x + 25 * mm
    y = rect.y + rect.h - 22

    for label, style, fill_hex in entries:
        # Draw line swatch
        c.saveState()
        if style == "dashed":
            c.setDash(4, 2)
        elif style == "dashdot":
            c.setDash([6, 2, 2, 2])
        c.setLineWidth(1.0)

        if fill_hex:
            from reportlab.lib.colors import HexColor
            c.setFillColor(HexColor(fill_hex))
            c.rect(swatch_x, y - 2, 15 * mm, 5, fill=1, stroke=1)
            c.setFillColor(HexColor("#000000"))
        else:
            c.line(swatch_x, y, swatch_x + 15 * mm, y)

        c.restoreState()

        c.setFont("Helvetica", 6)
        c.drawString(label_x, y - 2, label)
        y -= 12

    c.restoreState()


def draw_copyright_notes(c: rl_canvas.Canvas, rect: Rect) -> None:
    """Draw 4-line copyright/notes block."""
    c.saveState()
    c.setFont("Helvetica", 5)
    y = rect.y + rect.h - 8
    for note in _COPYRIGHT_NOTES:
        c.drawString(rect.x + 2 * mm, y, note)
        y -= 7
    c.restoreState()


def draw_north_arrow(c: rl_canvas.Canvas, rect: Rect) -> None:
    """Draw a north arrow in the given rectangle."""
    cx = rect.x + rect.w / 2
    cy = rect.y + rect.h / 2
    r = 8 * mm
    c.saveState()
    p = c.beginPath()
    p.moveTo(cx, cy + r)
    p.lineTo(cx - r / 2, cy - r / 2)
    p.lineTo(cx + r / 2, cy - r / 2)
    p.close()
    c.setFillGray(0.2)
    c.drawPath(p, fill=1)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(cx, cy + r + 4, "N")
    c.restoreState()


def draw_scale_bar(c: rl_canvas.Canvas, x: float, y: float) -> None:
    """Draw a horizontal scale bar."""
    bar_len = 40 * mm
    c.saveState()
    c.setLineWidth(1.0)
    c.line(x, y, x + bar_len, y)
    c.line(x, y - 2, x, y + 2)
    c.line(x + bar_len / 2, y - 2, x + bar_len / 2, y + 2)
    c.line(x + bar_len, y - 2, x + bar_len, y + 2)
    c.setFont(ANNO_FONT, ANNO_FONT_SIZE)
    c.drawCentredString(x, y + 5, "0")
    c.drawCentredString(x + bar_len / 2, y + 5, "10m")
    c.drawCentredString(x + bar_len, y + 5, "20m")
    c.restoreState()


def draw_dimension_line(
    c: rl_canvas.Canvas,
    x1: float, y1: float,
    x2: float, y2: float,
    label: str,
    offset: float = 8 * mm,
    horizontal: bool = False,
) -> tuple[float, float, float, float]:
    """Draw a dimension line (vertical or horizontal) with ticks and label.

    Returns (text_x, text_y, text_w, text_h) in PDF points for bbox tracking.
    """
    c.saveState()
    c.setLineWidth(0.5)
    c.setDash([])

    if horizontal:
        dim_y = y1 + offset
        c.line(x1, dim_y, x2, dim_y)
        c.line(x1, dim_y - TICK_LEN, x1, dim_y + TICK_LEN)
        c.line(x2, dim_y - TICK_LEN, x2, dim_y + TICK_LEN)
        # Extension lines
        c.setDash(2, 2)
        c.line(x1, y1, x1, dim_y)
        c.line(x2, y1, x2, dim_y)
        c.setDash([])
        # Label centred above
        mid_x = (x1 + x2) / 2
        c.setFont(ANNO_FONT, ANNO_FONT_SIZE)
        c.drawCentredString(mid_x, dim_y + 3, label)
        text_w = len(label) * ANNO_FONT_SIZE * 0.6
        text_x = mid_x - text_w / 2
        text_y = dim_y + 3
    else:
        dim_x = x1 - offset
        c.line(dim_x, y1, dim_x, y2)
        c.line(dim_x - TICK_LEN, y1, dim_x + TICK_LEN, y1)
        c.line(dim_x - TICK_LEN, y2, dim_x + TICK_LEN, y2)
        # Extension lines
        c.setDash(2, 2)
        c.line(x1, y1, dim_x, y1)
        c.line(x1, y2, dim_x, y2)
        c.setDash([])
        # Rotated label
        mid_y = (y1 + y2) / 2
        c.saveState()
        c.translate(dim_x - 3 * mm, mid_y)
        c.rotate(90)
        c.setFont(ANNO_FONT, ANNO_FONT_SIZE)
        c.drawCentredString(0, 0, label)
        c.restoreState()
        text_w = len(label) * ANNO_FONT_SIZE * 0.6
        text_x = dim_x - 3 * mm - text_w / 2
        text_y = mid_y

    c.restoreState()
    text_h = ANNO_FONT_SIZE * 1.2
    return (text_x, text_y, text_w, text_h)


def draw_hatching(
    c: rl_canvas.Canvas,
    x: float, y: float, w: float, h: float,
    spacing: float = 4 * mm,
    angle_deg: float = 45.0,
) -> None:
    """Fill a rectangle with diagonal line hatching."""
    c.saveState()
    c.setLineWidth(0.3)
    c.setStrokeGray(0.5)

    # Clip to the rectangle
    clip_path = c.beginPath()
    clip_path.rect(x, y, w, h)
    c.clipPath(clip_path, stroke=0, fill=0)

    angle = math.radians(angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    # Draw parallel lines across the rectangle
    diag = math.sqrt(w * w + h * h)
    n_lines = int(2 * diag / spacing) + 2
    cx, cy = x + w / 2, y + h / 2

    for i in range(-n_lines // 2, n_lines // 2 + 1):
        offset = i * spacing
        # Line perpendicular offset from centre
        px = cx + offset * cos_a
        py = cy + offset * sin_a
        # Line direction is perpendicular to the offset direction
        dx = -sin_a * diag
        dy = cos_a * diag
        c.line(px - dx, py - dy, px + dx, py + dy)

    c.restoreState()


def get_road_name(rng: random.Random) -> str:
    """Return a random road name."""
    return rng.choice(_ROAD_NAMES)
