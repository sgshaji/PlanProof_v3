"""SitePlanGenerator — generates a top-down site plan PDF using reportlab.

The site plan shows:
  - Property boundary polygon (one of several shape families)
  - Building footprint polygon (inset from boundary)
  - Front setback dimension line + annotation (when front_setback in values_to_place)
  - Rear garden depth dimension line (when rear_garden_depth in values_to_place)
  - Site coverage percentage label (when site_coverage in values_to_place)
  - North arrow (triangle + "N")
  - Scale bar labelled "1:200"
  - Title block: "Site Plan"

Every rendered annotation that corresponds to a Value in values_to_place is
recorded as a PlacedValue with its bounding box converted to pixels at 300 DPI
(canonical coordinate system, top-left origin).

# DESIGN: This generator is intentionally self-contained — it imports no other
# PlanProof rendering helpers except the coord_utils module.  This keeps the
# dependency surface minimal and makes it straightforward to test in isolation.
# reportlab canvas operations are collected into small private methods so the
# main generate() method reads as a sequential composition of layout steps,
# not a wall of graphics calls.

# WHY: Using A3-landscape (420 mm × 297 mm) as the page size matches common
# UK planning drawing convention for site plans, and is large enough that
# dimension annotations are legible without crowding.
"""

from __future__ import annotations

import io
import math
import random
from typing import Final

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

from planproof.datagen.rendering.coord_utils import (
    SCALE_FACTOR,
    pdf_points_to_pixels,
)
from planproof.datagen.rendering.models import GeneratedDocument, PlacedValue
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value
from planproof.schemas.entities import BoundingBox, DocumentType, EntityType

# ---------------------------------------------------------------------------
# Page geometry constants (all in mm, converted to points via reportlab's mm)
# ---------------------------------------------------------------------------

# WHY: Expressing layout constants in millimetres then converting to points
# keeps the numbers human-readable (matching a draftsperson's annotation)
# rather than opaque float literals in PDF points.

# Margins around the drawing area
MARGIN: Final[float] = 20 * mm

# Title block at bottom-right of page
TITLE_BLOCK_W: Final[float] = 80 * mm
TITLE_BLOCK_H: Final[float] = 30 * mm

# Annotation text size
ANNO_FONT_SIZE: Final[float] = 7.0   # points
ANNO_FONT: Final[str] = "Helvetica"

# Dimension line tick half-length (perpendicular to dimension line)
TICK_LEN: Final[float] = 3 * mm

# WHY: Shape family names used for seeded selection.  Each family produces a
# distinct property boundary and building footprint polygon, giving the corpus
# visual diversity that prevents classifiers from overfitting to a single
# rectangular layout.
_SHAPE_FAMILIES: Final[tuple[str, ...]] = (
    "rectangle",
    "l_shaped_property",
    "trapezoidal",
    "l_shaped_building",
    "angled",
)


class SitePlanGenerator:
    """Generates a top-down site plan PDF for a planning application scenario.

    Implements the DocumentGenerator Protocol: accepts a Scenario + DocumentSpec
    and returns a GeneratedDocument with PDF bytes and ground-truth PlacedValues.

    # DESIGN: The generator is a plain class (not a singleton) so that tests can
    # instantiate multiple independent instances without shared state.  There is
    # no __init__ configuration because all layout is driven by the Scenario.
    """

    def generate(
        self,
        scenario: Scenario,
        doc_spec: DocumentSpec,
        seed: int,
    ) -> GeneratedDocument:
        """Render a site plan PDF and return it with ground-truth placement data.

        Args:
            scenario:  Parent scenario supplying Value objects for annotation.
            doc_spec:  Per-document instructions (which attributes to track).
            seed:      Random seed for deterministic shape diversity.

        Returns:
            GeneratedDocument with PDF bytes and one PlacedValue per tracked
            annotation, all bounding boxes in pixels at 300 DPI (top-left origin).
        """
        rng = random.Random(seed)

        # WHY: Build a value lookup keyed by attribute name so we can resolve
        # any attribute in doc_spec.values_to_place in O(1) without scanning.
        value_by_attr: dict[str, Value] = {v.attribute: v for v in scenario.values}

        # Collect PlacedValues as a mutable list during rendering; freeze to
        # tuple at the end to satisfy GeneratedDocument's immutability contract.
        placed: list[PlacedValue] = []

        # --- render to in-memory bytes ---
        buf = io.BytesIO()
        page_w, page_h = landscape(A3)   # width, height in PDF points
        c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))

        self._draw_title_block(c, page_w, page_h)
        self._draw_north_arrow(c, page_w, page_h)
        self._draw_scale_bar(c, page_h)

        # WHY: Select a shape family using the seeded RNG so that different seeds
        # produce different property boundary and building footprint shapes, while
        # the same seed always produces the same shape for reproducibility.
        shape_family = rng.choice(_SHAPE_FAMILIES)

        # WHY: Vary plot dimensions within realistic UK residential ranges so
        # that every seed produces a differently proportioned site plan.
        plot_w_mm = rng.uniform(12.0, 25.0)   # metres (drawn as mm on page at ~1:200)
        plot_d_mm = rng.uniform(20.0, 40.0)   # metres depth

        # Convert to page units: 1 metre → ~5mm on page (approx 1:200 scale)
        scale = 5.0   # mm-per-metre on the page
        boundary_w = plot_w_mm * scale * mm
        boundary_h = plot_d_mm * scale * mm

        # Clamp so boundary fits within drawing area
        max_w = page_w - 2 * MARGIN - TITLE_BLOCK_W - 20 * mm
        max_h = page_h - 2 * MARGIN - 20 * mm
        boundary_w = min(boundary_w, max_w)
        boundary_h = min(boundary_h, max_h)

        # Boundary origin: anchored at bottom-left of drawing area
        bnd_x = MARGIN
        bnd_y = page_h - MARGIN - boundary_h

        # WHY: Vary setbacks using seeded random within realistic ranges.
        # The scenario still provides the *values* for annotations; we only
        # vary the visual position of the building within the plot.
        front_setback_frac = rng.uniform(0.05, 0.15)
        rear_setback_frac = rng.uniform(0.15, 0.35)
        side_setback_frac = rng.uniform(0.08, 0.20)

        bldg_front_offset = boundary_h * front_setback_frac
        bldg_rear_offset = boundary_h * rear_setback_frac
        bldg_left_offset = boundary_w * side_setback_frac
        bldg_right_offset = boundary_w * side_setback_frac

        # Building footprint inside the boundary
        bldg_x = bnd_x + bldg_left_offset
        bldg_y = bnd_y + bldg_rear_offset
        bldg_w = boundary_w - bldg_left_offset - bldg_right_offset
        bldg_h = boundary_h - bldg_front_offset - bldg_rear_offset

        # Draw boundary and building using the selected shape family
        boundary_poly, building_poly = self._compute_polygons(
            rng, shape_family,
            bnd_x, bnd_y, boundary_w, boundary_h,
            bldg_x, bldg_y, bldg_w, bldg_h,
        )

        self._draw_polygon(c, boundary_poly, dashed=True, line_width=1.5)
        self._draw_polygon(c, building_poly, dashed=False, line_width=1.0, fill=True)

        # --- Conditional annotation rendering ---
        # WHY: Dimension annotations reference the actual polygon edges, not the
        # simple rectangle constants from before, so they remain correct regardless
        # of the shape family selected.

        # For dimension lines, use the axis-aligned bounding box of the polygons
        bnd_min_x = min(p[0] for p in boundary_poly)
        bnd_max_x = max(p[0] for p in boundary_poly)
        bnd_min_y = min(p[1] for p in boundary_poly)
        bnd_max_y = max(p[1] for p in boundary_poly)

        bldg_min_x = min(p[0] for p in building_poly)
        bldg_max_x = max(p[0] for p in building_poly)
        bldg_min_y = min(p[1] for p in building_poly)
        bldg_max_y = max(p[1] for p in building_poly)

        if "front_setback" in doc_spec.values_to_place:
            pv = self._draw_front_setback(
                c, page_h,
                bnd_min_x, bnd_max_y,
                bldg_min_x, bldg_max_x, bldg_max_y,
                value_by_attr.get("front_setback"),
            )
            if pv is not None:
                placed.append(pv)

        if "rear_garden_depth" in doc_spec.values_to_place:
            pv = self._draw_rear_garden_depth(
                c, page_h,
                bnd_min_x, bnd_min_y,
                bldg_min_y,
                value_by_attr.get("rear_garden_depth"),
            )
            if pv is not None:
                placed.append(pv)

        if "site_coverage" in doc_spec.values_to_place:
            pv = self._draw_site_coverage(
                c, page_h,
                bnd_min_x, bnd_min_y,
                bnd_max_x - bnd_min_x, bnd_max_y - bnd_min_y,
                value_by_attr.get("site_coverage"),
            )
            if pv is not None:
                placed.append(pv)

        c.save()
        pdf_bytes = buf.getvalue()

        return GeneratedDocument(
            filename=f"{scenario.set_id}_site_plan.pdf",
            doc_type=DocumentType.DRAWING,
            content_bytes=pdf_bytes,
            file_format="pdf",
            placed_values=tuple(placed),
        )

    # ------------------------------------------------------------------
    # Shape family polygon computation
    # ------------------------------------------------------------------

    def _compute_polygons(
        self,
        rng: random.Random,
        shape_family: str,
        bnd_x: float, bnd_y: float, bnd_w: float, bnd_h: float,
        bldg_x: float, bldg_y: float, bldg_w: float, bldg_h: float,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Compute property boundary and building footprint polygons.

        # WHY: Centralising polygon computation in one dispatcher method keeps
        # the generate() method clean and makes it easy to add new shape families
        # without modifying the main rendering flow.

        Returns:
            (boundary_polygon, building_polygon) as lists of (x, y) tuples.
        """
        if shape_family == "l_shaped_property":
            return self._shape_l_property(rng, bnd_x, bnd_y, bnd_w, bnd_h,
                                          bldg_x, bldg_y, bldg_w, bldg_h)
        elif shape_family == "trapezoidal":
            return self._shape_trapezoidal(rng, bnd_x, bnd_y, bnd_w, bnd_h,
                                           bldg_x, bldg_y, bldg_w, bldg_h)
        elif shape_family == "l_shaped_building":
            return self._shape_l_building(rng, bnd_x, bnd_y, bnd_w, bnd_h,
                                          bldg_x, bldg_y, bldg_w, bldg_h)
        elif shape_family == "angled":
            return self._shape_angled(rng, bnd_x, bnd_y, bnd_w, bnd_h,
                                      bldg_x, bldg_y, bldg_w, bldg_h)
        else:
            # WHY: Default to simple rectangle — the original layout.
            return self._shape_rectangle(bnd_x, bnd_y, bnd_w, bnd_h,
                                         bldg_x, bldg_y, bldg_w, bldg_h)

    def _shape_rectangle(
        self,
        bnd_x: float, bnd_y: float, bnd_w: float, bnd_h: float,
        bldg_x: float, bldg_y: float, bldg_w: float, bldg_h: float,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Simple rectangular property and building — the original layout."""
        boundary = [
            (bnd_x, bnd_y),
            (bnd_x + bnd_w, bnd_y),
            (bnd_x + bnd_w, bnd_y + bnd_h),
            (bnd_x, bnd_y + bnd_h),
        ]
        building = [
            (bldg_x, bldg_y),
            (bldg_x + bldg_w, bldg_y),
            (bldg_x + bldg_w, bldg_y + bldg_h),
            (bldg_x, bldg_y + bldg_h),
        ]
        return boundary, building

    def _shape_l_property(
        self,
        rng: random.Random,
        bnd_x: float, bnd_y: float, bnd_w: float, bnd_h: float,
        bldg_x: float, bldg_y: float, bldg_w: float, bldg_h: float,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """L-shaped property: main rectangle with an extension on one side.

        # WHY: L-shaped plots are common in UK suburban areas where properties
        # have been subdivided or have a side garden that wraps around a neighbour.
        """
        ext_w = bnd_w * rng.uniform(0.3, 0.5)
        ext_h = bnd_h * rng.uniform(0.3, 0.5)

        boundary = [
            (bnd_x, bnd_y),
            (bnd_x + bnd_w, bnd_y),
            (bnd_x + bnd_w, bnd_y + bnd_h - ext_h),
            (bnd_x + bnd_w - ext_w, bnd_y + bnd_h - ext_h),
            (bnd_x + bnd_w - ext_w, bnd_y + bnd_h),
            (bnd_x, bnd_y + bnd_h),
        ]
        building = [
            (bldg_x, bldg_y),
            (bldg_x + bldg_w, bldg_y),
            (bldg_x + bldg_w, bldg_y + bldg_h),
            (bldg_x, bldg_y + bldg_h),
        ]
        return boundary, building

    def _shape_trapezoidal(
        self,
        rng: random.Random,
        bnd_x: float, bnd_y: float, bnd_w: float, bnd_h: float,
        bldg_x: float, bldg_y: float, bldg_w: float, bldg_h: float,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Trapezoidal property: front wider or narrower than rear.

        # WHY: Tapered plots arise from cul-de-sac layouts and irregular land
        # parcels.  The front (top in PDF coords) and rear boundaries differ in
        # width, creating a trapezoid.
        """
        taper = bnd_w * rng.uniform(0.05, 0.15)
        if rng.random() < 0.5:
            # Front wider than rear
            boundary = [
                (bnd_x + taper, bnd_y),
                (bnd_x + bnd_w - taper, bnd_y),
                (bnd_x + bnd_w, bnd_y + bnd_h),
                (bnd_x, bnd_y + bnd_h),
            ]
        else:
            # Rear wider than front
            boundary = [
                (bnd_x, bnd_y),
                (bnd_x + bnd_w, bnd_y),
                (bnd_x + bnd_w - taper, bnd_y + bnd_h),
                (bnd_x + taper, bnd_y + bnd_h),
            ]
        building = [
            (bldg_x, bldg_y),
            (bldg_x + bldg_w, bldg_y),
            (bldg_x + bldg_w, bldg_y + bldg_h),
            (bldg_x, bldg_y + bldg_h),
        ]
        return boundary, building

    def _shape_l_building(
        self,
        rng: random.Random,
        bnd_x: float, bnd_y: float, bnd_w: float, bnd_h: float,
        bldg_x: float, bldg_y: float, bldg_w: float, bldg_h: float,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Rectangular plot with an L-shaped building (rear extension).

        # WHY: Single-storey rear extensions are the most common permitted
        # development in the UK, making this footprint shape realistic for
        # planning applications.
        """
        boundary = [
            (bnd_x, bnd_y),
            (bnd_x + bnd_w, bnd_y),
            (bnd_x + bnd_w, bnd_y + bnd_h),
            (bnd_x, bnd_y + bnd_h),
        ]
        # L-shaped building: main block + extension at the rear
        ext_w = bldg_w * rng.uniform(0.3, 0.5)
        ext_h = bldg_h * rng.uniform(0.2, 0.35)
        building = [
            (bldg_x, bldg_y),
            (bldg_x + ext_w, bldg_y),
            (bldg_x + ext_w, bldg_y + ext_h),
            (bldg_x + bldg_w, bldg_y + ext_h),
            (bldg_x + bldg_w, bldg_y + bldg_h),
            (bldg_x, bldg_y + bldg_h),
        ]
        return boundary, building

    def _shape_angled(
        self,
        rng: random.Random,
        bnd_x: float, bnd_y: float, bnd_w: float, bnd_h: float,
        bldg_x: float, bldg_y: float, bldg_w: float, bldg_h: float,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Rectangular property rotated 5-15 degrees from axis.

        # WHY: Many real plots are not axis-aligned — they follow road curves
        # or historic field boundaries.  Rotating the rectangle tests that
        # downstream processors handle non-orthogonal geometry.
        """
        angle_deg = rng.uniform(5.0, 15.0)
        if rng.random() < 0.5:
            angle_deg = -angle_deg
        angle_rad = math.radians(angle_deg)

        # Rotate boundary rectangle around its centre
        cx_bnd = bnd_x + bnd_w / 2
        cy_bnd = bnd_y + bnd_h / 2

        def _rotate(
            px: float, py: float, cx: float, cy: float, angle: float,
        ) -> tuple[float, float]:
            dx, dy = px - cx, py - cy
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            return (cx + dx * cos_a - dy * sin_a,
                    cy + dx * sin_a + dy * cos_a)

        boundary_corners = [
            (bnd_x, bnd_y),
            (bnd_x + bnd_w, bnd_y),
            (bnd_x + bnd_w, bnd_y + bnd_h),
            (bnd_x, bnd_y + bnd_h),
        ]
        boundary = [_rotate(px, py, cx_bnd, cy_bnd, angle_rad)
                    for px, py in boundary_corners]

        # Rotate building around the same centre so it stays inside the plot
        building_corners = [
            (bldg_x, bldg_y),
            (bldg_x + bldg_w, bldg_y),
            (bldg_x + bldg_w, bldg_y + bldg_h),
            (bldg_x, bldg_y + bldg_h),
        ]
        building = [_rotate(px, py, cx_bnd, cy_bnd, angle_rad)
                    for px, py in building_corners]

        return boundary, building

    # ------------------------------------------------------------------
    # Private drawing helpers
    # ------------------------------------------------------------------

    def _draw_polygon(
        self,
        c: rl_canvas.Canvas,
        points: list[tuple[float, float]],
        *,
        dashed: bool = False,
        line_width: float = 1.0,
        fill: bool = False,
    ) -> None:
        """Draw a closed polygon from a list of (x, y) vertices.

        # WHY: A general polygon drawing method replaces the old _draw_boundary
        # and _draw_building methods, supporting all shape families uniformly.
        """
        if not points:
            return
        c.saveState()
        c.setLineWidth(line_width)
        if dashed:
            c.setDash(6, 3)
        if fill:
            c.setFillGray(0.80)
        p = c.beginPath()
        p.moveTo(points[0][0], points[0][1])
        for px, py in points[1:]:
            p.lineTo(px, py)
        p.close()
        c.drawPath(p, fill=1 if fill else 0, stroke=1)
        c.restoreState()

    def _draw_title_block(
        self, c: rl_canvas.Canvas, page_w: float, page_h: float
    ) -> None:
        """Draw the title block in the bottom-right corner.

        # WHY: A title block with "Site Plan" satisfies minimum drawing standards
        # and gives the OCR/VLM a signal that this is a site plan document type.
        """
        tb_x = page_w - MARGIN - TITLE_BLOCK_W
        tb_y = MARGIN / 2
        c.saveState()
        c.setLineWidth(0.5)
        c.rect(tb_x, tb_y, TITLE_BLOCK_W, TITLE_BLOCK_H)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(
            tb_x + TITLE_BLOCK_W / 2,
            tb_y + TITLE_BLOCK_H / 2 + 5,
            "Site Plan",
        )
        c.setFont("Helvetica", 7)
        c.drawCentredString(
            tb_x + TITLE_BLOCK_W / 2,
            tb_y + TITLE_BLOCK_H / 2 - 5,
            "Scale 1:200",
        )
        c.restoreState()

    def _draw_north_arrow(
        self, c: rl_canvas.Canvas, page_w: float, page_h: float
    ) -> None:
        """Draw a simple north arrow (triangle + N label) near the top-right.

        # WHY: A north arrow is mandatory on site plans submitted to UK local
        # planning authorities.  Including it makes the synthetic document
        # realistic enough that classifiers trained on it generalise to real docs.
        """
        cx = page_w - MARGIN - TITLE_BLOCK_W / 2
        cy = page_h - MARGIN - 20 * mm
        r = 8 * mm
        c.saveState()
        # Triangle pointing up
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

    def _draw_scale_bar(self, c: rl_canvas.Canvas, page_h: float) -> None:
        """Draw a simple scale bar below the north arrow area.

        # WHY: A graphical scale bar lets the reader verify scale independently
        # of reproduction; including it is standard practice for planning drawings.
        """
        bar_x = MARGIN
        bar_y = MARGIN / 2 + TITLE_BLOCK_H + 5 * mm
        bar_len = 40 * mm
        c.saveState()
        c.setLineWidth(1.0)
        c.line(bar_x, bar_y, bar_x + bar_len, bar_y)
        c.line(bar_x, bar_y - 2, bar_x, bar_y + 2)
        c.line(bar_x + bar_len / 2, bar_y - 2, bar_x + bar_len / 2, bar_y + 2)
        c.line(bar_x + bar_len, bar_y - 2, bar_x + bar_len, bar_y + 2)
        c.setFont(ANNO_FONT, ANNO_FONT_SIZE)
        c.drawCentredString(bar_x + bar_len / 4, bar_y + 3, "0")
        c.drawCentredString(bar_x + bar_len / 2, bar_y + 3, "10m")
        c.drawCentredString(bar_x + bar_len * 3 / 4, bar_y + 3, "20m")
        c.restoreState()

    def _draw_front_setback(
        self,
        c: rl_canvas.Canvas,
        page_h: float,
        bnd_x: float,
        bnd_front_y: float,
        bldg_min_x: float,
        bldg_max_x: float,
        bldg_front_y: float,
        value: Value | None,
    ) -> PlacedValue | None:
        """Draw front setback dimension line and return its PlacedValue.

        The dimension line runs vertically between the front boundary edge and
        the front (top) face of the building, centred on the building width.

        # WHY: The front setback is drawn as a classic architectural dimension:
        # two extension lines + a dimension line with ticks + a text annotation.

        Returns:
            PlacedValue with a pixel bounding box, or None if value is missing.
        """
        if value is None:
            return None

        # Guard: the building front must be below the boundary front in PDF y.
        if bnd_front_y <= bldg_front_y:
            return None

        # Horizontal position: centre on the building width
        dim_x = (bldg_min_x + bldg_max_x) / 2

        self._draw_dimension_line_vertical(
            c, dim_x, bldg_front_y, bnd_front_y, value.display_text
        )

        # Annotation bounding box
        text_x_pt = dim_x + 2 * mm
        text_y_pt = (bldg_front_y + bnd_front_y) / 2
        text_w_pt = len(value.display_text) * ANNO_FONT_SIZE * 0.6
        text_h_pt = ANNO_FONT_SIZE * 1.2

        bb = _make_bounding_box(text_x_pt, text_y_pt, text_w_pt, text_h_pt, page_h)

        return PlacedValue(
            attribute=value.attribute,
            value=value.value,
            text_rendered=value.display_text,
            page=1,
            bounding_box=bb,
            entity_type=EntityType.MEASUREMENT,
        )

    def _draw_rear_garden_depth(
        self,
        c: rl_canvas.Canvas,
        page_h: float,
        bnd_x: float,
        bnd_rear_y: float,
        bldg_rear_y: float,
        value: Value | None,
    ) -> PlacedValue | None:
        """Draw rear garden depth dimension line and return its PlacedValue.

        # WHY: Rear garden depth is a critical planning metric (usually must be
        # >= 10 m for residential extensions).

        Returns:
            PlacedValue with pixel bounding box, or None if value is missing.
        """
        if value is None:
            return None

        dim_x = bnd_x - 8 * mm

        if bldg_rear_y <= bnd_rear_y:
            return None

        self._draw_dimension_line_vertical(
            c, dim_x, bnd_rear_y, bldg_rear_y, value.display_text
        )

        # WHY: Clamp text_x_pt to a small positive offset so the bounding box
        # never falls off the left edge of the page, which would produce a
        # negative x coordinate in the ground-truth bounding box.
        text_w_candidate = len(value.display_text) * ANNO_FONT_SIZE * 0.6
        text_x_pt = max(2.0, dim_x - text_w_candidate - 2 * mm)
        text_y_pt = (bnd_rear_y + bldg_rear_y) / 2
        text_w_pt = len(value.display_text) * ANNO_FONT_SIZE * 0.6
        text_h_pt = ANNO_FONT_SIZE * 1.2

        bb = _make_bounding_box(text_x_pt, text_y_pt, text_w_pt, text_h_pt, page_h)

        return PlacedValue(
            attribute=value.attribute,
            value=value.value,
            text_rendered=value.display_text,
            page=1,
            bounding_box=bb,
            entity_type=EntityType.MEASUREMENT,
        )

    def _draw_site_coverage(
        self,
        c: rl_canvas.Canvas,
        page_h: float,
        bnd_x: float,
        bnd_y: float,
        bnd_w: float,
        bnd_h: float,
        value: Value | None,
    ) -> PlacedValue | None:
        """Draw site coverage percentage as a label inside the boundary.

        # WHY: Site coverage is a ratio (not a dimension), so it is rendered as
        # a plain annotation label rather than a dimension line.

        Returns:
            PlacedValue with pixel bounding box, or None if value is missing.
        """
        if value is None:
            return None

        label = f"Site Coverage: {value.display_text}"
        # Place in the lower-right of the boundary area
        text_x_pt = bnd_x + bnd_w - 50 * mm
        text_y_pt = bnd_y + 8 * mm

        c.saveState()
        c.setFont(ANNO_FONT, ANNO_FONT_SIZE)
        c.drawString(text_x_pt, text_y_pt, label)
        c.restoreState()

        text_w_pt = len(label) * ANNO_FONT_SIZE * 0.6
        text_h_pt = ANNO_FONT_SIZE * 1.2

        bb = _make_bounding_box(text_x_pt, text_y_pt, text_w_pt, text_h_pt, page_h)

        return PlacedValue(
            attribute=value.attribute,
            value=value.value,
            text_rendered=value.display_text,
            page=1,
            bounding_box=bb,
            entity_type=EntityType.MEASUREMENT,
        )

    def _draw_dimension_line_vertical(
        self,
        c: rl_canvas.Canvas,
        x: float,
        y_low: float,
        y_high: float,
        label: str,
    ) -> None:
        """Draw a vertical dimension line between y_low and y_high at x.

        Includes arrow ticks at each end and a centred text annotation.

        # WHY: A helper method for dimension lines avoids repeating the same
        # four-line pattern for every annotated value.
        """
        c.saveState()
        c.setLineWidth(0.5)
        c.setDash([])   # solid line for dimension lines

        # Vertical dimension line
        c.line(x, y_low, x, y_high)

        # Ticks at both ends (perpendicular to line = horizontal)
        c.line(x - TICK_LEN, y_low, x + TICK_LEN, y_low)
        c.line(x - TICK_LEN, y_high, x + TICK_LEN, y_high)

        # Extension lines from dimension line to the measured geometry
        ext_offset = 2 * mm
        c.setDash(2, 2)
        c.line(x, y_low - ext_offset, x, y_low)
        c.line(x, y_high, x, y_high + ext_offset)

        # Annotation text at midpoint, rotated 90° to read along the line
        mid_y = (y_low + y_high) / 2
        c.saveState()
        c.translate(x + 2 * mm, mid_y)
        c.rotate(90)
        c.setFont(ANNO_FONT, ANNO_FONT_SIZE)
        c.setDash([])
        c.drawCentredString(0, 0, label)
        c.restoreState()

        c.restoreState()


# ---------------------------------------------------------------------------
# Module-level coordinate helper
# ---------------------------------------------------------------------------

def _make_bounding_box(
    x_pt: float,
    y_pt: float,
    w_pt: float,
    h_pt: float,
    page_height_pt: float,
) -> BoundingBox:
    """Convert a PDF-point rectangle to a pixel BoundingBox (top-left origin).

    Args:
        x_pt:           Left edge of the text/annotation in PDF points.
        y_pt:           Bottom-left Y of the text baseline in PDF points.
        w_pt:           Width of the bounding rectangle in PDF points.
        h_pt:           Height of the bounding rectangle in PDF points.
        page_height_pt: Total page height in PDF points (for Y-axis flip).

    Returns:
        BoundingBox in pixels at CANONICAL_DPI=300, origin top-left, page=1.

    # WHY: Converting at the point of recording (rather than later) keeps the
    # coordinate system concerns inside this module.
    """
    top_left = pdf_points_to_pixels(x_pt, y_pt + h_pt, page_height_pt)

    w_px = w_pt * SCALE_FACTOR
    h_px = h_pt * SCALE_FACTOR

    return BoundingBox(
        x=top_left.x,
        y=top_left.y,
        width=w_px,
        height=h_px,
        page=1,
    )
