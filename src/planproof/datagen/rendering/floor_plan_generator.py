"""FloorPlanGenerator — generates a room-layout floor plan PDF using reportlab.

The floor plan shows:
  - External wall rectangle (the building outline)
  - 2-3 internal room subdivisions (rectangles separated by wall lines)
  - Room dimension annotations (width × depth)
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

# External wall extents (the full building footprint on the page)
EXT_W: Final[float] = 160 * mm
EXT_H: Final[float] = 120 * mm

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

        # External wall origin: top-left quadrant of page
        ext_x = MARGIN
        ext_y = page_h - MARGIN - EXT_H

        # Subdivide into 2-3 rooms using the RNG
        rooms = self._make_rooms(rng, ext_x, ext_y, EXT_W, EXT_H)

        self._draw_external_walls(c, ext_x, ext_y, EXT_W, EXT_H)
        self._draw_internal_walls(c, rooms)
        self._draw_windows(c, ext_x, ext_y, EXT_W, EXT_H)
        self._draw_doors(c, rooms)
        self._draw_room_labels(c, rooms)

        # --- Conditional annotation rendering for tracked area values ---
        # WHY: Area values are placed once per document as a summary annotation
        # in the title block area rather than as a dimension on a specific room,
        # because floor area is a property of the whole floor, not one room.

        for attr in doc_spec.values_to_place:
            if attr not in _TRACKED_AREA_ATTRS:
                # WHY: Silently skip unrecognised attributes rather than raising,
                # so this generator composes safely in multi-document scenarios
                # where the same values_to_place list is shared across generators.
                continue
            val = value_by_attr.get(attr)
            if val is None:
                continue
            pv = self._draw_area_annotation(
                c, page_h, ext_x, ext_y, EXT_W, EXT_H, val, len(placed)
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
    # Private geometry helpers
    # ------------------------------------------------------------------

    def _make_rooms(
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
        # that no two seeds produce identical proportions.  The minimum room
        # dimension guard (0.25 × ext dimension) prevents degenerate thin rooms
        # that would make dimension annotations unreadable.

        Returns:
            List of _Room objects covering the full external footprint.
        """
        rooms: list[_Room] = []

        # First cut: always vertical, splitting at 40%–60% of width
        cut1 = ext_w * rng.uniform(0.40, 0.60)
        rooms.append(_Room(ext_x, ext_y, cut1, ext_h, "Living Room"))
        rooms.append(_Room(ext_x + cut1, ext_y, ext_w - cut1, ext_h, "Kitchen"))

        # Optional second cut: horizontal, splitting the right room
        if rng.random() < 0.5:
            cut2 = ext_h * rng.uniform(0.40, 0.60)
            # Replace the "Kitchen" room with two stacked rooms
            right_x = ext_x + cut1
            right_w = ext_w - cut1
            rooms.pop()  # remove original right room
            rooms.append(_Room(right_x, ext_y + cut2, right_w, ext_h - cut2, "Kitchen"))
            rooms.append(_Room(right_x, ext_y, right_w, cut2, "Utility"))

        return rooms

    def _draw_external_walls(
        self,
        c: rl_canvas.Canvas,
        x: float, y: float, w: float, h: float,
    ) -> None:
        """Draw the external building outline as a thick solid rectangle."""
        c.saveState()
        c.setLineWidth(WALL_T)
        c.rect(x, y, w, h)
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

        # Collect unique vertical dividers (x-coordinate of room right edges
        # that are interior to the external boundary).
        dividers: set[tuple[float, float, float, float]] = set()
        for room in rooms:
            right_x = room.x + room.w
            top_y = room.y + room.h
            # Vertical right edge that is not the external boundary right edge
            # WHY: We check whether this edge is shared by another room to avoid
            # drawing external walls twice.
            for other in rooms:
                if abs(other.x - right_x) < 0.5:   # matches another room's left
                    dividers.add((right_x, room.y, right_x, top_y))
            # Horizontal top edge that is not the external boundary top edge
            for other in rooms:
                if abs(other.y - top_y) < 0.5:
                    dividers.add((room.x, top_y, room.x + room.w, top_y))

        for x1, y1, x2, y2 in dividers:
            c.line(x1, y1, x2, y2)

        c.restoreState()

    def _draw_windows(
        self,
        c: rl_canvas.Canvas,
        ext_x: float, ext_y: float, ext_w: float, ext_h: float,
    ) -> None:
        """Draw double-line window indicators on the external walls.

        # WHY: Window indicators (two parallel lines interrupting the wall line)
        # are a standard architectural drawing convention.  Including them makes
        # the floor plan look like a real architectural drawing rather than a
        # simple rectangle, which matters for visual realism of the synthetic data.
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
        # the floor plan visual complexity and confirm that the drawing is a
        # habitable room layout rather than a structural diagram.
        """
        c.saveState()
        c.setLineWidth(0.5)
        for room in rooms:
            # Door gap line (where the door leaf sits in the wall)
            door_x = room.x + DOOR_R
            door_y = room.y
            c.line(door_x, door_y, door_x + DOOR_R, door_y)
            # Swing arc: quarter circle from 180° to 90° (bottom-left)
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
        # label prefix.  The index parameter staggers multiple annotations
        # vertically so they never overlap.

        Args:
            index:  Zero-based ordinal of this annotation (for vertical offset).

        Returns:
            PlacedValue with pixel bounding box, or None if geometry is invalid.
        """
        label = f"{value.attribute.replace('_', ' ').title()}: {value.display_text}"
        text_x_pt = ext_x
        # Place below the external wall boundary, staggered by index
        text_y_pt = ext_y - (10 + index * (ANNO_FONT_SIZE * 1.5)) * mm

        # Guard: annotation must not fall off the page bottom
        if text_y_pt < MARGIN:
            # WHY: If the annotation would fall below the margin, move it inside
            # the boundary area near the bottom to avoid off-page bounding boxes.
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
    # keeps the two modules independent — they are separate generators that
    # happen to share the same coordinate math.  If either is removed the other
    # remains fully functional.  A shared coord_utils import is still used for
    # the actual math, so there is no duplication of logic.
    """
    # Top-left corner: PDF "top" of text box is y_pt + h_pt (Y increases up in PDF)
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
