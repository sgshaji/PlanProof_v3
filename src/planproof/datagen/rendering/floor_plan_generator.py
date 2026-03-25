"""FloorPlanGenerator — generates a room-layout floor plan PDF using reportlab.

The floor plan shows:
  - External wall polygon (the building outline — one of several layout families)
  - Internal room subdivisions with varied arrangements
  - Room dimension annotations (width x depth)
  - Door indicators (arcs in room corners)
  - Window indicators (double lines on external walls)
  - Title block: "Ground Floor Plan" or "First Floor Plan" (chosen by seed)

The floor plan is primarily structural context.  Any Values in values_to_place
that match known area attributes (building_footprint_area, ground_floor_area)
are rendered as annotation labels and tracked as PlacedValues.  Unrecognised
attributes are silently skipped.

# DESIGN: The generator shares no state with SitePlanGenerator.  Room layout
# geometry is computed deterministically from the seed so that the same seed
# always produces the same PDF bytes — critical for reproducible corpus
# generation in parallel pipelines.

# WHY: Using A3-landscape matches the site plan convention and ensures the two
# drawings are visually consistent when placed side-by-side in a planning pack.
"""

from __future__ import annotations

import io
import random
from collections.abc import Callable
from dataclasses import dataclass
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
# Layout constants
# ---------------------------------------------------------------------------

MARGIN: Final[float] = 20 * mm

# Wall thickness (solid lines drawn as pairs)
WALL_T: Final[float] = 2.0   # PDF points

# Door arc radius
DOOR_R: Final[float] = 8 * mm

# Window double-line gap
WIN_GAP: Final[float] = 2 * mm
WIN_LEN: Final[float] = 20 * mm

# Annotation typography
ANNO_FONT: Final[str] = "Helvetica"
ANNO_FONT_SIZE: Final[float] = 7.0   # points

# Title block dimensions
TITLE_BLOCK_W: Final[float] = 80 * mm
TITLE_BLOCK_H: Final[float] = 25 * mm

# Known area attribute names this generator will track
_TRACKED_AREA_ATTRS: Final[frozenset[str]] = frozenset({
    "building_footprint_area",
    "ground_floor_area",
})

# Title options driven by seed parity
_FLOOR_TITLES: Final[tuple[str, ...]] = (
    "Ground Floor Plan",
    "First Floor Plan",
)

# WHY: Layout family names used for seeded selection.  Each family produces a
# distinct room arrangement and external wall shape, giving the corpus visual
# diversity that prevents classifiers from overfitting to one floor plan layout.
_LAYOUT_FAMILIES: Final[tuple[str, ...]] = (
    "simple_rectangle",
    "l_shaped",
    "open_plan",
    "two_storey",
    "bay_window",
)


@dataclass
class _Room:
    """Internal record describing one room's geometry (in PDF points).

    # DESIGN: A lightweight dataclass rather than a named tuple so that we can
    # attach a label string alongside the coordinates.  Room objects are short-
    # lived and never escape the generator's generate() call.
    """
    x: float    # left edge (PDF points)
    y: float    # bottom edge (PDF points)
    w: float    # width (PDF points)
    h: float    # height (PDF points)
    label: str  # e.g. "Living Room"


class FloorPlanGenerator:
    """Generates a room-layout floor plan PDF for a planning application scenario.

    Implements the DocumentGenerator Protocol.

    # DESIGN: Room layout is computed from a seeded RNG so that different seeds
    # produce visually distinct room proportions while remaining deterministic.
    # This prevents every scenario in the corpus from looking identical, which
    # would make the training data less diverse.
    """

    def generate(
        self,
        scenario: Scenario,
        doc_spec: DocumentSpec,
        seed: int,
    ) -> GeneratedDocument:
        """Render a floor plan PDF and return it with ground-truth placement data.

        Args:
            scenario:  Parent scenario supplying Value objects for annotation.
            doc_spec:  Per-document instructions (which attributes to track).
            seed:      Random seed for deterministic room-layout variation.

        Returns:
            GeneratedDocument with PDF bytes and one PlacedValue per tracked
            annotation, all bounding boxes in pixels at 300 DPI (top-left origin).
        """
        rng = random.Random(seed)

        # WHY: Build lookup by attribute name so tracked values resolve in O(1).
        value_by_attr: dict[str, Value] = {v.attribute: v for v in scenario.values}

        placed: list[PlacedValue] = []

        buf = io.BytesIO()
        page_w, page_h = landscape(A3)
        c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))

        # Choose title deterministically: seed parity picks Ground vs First floor.
        title = _FLOOR_TITLES[seed % len(_FLOOR_TITLES)]
        self._draw_title_block(c, page_w, page_h, title)

        # WHY: Vary external wall dimensions using seeded random so floor plans
        # have different proportions across the corpus.
        ext_w = rng.uniform(120, 200) * mm
        ext_h = rng.uniform(80, 150) * mm

        # Clamp to page
        max_w = page_w - 2 * MARGIN - TITLE_BLOCK_W - 20 * mm
        max_h = page_h - 2 * MARGIN - 20 * mm
        ext_w = min(ext_w, max_w)
        ext_h = min(ext_h, max_h)

        # External wall origin: top-left quadrant of page
        ext_x = MARGIN
        ext_y = page_h - MARGIN - ext_h

        # WHY: Select a layout family using the seeded RNG so different seeds
        # produce different room arrangements and external wall shapes.
        layout_family = rng.choice(_LAYOUT_FAMILIES)

        # Compute rooms and external wall polygon based on the layout family
        rooms, ext_polygon, extra_draw = self._compute_layout(
            rng, layout_family, ext_x, ext_y, ext_w, ext_h,
        )

        # Draw external walls as polygon
        self._draw_external_polygon(c, ext_polygon)

        self._draw_internal_walls(c, rooms)
        self._draw_windows_on_polygon(c, ext_polygon, ext_x, ext_y, ext_w, ext_h)
        self._draw_doors(c, rooms)
        self._draw_room_labels(c, rooms)

        # Draw any extra elements (staircase symbol, bay window detail, etc.)
        if extra_draw is not None:
            extra_draw(c)

        # --- Conditional annotation rendering for tracked area values ---
        for attr in doc_spec.values_to_place:
            if attr not in _TRACKED_AREA_ATTRS:
                continue
            val = value_by_attr.get(attr)
            if val is None:
                continue
            pv = self._draw_area_annotation(
                c, page_h, ext_x, ext_y, ext_w, ext_h, val, len(placed)
            )
            if pv is not None:
                placed.append(pv)

        c.save()
        pdf_bytes = buf.getvalue()

        return GeneratedDocument(
            filename=f"{scenario.set_id}_floor_plan.pdf",
            doc_type=DocumentType.DRAWING,
            content_bytes=pdf_bytes,
            file_format="pdf",
            placed_values=tuple(placed),
        )

    # ------------------------------------------------------------------
    # Layout family computation
    # ------------------------------------------------------------------

    def _compute_layout(
        self,
        rng: random.Random,
        layout_family: str,
        ext_x: float,
        ext_y: float,
        ext_w: float,
        ext_h: float,
    ) -> tuple[
        list[_Room],
        list[tuple[float, float]],
        None | Callable[[rl_canvas.Canvas], None],
    ]:
        """Compute rooms, external wall polygon, and optional extra draw callback.

        # WHY: Centralising layout computation keeps the generate() method clean
        # and makes it easy to add new layout families.

        Returns:
            (rooms, ext_polygon, extra_draw_callback_or_None)
        """
        if layout_family == "l_shaped":
            return self._layout_l_shaped(rng, ext_x, ext_y, ext_w, ext_h)
        elif layout_family == "open_plan":
            return self._layout_open_plan(rng, ext_x, ext_y, ext_w, ext_h)
        elif layout_family == "two_storey":
            return self._layout_two_storey(rng, ext_x, ext_y, ext_w, ext_h)
        elif layout_family == "bay_window":
            return self._layout_bay_window(rng, ext_x, ext_y, ext_w, ext_h)
        else:
            # WHY: Default to simple_rectangle — the original 2-3 room layout.
            return self._layout_simple_rectangle(rng, ext_x, ext_y, ext_w, ext_h)

    def _layout_simple_rectangle(
        self,
        rng: random.Random,
        ext_x: float, ext_y: float, ext_w: float, ext_h: float,
    ) -> tuple[list[_Room], list[tuple[float, float]], None]:
        """Simple rectangular outline with 2-3 rooms in a row (original layout).

        # WHY: This is the baseline layout, preserved for backward compatibility
        # and as the simplest variant in the diversity mix.
        """
        polygon = [
            (ext_x, ext_y),
            (ext_x + ext_w, ext_y),
            (ext_x + ext_w, ext_y + ext_h),
            (ext_x, ext_y + ext_h),
        ]
        rooms = self._make_rooms_subdivide(rng, ext_x, ext_y, ext_w, ext_h)
        return rooms, polygon, None

    def _layout_l_shaped(
        self,
        rng: random.Random,
        ext_x: float, ext_y: float, ext_w: float, ext_h: float,
    ) -> tuple[list[_Room], list[tuple[float, float]], None]:
        """L-shaped floor plan: main block + extension.

        # WHY: L-shaped floor plans arise from single-storey extensions at the
        # rear or side of a building — the most common UK domestic extension type.
        """
        # Extension dimensions as fraction of the main block
        ext_frac_w = rng.uniform(0.35, 0.55)
        ext_frac_h = rng.uniform(0.3, 0.45)
        ext_part_w = ext_w * ext_frac_w
        ext_part_h = ext_h * ext_frac_h

        # L-shape: main rectangle + extension at bottom-right
        polygon = [
            (ext_x, ext_y),
            (ext_x + ext_w, ext_y),
            (ext_x + ext_w, ext_y + ext_h - ext_part_h),
            (ext_x + ext_part_w, ext_y + ext_h - ext_part_h),
            (ext_x + ext_part_w, ext_y + ext_h),
            (ext_x, ext_y + ext_h),
        ]

        # Rooms: main block gets 2 rooms, extension gets 1
        cut = ext_w * rng.uniform(0.4, 0.6)
        main_h = ext_h - ext_part_h
        rooms = [
            _Room(ext_x, ext_y, cut, main_h, "Living Room"),
            _Room(ext_x + cut, ext_y, ext_w - cut, main_h, "Kitchen"),
            _Room(ext_x, ext_y + main_h, ext_part_w, ext_part_h, "Extension"),
        ]
        return rooms, polygon, None

    def _layout_open_plan(
        self,
        rng: random.Random,
        ext_x: float, ext_y: float, ext_w: float, ext_h: float,
    ) -> tuple[list[_Room], list[tuple[float, float]], None]:
        """Open plan: large living/kitchen with a small utility room.

        # WHY: Open-plan layouts are increasingly common in modern residential
        # designs and differ visually from traditional subdivided layouts.
        """
        polygon = [
            (ext_x, ext_y),
            (ext_x + ext_w, ext_y),
            (ext_x + ext_w, ext_y + ext_h),
            (ext_x, ext_y + ext_h),
        ]
        # Small utility room in one corner
        util_w = ext_w * rng.uniform(0.2, 0.3)
        util_h = ext_h * rng.uniform(0.25, 0.4)
        rooms = [
            _Room(ext_x, ext_y, ext_w, ext_h - util_h, "Living / Kitchen"),
            _Room(ext_x, ext_y + ext_h - util_h, util_w, util_h, "Utility"),
        ]
        return rooms, polygon, None

    def _layout_two_storey(
        self,
        rng: random.Random,
        ext_x: float, ext_y: float, ext_w: float, ext_h: float,
    ) -> tuple[
        list[_Room],
        list[tuple[float, float]],
        Callable[[rl_canvas.Canvas], None] | None,
    ]:
        """Simple rectangle with a staircase symbol added.

        # WHY: A staircase symbol signals to VLM/OCR classifiers that this is a
        # multi-storey building, adding meaningful structural variety.
        """
        polygon = [
            (ext_x, ext_y),
            (ext_x + ext_w, ext_y),
            (ext_x + ext_w, ext_y + ext_h),
            (ext_x, ext_y + ext_h),
        ]
        rooms = self._make_rooms_subdivide(rng, ext_x, ext_y, ext_w, ext_h)

        # Place staircase symbol in one of the rooms (last room)
        stair_room = rooms[-1]

        def _draw_staircase(c: rl_canvas.Canvas) -> None:
            """Draw a staircase symbol (parallel lines) in the stair room.

            # WHY: The standard architectural convention for stairs is a series
            # of parallel lines with an arrow indicating the direction of ascent.
            """
            c.saveState()
            c.setLineWidth(0.5)
            sx = stair_room.x + stair_room.w * 0.2
            sy = stair_room.y + stair_room.h * 0.2
            sw = stair_room.w * 0.6
            sh = stair_room.h * 0.6
            n_treads = 8
            for i in range(n_treads + 1):
                y = sy + sh * i / n_treads
                c.line(sx, y, sx + sw, y)
            # Arrow pointing up
            arrow_x = sx + sw / 2
            arrow_y_top = sy + sh
            c.line(arrow_x, sy, arrow_x, arrow_y_top)
            c.line(arrow_x - 3 * mm, arrow_y_top - 3 * mm,
                   arrow_x, arrow_y_top)
            c.line(arrow_x + 3 * mm, arrow_y_top - 3 * mm,
                   arrow_x, arrow_y_top)
            # Label
            c.setFont(ANNO_FONT, ANNO_FONT_SIZE - 1)
            c.drawCentredString(sx + sw / 2, sy - ANNO_FONT_SIZE, "UP")
            c.restoreState()

        return rooms, polygon, _draw_staircase

    def _layout_bay_window(
        self,
        rng: random.Random,
        ext_x: float, ext_y: float, ext_w: float, ext_h: float,
    ) -> tuple[list[_Room], list[tuple[float, float]], None]:
        """One external wall has a triangular bay window projection.

        # WHY: Bay windows are a distinctive architectural feature of Victorian
        # and Edwardian UK housing stock, making this variant realistic for
        # planning applications in conservation areas.
        """
        # Bay projection on the bottom wall (front of house)
        bay_w = ext_w * rng.uniform(0.2, 0.35)
        bay_d = ext_h * rng.uniform(0.08, 0.15)
        bay_cx = ext_x + ext_w * rng.uniform(0.3, 0.7)

        polygon = [
            (ext_x, ext_y),
            (bay_cx - bay_w / 2, ext_y),
            (bay_cx, ext_y - bay_d),        # Bay projection apex
            (bay_cx + bay_w / 2, ext_y),
            (ext_x + ext_w, ext_y),
            (ext_x + ext_w, ext_y + ext_h),
            (ext_x, ext_y + ext_h),
        ]

        rooms = self._make_rooms_subdivide(rng, ext_x, ext_y, ext_w, ext_h)
        return rooms, polygon, None

    # ------------------------------------------------------------------
    # Room subdivision helper
    # ------------------------------------------------------------------

    def _make_rooms_subdivide(
        self,
        rng: random.Random,
        ext_x: float,
        ext_y: float,
        ext_w: float,
        ext_h: float,
    ) -> list[_Room]:
        """Subdivide the external wall rectangle into 2-3 rooms.

        The subdivision uses a single vertical or horizontal cut, optionally
        followed by a second cut — producing 2 or 3 rooms respectively.

        # DESIGN: The cut positions are randomised within a sensible range so
        # that no two seeds produce identical proportions.

        Returns:
            List of _Room objects covering the full external footprint.
        """
        rooms: list[_Room] = []

        # First cut: always vertical, splitting at 40%-60% of width
        cut1 = ext_w * rng.uniform(0.40, 0.60)
        rooms.append(_Room(ext_x, ext_y, cut1, ext_h, "Living Room"))
        rooms.append(_Room(ext_x + cut1, ext_y, ext_w - cut1, ext_h, "Kitchen"))

        # Optional second cut: horizontal, splitting the right room
        if rng.random() < 0.5:
            cut2 = ext_h * rng.uniform(0.40, 0.60)
            right_x = ext_x + cut1
            right_w = ext_w - cut1
            rooms.pop()
            rooms.append(_Room(right_x, ext_y + cut2, right_w, ext_h - cut2, "Kitchen"))
            rooms.append(_Room(right_x, ext_y, right_w, cut2, "Utility"))

        return rooms

    # ------------------------------------------------------------------
    # Private drawing helpers
    # ------------------------------------------------------------------

    def _draw_external_polygon(
        self,
        c: rl_canvas.Canvas,
        polygon: list[tuple[float, float]],
    ) -> None:
        """Draw the external building outline as a thick polygon.

        # WHY: Using a polygon path instead of rect() supports non-rectangular
        # shapes like L-plans and bay window projections.
        """
        if not polygon:
            return
        c.saveState()
        c.setLineWidth(WALL_T)
        p = c.beginPath()
        p.moveTo(polygon[0][0], polygon[0][1])
        for px, py in polygon[1:]:
            p.lineTo(px, py)
        p.close()
        c.drawPath(p, fill=0, stroke=1)
        c.restoreState()

    def _draw_internal_walls(
        self, c: rl_canvas.Canvas, rooms: list[_Room]
    ) -> None:
        """Draw internal wall lines between adjacent rooms.

        # WHY: Drawing internal walls as thin lines (not filled rectangles)
        # keeps the room areas clear for labels and matches architectural
        # drawing convention for partition walls.
        """
        c.saveState()
        c.setLineWidth(0.75)

        dividers: set[tuple[float, float, float, float]] = set()
        for room in rooms:
            right_x = room.x + room.w
            top_y = room.y + room.h
            for other in rooms:
                if abs(other.x - right_x) < 0.5:
                    dividers.add((right_x, room.y, right_x, top_y))
            for other in rooms:
                if abs(other.y - top_y) < 0.5:
                    dividers.add((room.x, top_y, room.x + room.w, top_y))

        for x1, y1, x2, y2 in dividers:
            c.line(x1, y1, x2, y2)

        c.restoreState()

    def _draw_windows_on_polygon(
        self,
        c: rl_canvas.Canvas,
        polygon: list[tuple[float, float]],
        ext_x: float, ext_y: float, ext_w: float, ext_h: float,
    ) -> None:
        """Draw double-line window indicators on the external walls.

        # WHY: Window indicators (two parallel lines interrupting the wall line)
        # are a standard architectural drawing convention.  We place them using
        # the axis-aligned bounding box for simplicity, which works for all
        # layout families.
        """
        c.saveState()
        c.setLineWidth(0.5)

        # Front wall (bottom edge): one window centred
        win_x = ext_x + ext_w / 2 - WIN_LEN / 2
        win_y = ext_y
        c.line(win_x, win_y - WIN_GAP, win_x + WIN_LEN, win_y - WIN_GAP)
        c.line(win_x, win_y + WIN_GAP, win_x + WIN_LEN, win_y + WIN_GAP)

        # Rear wall (top edge): one window centred
        win_y2 = ext_y + ext_h
        c.line(win_x, win_y2 - WIN_GAP, win_x + WIN_LEN, win_y2 - WIN_GAP)
        c.line(win_x, win_y2 + WIN_GAP, win_x + WIN_LEN, win_y2 + WIN_GAP)

        c.restoreState()

    def _draw_doors(self, c: rl_canvas.Canvas, rooms: list[_Room]) -> None:
        """Draw a door arc in the bottom-left corner of each room.

        # WHY: Door arcs indicate the swing radius of a hinged door.  They give
        # the floor plan visual complexity.
        """
        c.saveState()
        c.setLineWidth(0.5)
        for room in rooms:
            door_x = room.x + DOOR_R
            door_y = room.y
            c.line(door_x, door_y, door_x + DOOR_R, door_y)
            c.arc(
                room.x,
                room.y,
                room.x + DOOR_R,
                room.y + DOOR_R,
                startAng=0,
                extent=90,
            )
        c.restoreState()

    def _draw_room_labels(self, c: rl_canvas.Canvas, rooms: list[_Room]) -> None:
        """Draw the room name centred in each room rectangle."""
        c.saveState()
        c.setFont(ANNO_FONT, ANNO_FONT_SIZE)
        for room in rooms:
            cx = room.x + room.w / 2
            cy = room.y + room.h / 2
            c.drawCentredString(cx, cy, room.label)
        c.restoreState()

    def _draw_title_block(
        self,
        c: rl_canvas.Canvas,
        page_w: float,
        page_h: float,
        title: str,
    ) -> None:
        """Draw the title block in the bottom-right corner with the given title."""
        tb_x = page_w - MARGIN - TITLE_BLOCK_W
        tb_y = MARGIN / 2
        c.saveState()
        c.setLineWidth(0.5)
        c.rect(tb_x, tb_y, TITLE_BLOCK_W, TITLE_BLOCK_H)
        c.setFont("Helvetica-Bold", 9)
        cx = tb_x + TITLE_BLOCK_W / 2
        cy = tb_y + TITLE_BLOCK_H / 2
        c.drawCentredString(cx, cy + 4, title)
        c.setFont("Helvetica", 7)
        c.drawCentredString(cx, cy - 6, "NTS")
        c.restoreState()

    def _draw_area_annotation(
        self,
        c: rl_canvas.Canvas,
        page_h: float,
        ext_x: float,
        ext_y: float,
        ext_w: float,
        ext_h: float,
        value: Value,
        index: int,
    ) -> PlacedValue | None:
        """Render a floor area annotation below the plan and return PlacedValue.

        # WHY: Area values are totals for the whole floor, not individual rooms,
        # so they are placed beneath the external wall rectangle with a clear
        # label prefix.

        Args:
            index:  Zero-based ordinal of this annotation (for vertical offset).

        Returns:
            PlacedValue with pixel bounding box, or None if geometry is invalid.
        """
        label = f"{value.attribute.replace('_', ' ').title()}: {value.display_text}"
        text_x_pt = ext_x
        text_y_pt = ext_y - (10 + index * (ANNO_FONT_SIZE * 1.5)) * mm

        # Guard: annotation must not fall off the page bottom
        if text_y_pt < MARGIN:
            text_y_pt = ext_y + 5 * mm + index * ANNO_FONT_SIZE * 1.5

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




# ---------------------------------------------------------------------------
# Module-level coordinate helper (identical contract to site_plan_generator)
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
        x_pt:           Left edge in PDF points.
        y_pt:           Bottom-left Y of text baseline in PDF points.
        w_pt:           Width in PDF points.
        h_pt:           Height in PDF points.
        page_height_pt: Total page height in PDF points (for Y-axis flip).

    Returns:
        BoundingBox in pixels at CANONICAL_DPI=300, origin top-left, page=1.

    # WHY: Duplicating this helper rather than importing from site_plan_generator
    # keeps the two modules independent.
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
