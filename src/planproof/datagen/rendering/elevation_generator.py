"""ElevationGenerator — raster building elevation with height annotation.

Produces a PNG image (A4 at 300 DPI, 2480 × 3508 px) showing a schematic
building front or side elevation with a labelled vertical height dimension line.
Every rendered measurement value is tracked with a pixel-precise bounding box so
the evaluation harness can locate it without re-parsing the image.

# DESIGN: This module uses Pillow (PIL) exclusively for raster operations.  No
# vector formats (SVG, PDF) are involved so coordinate arithmetic stays entirely
# in pixel space — there is no DPI scaling required at draw time.  The class
# satisfies the DocumentGenerator Protocol via structural subtyping (duck typing)
# without inheriting from any base class.

# WHY: A raster generator is preferred here over a vector generator because the
# downstream OCR/VLM pipeline consumes images, not vector graphics.  Generating
# directly to PNG avoids a vector-to-raster conversion step and gives us full
# control over rendering artefacts (anti-aliasing, line widths) that affect
# extraction difficulty.
"""

from __future__ import annotations

import io
import random
from typing import Final

from PIL import Image, ImageDraw, ImageFont

from planproof.datagen.rendering.models import GeneratedDocument, PlacedValue
from planproof.datagen.scenario.models import DocumentSpec, Scenario
from planproof.schemas.entities import BoundingBox, DocumentType, EntityType

# ---------------------------------------------------------------------------
# Canvas constants (A4 at 300 DPI)
# ---------------------------------------------------------------------------

# WHY: Using a single DPI constant makes it easy to switch resolution without
# hunting through magic numbers.  300 DPI is the canonical resolution for the
# entire PlanProof pipeline (see PlacedValue docstring in rendering/models.py).
CANVAS_DPI: Final[int] = 300

# A4 dimensions in millimetres, converted to pixels at 300 DPI.
# 210 mm × 297 mm → 2480 × 3508 px (rounding as per ISO 216 standard).
CANVAS_W: Final[int] = 2480
CANVAS_H: Final[int] = 3508

# Colour palette — light engineering drawing style (white background, dark lines).
BG_COLOUR: Final[tuple[int, int, int]] = (255, 255, 255)
LINE_COLOUR: Final[tuple[int, int, int]] = (20, 20, 20)
DIM_COLOUR: Final[tuple[int, int, int]] = (60, 60, 180)   # blue dimension lines
HATCH_COLOUR: Final[tuple[int, int, int]] = (160, 160, 160)

# Font sizes in pixels (roughly equivalent to pt sizes at 300 DPI).
FONT_LARGE: Final[int] = 72   # title block
FONT_MEDIUM: Final[int] = 52  # dimension labels, axis labels
FONT_SMALL: Final[int] = 40   # minor annotations

# Line widths in pixels.
BUILDING_LINE_W: Final[int] = 8
DIM_LINE_W: Final[int] = 4
DATUM_LINE_W: Final[int] = 6
ARROW_SIZE: Final[int] = 28   # arrowhead half-length


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Attempt to load a TrueType system font; fall back to Pillow's bitmap default.

    # WHY: System font availability varies across operating systems and Docker
    # images.  Falling back gracefully ensures the generator never raises an
    # uncaught exception in CI environments that lack TrueType fonts.  The
    # bitmap default is ugly but functional — tests pass regardless.

    # DESIGN: We try a short ordered list of common font paths rather than
    # querying the OS font registry to keep this module dependency-free and
    # cross-platform without needing fonttools or fc-list.
    """
    candidate_fonts = [
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "C:/Windows/Fonts/DejaVuSans.ttf",
        # macOS
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Linux / Docker
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidate_fonts:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    # WHY: load_default() always succeeds — it returns a small bitmap font
    # with a fixed size.  We accept the visual degradation for robustness.
    return ImageFont.load_default()


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    tip_x: int,
    tip_y: int,
    direction: str,
    colour: tuple[int, int, int],
    size: int,
) -> None:
    """Draw a small filled triangular arrowhead.

    Args:
        draw:      The ImageDraw context.
        tip_x:     X pixel coordinate of the arrow tip.
        tip_y:     Y pixel coordinate of the arrow tip.
        direction: 'up' or 'down' — determines which way the point faces.
        colour:    RGB fill colour.
        size:      Half-width of the arrowhead base in pixels.

    # WHY: Dimension lines in engineering drawings conventionally terminate with
    # filled arrowheads.  Drawing them as filled polygons gives crisper results
    # than line-based approaches at this resolution.
    """
    if direction == "up":
        polygon = [
            (tip_x, tip_y),
            (tip_x - size, tip_y + size * 2),
            (tip_x + size, tip_y + size * 2),
        ]
    else:  # down
        polygon = [
            (tip_x, tip_y),
            (tip_x - size, tip_y - size * 2),
            (tip_x + size, tip_y - size * 2),
        ]
    draw.polygon(polygon, fill=colour)


def _text_bounding_box(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> BoundingBox:
    """Compute the tight pixel bounding box of a text string as it would be drawn.

    Args:
        draw:  ImageDraw context (needed to measure text extents).
        x:     Left edge of the text in pixels.
        y:     Top edge of the text in pixels.
        text:  The string to measure.
        font:  The font used to render the text.

    Returns:
        BoundingBox in pixel coordinates, page=1.

    # WHY: Pillow's textbbox() returns (left, top, right, bottom) in absolute
    # pixel coordinates anchored at (x, y).  We convert this to (x, y, w, h)
    # because BoundingBox uses width/height rather than x2/y2, which is
    # consistent with the rest of the PlanProof coordinate model.
    """
    # textbbox returns (left, top, right, bottom) relative to the draw surface.
    # The anchor parameter "lt" means (x, y) is the left-top corner of the text.
    bbox = draw.textbbox((x, y), text, font=font, anchor="lt")
    left, top, right, bottom = bbox
    return BoundingBox(
        x=float(left),
        y=float(top),
        width=float(right - left),
        height=float(bottom - top),
        page=1,
    )


class ElevationGenerator:
    """Generates a raster PNG building elevation drawing with height annotation.

    Satisfies the DocumentGenerator Protocol (structural subtyping — no
    inheritance required).

    # DESIGN: All layout geometry is derived from the seed-controlled RNG so
    # that different seeds produce visually distinct drawings (varying roof type,
    # building proportions, etc.) while remaining byte-identical for the same
    # seed.  This gives the corpus controlled visual diversity.

    # WHY: Keeping all state in local variables within generate() (rather than
    # instance attributes) ensures the generator is stateless and therefore
    # safe to call from multiple threads simultaneously, which matters when
    # corpus generation is parallelised with concurrent.futures.
    """

    def generate(
        self,
        scenario: Scenario,
        doc_spec: DocumentSpec,
        seed: int,
    ) -> GeneratedDocument:
        """Render a building elevation PNG and return it with ground-truth metadata.

        Args:
            scenario:  Parent scenario — supplies ground-truth values (we look
                       up 'building_height' from scenario.values).
            doc_spec:  Per-document instructions (used for filename construction).
            seed:      Deterministic RNG seed for layout choices.

        Returns:
            GeneratedDocument with PNG bytes and PlacedValue records.

        # WHY: Accepting seed as an explicit parameter (not reading scenario.seed)
        # matches the DocumentGenerator Protocol contract and allows the registry
        # to override the seed for targeted reproduction of individual documents.
        """
        rng = random.Random(seed)

        # ------------------------------------------------------------------
        # Resolve building_height from the scenario values tuple.
        # ------------------------------------------------------------------

        # WHY: We look up by attribute name rather than position so this
        # generator is robust to scenarios that include additional values
        # (e.g. site_area, setback_front) alongside building_height.
        building_height_value = next(
            (v for v in scenario.values if v.attribute == "building_height"),
            None,
        )
        # Provide a sensible fallback so the generator never crashes when
        # building_height is absent from the scenario (e.g. unit tests that
        # exercise other aspects of the pipeline).
        if building_height_value is not None:
            height_display = building_height_value.display_text
            height_numeric = building_height_value.value
        else:
            height_display = "8.0m"
            height_numeric = 8.0

        # ------------------------------------------------------------------
        # Create canvas
        # ------------------------------------------------------------------

        image = Image.new("RGB", (CANVAS_W, CANVAS_H), color=BG_COLOUR)
        draw = ImageDraw.Draw(image)

        # Load fonts at the sizes we need.
        font_large = _load_font(FONT_LARGE)
        font_medium = _load_font(FONT_MEDIUM)
        font_small = _load_font(FONT_SMALL)

        # ------------------------------------------------------------------
        # Layout geometry — all in pixel coordinates.
        # ------------------------------------------------------------------

        # Reserve margins and title block at the bottom.
        margin_left: int = 200
        margin_right: int = 200
        margin_top: int = 200
        title_block_h: int = 280   # height of the bottom title band

        # Drawing area (excluding title block and top margin).
        draw_top: int = margin_top
        draw_bottom: int = CANVAS_H - title_block_h - 100  # 100 px gap above title
        draw_left: int = margin_left
        draw_right: int = CANVAS_W - margin_right

        # Ground datum sits near the bottom of the drawing area.
        ground_y: int = draw_bottom - 80

        # Building footprint — horizontally centred, random-width variations.
        bldg_width: int = rng.randint(900, 1400)
        bldg_cx: int = CANVAS_W // 2
        bldg_left: int = bldg_cx - bldg_width // 2
        bldg_right: int = bldg_cx + bldg_width // 2

        # Building height in pixels — scale so that height_numeric metres maps
        # to roughly 60 % of the available vertical drawing space.
        available_h: int = ground_y - draw_top - 200  # leave headroom for dim labels
        # WHY: We use a fixed reference scale (1 m = ~80 px at these canvas dims)
        # rather than fitting exactly to available_h so that different building
        # heights produce proportionally taller/shorter buildings, making the
        # visual diversity meaningful rather than always filling the frame.
        px_per_metre: float = min(80.0, available_h / max(height_numeric, 1.0) * 0.7)
        bldg_height_px: int = int(height_numeric * px_per_metre)
        bldg_top: int = ground_y - bldg_height_px

        # Ensure the building top does not exceed the drawing area top.
        bldg_top = max(bldg_top, draw_top + 200)

        # ------------------------------------------------------------------
        # Roof style — triangular (pitched) or flat, seeded random.
        # ------------------------------------------------------------------

        roof_style: str = rng.choice(["pitched", "flat"])
        ridge_x: int = bldg_cx
        overhang: int = rng.randint(30, 80)  # eave overhang in px

        # ------------------------------------------------------------------
        # Draw ground hatch (diagonal lines below datum for soil indication).
        # ------------------------------------------------------------------

        hatch_bottom: int = ground_y + 60
        hatch_step: int = 40
        for hx in range(draw_left, draw_right + hatch_step, hatch_step):
            draw.line(
                [(hx, ground_y), (hx - 60, hatch_bottom)],
                fill=HATCH_COLOUR,
                width=2,
            )

        # ------------------------------------------------------------------
        # Draw ground datum line.
        # ------------------------------------------------------------------

        draw.line(
            [(draw_left, ground_y), (draw_right, ground_y)],
            fill=LINE_COLOUR,
            width=DATUM_LINE_W,
        )

        # Ground level label "G.L." — placed left of the building.
        gl_label = "G.L."
        gl_x: int = draw_left + 20
        gl_y: int = ground_y - FONT_SMALL - 10
        draw.text(
            (gl_x, gl_y), gl_label,
            fill=LINE_COLOUR, font=font_small, anchor="lt",
        )

        # ------------------------------------------------------------------
        # Draw building outline (rectangle representing the front face).
        # ------------------------------------------------------------------

        draw.rectangle(
            [(bldg_left, bldg_top), (bldg_right, ground_y)],
            outline=LINE_COLOUR,
            width=BUILDING_LINE_W,
        )

        # ------------------------------------------------------------------
        # Draw roof.
        # ------------------------------------------------------------------

        if roof_style == "pitched":
            # Triangular pitched roof rising above the building rectangle.
            roof_apex_y: int = bldg_top - rng.randint(150, 350)
            roof_apex_y = max(roof_apex_y, draw_top + 50)
            draw.polygon(
                [
                    (bldg_left - overhang, bldg_top),
                    (ridge_x, roof_apex_y),
                    (bldg_right + overhang, bldg_top),
                ],
                outline=LINE_COLOUR,
                width=BUILDING_LINE_W,
            )
        else:
            # Flat roof with a small parapet overhang.
            parapet_y: int = bldg_top - rng.randint(30, 80)
            parapet_y = max(parapet_y, draw_top + 50)
            draw.rectangle(
                [
                    (bldg_left - overhang, parapet_y),
                    (bldg_right + overhang, bldg_top),
                ],
                outline=LINE_COLOUR,
                width=BUILDING_LINE_W,
            )
            _ = parapet_y  # roof_top_y used for future detail

        # ------------------------------------------------------------------
        # Height dimension line (vertical, with arrows and label).
        # ------------------------------------------------------------------

        # DESIGN: The dimension line is drawn to the right of the building
        # outline with a fixed offset so it does not overlap the facade.
        # Extension lines (horizontal ticks) project from the building at
        # ground level and building-top level to meet the dimension line.

        dim_offset_x: int = 160   # pixels to the right of the building right edge
        dim_x: int = bldg_right + dim_offset_x

        # Clamp dimension endpoints to the actual building face height.
        dim_top_y: int = bldg_top
        dim_bot_y: int = ground_y

        # Extension lines (horizontal) connecting building to dimension line.
        ext_y_values = [dim_top_y, dim_bot_y]
        for ey in ext_y_values:
            draw.line(
                [(bldg_right + 10, ey), (dim_x + 30, ey)],
                fill=DIM_COLOUR,
                width=DIM_LINE_W,
            )

        # Vertical dimension line.
        draw.line(
            [(dim_x, dim_top_y), (dim_x, dim_bot_y)],
            fill=DIM_COLOUR,
            width=DIM_LINE_W,
        )

        # Arrowheads at top and bottom of the dimension line.
        _draw_arrow(draw, dim_x, dim_top_y, "up", DIM_COLOUR, ARROW_SIZE)
        _draw_arrow(draw, dim_x, dim_bot_y, "down", DIM_COLOUR, ARROW_SIZE)

        # ------------------------------------------------------------------
        # Dimension label — the building_height value.
        # ------------------------------------------------------------------

        # WHY: The label is placed to the right of the dimension line,
        # vertically centred between the two arrowheads.  We record the
        # precise pixel bounding box of this text as a PlacedValue so the
        # evaluation harness can crop exactly this region for targeted
        # re-extraction.

        label_text: str = height_display
        label_x: int = dim_x + 30
        label_y_centre: int = (dim_top_y + dim_bot_y) // 2
        # Anchor "lm" = left-middle — horizontal left edge, vertical centre.
        # We compute the bbox using anchor "lt" after adjusting y for the font
        # half-height to keep the maths simple and compatible with all font types.
        label_y_top: int = label_y_centre - FONT_MEDIUM // 2

        draw.text(
            (label_x, label_y_top),
            label_text,
            fill=DIM_COLOUR,
            font=font_medium,
            anchor="lt",
        )

        # Record the bounding box using Pillow's textbbox measurement.
        # WHY: We compute the bbox *after* drawing so that if textbbox returns
        # a slightly different region due to font metrics, we record what Pillow
        # actually rendered rather than a hand-calculated approximation.
        height_bbox = _text_bounding_box(
            draw, label_x, label_y_top, label_text, font_medium,
        )

        # ------------------------------------------------------------------
        # "0.00" ground level annotation below datum.
        # ------------------------------------------------------------------

        datum_label = "0.00"
        datum_label_x = bldg_cx - 60
        datum_label_y = ground_y + 20
        draw.text(
            (datum_label_x, datum_label_y),
            datum_label,
            fill=LINE_COLOUR,
            font=font_small,
            anchor="lt",
        )

        # ------------------------------------------------------------------
        # Elevation title: "Front Elevation" or "Side Elevation" (seeded).
        # ------------------------------------------------------------------

        elevation_name: str = rng.choice(["Front Elevation", "Side Elevation"])

        # Title block background band at the bottom.
        title_top: int = CANVAS_H - title_block_h
        draw.rectangle(
            [(0, title_top), (CANVAS_W, CANVAS_H)],
            fill=(230, 230, 230),
            outline=LINE_COLOUR,
            width=4,
        )
        # Title text centred in the block.
        draw.text(
            (CANVAS_W // 2, title_top + title_block_h // 2),
            elevation_name,
            fill=LINE_COLOUR,
            font=font_large,
            anchor="mm",   # middle-middle (centre-centre)
        )

        # Drawing border (outer frame).
        draw.rectangle(
            [(50, 50), (CANVAS_W - 50, CANVAS_H - 50)],
            outline=LINE_COLOUR,
            width=6,
        )

        # ------------------------------------------------------------------
        # Encode image to PNG bytes.
        # ------------------------------------------------------------------

        buf = io.BytesIO()
        # WHY: optimize=False keeps encoding fast during corpus generation;
        # the file size is not a concern at the generation stage.
        image.save(buf, format="PNG", optimize=False)
        png_bytes: bytes = buf.getvalue()

        # ------------------------------------------------------------------
        # Build the PlacedValue record for building_height.
        # ------------------------------------------------------------------

        placed_height = PlacedValue(
            attribute="building_height",
            value=height_numeric,
            text_rendered=label_text,
            page=1,
            bounding_box=height_bbox,
            entity_type=EntityType.MEASUREMENT,
        )

        # ------------------------------------------------------------------
        # Construct and return the GeneratedDocument.
        # ------------------------------------------------------------------

        filename = f"{scenario.set_id}_elevation.png"

        return GeneratedDocument(
            filename=filename,
            doc_type=DocumentType.DRAWING,
            content_bytes=png_bytes,
            file_format="png",
            placed_values=(placed_height,),
        )
