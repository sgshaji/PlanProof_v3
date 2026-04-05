"""FormGenerator — 7-page planning application PDF with bbox tracking.

Generates a synthetic BCC-style householder planning application form.
Every ground-truth value is rendered at a deterministic position and
tracked as a PlacedValue with a pixel-space bounding box (300 DPI,
origin top-left).

# DESIGN: The form structure is modelled after real BCC (Brisbane City
# Council) householder application forms, which follow a standard layout:
#   Page 1 — Application header, site address, applicant details
#   Page 2 — Agent details, description of proposed works
#   Page 3 — Materials and measurements (building_height, site_coverage, …)
#   Page 4 — Trees, parking, access
#   Page 5 — Flooding, drainage, waste
#   Page 6 — Ownership certificate (Certificate A or B)
#   Page 7 — Declaration and signature
#
# The 7-page structure is fixed so downstream models can expect a
# consistent document shape, making form-type classification and page
# segmentation easier to train and evaluate.

# DESIGN: We use a single class with no base class and implement the
# DocumentGenerator Protocol via structural subtyping (duck typing).
# This keeps FormGenerator independent of the registry module; it can
# be imported and tested without touching the registry at all.
"""

from __future__ import annotations

import io
import random
from typing import Final

import reportlab.lib.colors as colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from planproof.datagen.rendering.coord_utils import pdf_points_to_pixels
from planproof.datagen.rendering.models import GeneratedDocument, PlacedValue
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value
from planproof.schemas.entities import BoundingBox, DocumentType, EntityType

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# WHY: Store A4 dimensions in module-level constants so every page-drawing
# helper reads from one authoritative source.  Changing page size only
# requires updating these two lines.
PAGE_WIDTH_PT: Final[float] = A4[0]   # 595.28 points
PAGE_HEIGHT_PT: Final[float] = A4[1]  # 841.89 points

# WHY: Margins are fixed at 20 mm so the form looks professional and the
# content area is consistent across all pages.  All layout x-positions are
# expressed relative to LEFT_MARGIN_PT.
LEFT_MARGIN_PT: Final[float] = 20 * mm
RIGHT_MARGIN_PT: Final[float] = PAGE_WIDTH_PT - 20 * mm
TOP_MARGIN_PT: Final[float] = PAGE_HEIGHT_PT - 20 * mm
CONTENT_WIDTH_PT: Final[float] = RIGHT_MARGIN_PT - LEFT_MARGIN_PT

# WHY: Font sizes are named constants rather than magic numbers so the
# visual hierarchy is self-documenting in the rendering code.
FONT_TITLE: Final[int] = 14
FONT_SECTION: Final[int] = 11
FONT_LABEL: Final[int] = 9
FONT_VALUE: Final[int] = 10

# WHY: The value-text fill colour (dark blue) differentiates ground-truth
# values from placeholder text at a glance during visual QA.
VALUE_COLOUR = colors.HexColor("#1a3a6b")

# ---------------------------------------------------------------------------
# Synthetic content pools (seeded-random selection)
# ---------------------------------------------------------------------------

# WHY: Using small, fixed pools of realistic UK planning content means the
# generated forms look plausible without requiring external data files.  The
# seed controls which items are selected, so content is deterministic and
# reproducible across pipeline runs.

_STREET_NAMES: Final[tuple[str, ...]] = (
    "Acacia Avenue",
    "Birchwood Close",
    "Cedar Drive",
    "Daffodil Lane",
    "Elm Court",
    "Foxglove Road",
    "Gorse Hill",
    "Hawthorn Way",
    "Ivy Gardens",
    "Juniper Mews",
)

_CITIES: Final[tuple[str, ...]] = (
    "Bristol",
    "Leeds",
    "Manchester",
    "Sheffield",
    "Birmingham",
    "Nottingham",
    "Leicester",
    "Brighton",
    "Oxford",
    "Cambridge",
)

_POSTCODES: Final[tuple[str, ...]] = (
    "BS1 4DJ",
    "LS2 7AB",
    "M4 1EQ",
    "S1 2GH",
    "B3 2PX",
    "NG1 5FT",
    "LE1 7GH",
    "BN1 1AE",
    "OX1 3BQ",
    "CB2 1TN",
)

_FIRST_NAMES: Final[tuple[str, ...]] = (
    "James",
    "Emily",
    "Oliver",
    "Charlotte",
    "William",
    "Amelia",
    "Thomas",
    "Sophie",
    "George",
    "Isabella",
)

_LAST_NAMES: Final[tuple[str, ...]] = (
    "Smith",
    "Jones",
    "Taylor",
    "Brown",
    "Davies",
    "Evans",
    "Wilson",
    "Thomas",
    "Roberts",
    "Johnson",
)

_WORK_DESCRIPTIONS: Final[tuple[str, ...]] = (
    "Single storey rear extension to provide additional kitchen/dining space.",
    "Two-storey side extension with loft conversion including rear dormer window.",
    "Ground floor front porch extension with pitched roof.",
    "Detached double garage with room in roof to rear of existing dwelling.",
    "First floor side extension above existing garage to create additional bedroom.",
    "Rear conservatory extension with glazed roof to existing dwelling.",
)

_MATERIALS: Final[tuple[str, ...]] = (
    "Facing brick to match existing, plain clay roof tiles.",
    "Render finish to match existing walls, concrete interlocking roof tiles.",
    "Red stock brick, natural Welsh slate roof covering.",
    "Facing brick, fibre cement roof slates, UPVC windows and doors.",
    "Engineering brick base, render above DPC, clay pantiles.",
)

_AGENT_COMPANIES: Final[tuple[str, ...]] = (
    "Apex Planning Consultants Ltd",
    "Blueprint Architecture Studio",
    "Clearview Design & Build Ltd",
    "Draftsman Design Services",
    "Elevation Planning Ltd",
)


# ---------------------------------------------------------------------------
# Internal helper: _CanvasState
# ---------------------------------------------------------------------------

class _CanvasState:
    """Mutable rendering context passed through all page-drawing helpers.

    # DESIGN: Grouping the canvas, buffer, placed_values list, and current
    # page cursor into one object keeps helper function signatures concise —
    # helpers accept a single _CanvasState rather than four separate arguments.
    # This is an internal implementation detail; it never crosses the public
    # API boundary.

    # WHY: placed_values is a list during construction then converted to a
    # tuple in the public return value.  Appending to a list is O(1) amortised
    # and avoids creating a new tuple for every placed value, which would be
    # O(n²) overall.
    """

    def __init__(self, c: canvas.Canvas, page_num: int) -> None:
        self.c = c
        self.page_num = page_num
        self.placed_values: list[PlacedValue] = []


# ---------------------------------------------------------------------------
# Internal drawing primitives
# ---------------------------------------------------------------------------

def _draw_header(c: canvas.Canvas, title: str, page_num: int) -> None:
    """Draw the standard page header with form title, page number, and a rule.

    # WHY: Every page shares the same header so the form reads as a coherent
    # multi-page document.  Factoring it out prevents copy-paste drift between
    # pages.
    """
    # Form title in bold
    c.setFont("Helvetica-Bold", FONT_TITLE)
    c.setFillColor(colors.HexColor("#2c2c2c"))
    c.drawString(LEFT_MARGIN_PT, TOP_MARGIN_PT, "HOUSEHOLDER PLANNING APPLICATION")

    # Page reference, right-aligned
    c.setFont("Helvetica", FONT_LABEL)
    page_label = f"Page {page_num} of 7"
    c.drawRightString(RIGHT_MARGIN_PT, TOP_MARGIN_PT, page_label)

    # Subtitle / section hint
    c.setFont("Helvetica", FONT_SECTION - 1)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(LEFT_MARGIN_PT, TOP_MARGIN_PT - 14, title)

    # Horizontal rule under header
    c.setStrokeColor(colors.HexColor("#2c2c2c"))
    c.setLineWidth(1.2)
    c.line(LEFT_MARGIN_PT, TOP_MARGIN_PT - 20, RIGHT_MARGIN_PT, TOP_MARGIN_PT - 20)

    c.setFillColor(colors.black)  # reset


def _draw_section_heading(c: canvas.Canvas, y: float, text: str) -> float:
    """Draw a section heading bar and return the new y cursor below it.

    # WHY: Returning the new y position keeps the caller's layout loop
    # simple: it just passes the returned y to the next draw call.
    """
    c.setFillColor(colors.HexColor("#dce6f0"))
    c.rect(LEFT_MARGIN_PT, y - 12, CONTENT_WIDTH_PT, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1a3a6b"))
    c.setFont("Helvetica-Bold", FONT_SECTION)
    c.drawString(LEFT_MARGIN_PT + 4, y - 9, text)
    c.setFillColor(colors.black)
    return y - 22  # move cursor below heading


def _draw_field(
    c: canvas.Canvas,
    y: float,
    label: str,
    value_text: str,
    label_width: float = 160,
) -> tuple[float, float, float, float, float]:
    """Draw a label + value field row.

    Returns (x_pt, y_pt, field_w, field_h, new_y) where:
      - (x_pt, y_pt) is the PDF-point origin of the value text bounding box
        (bottom-left of the text baseline, in PDF coordinate system)
      - field_w / field_h are the bounding box dimensions in PDF points
      - new_y is the cursor y after this row

    # WHY: Returning the raw PDF coordinates here (not pixel coords) keeps
    # this function free of knowledge about DPI conversion.  The caller owns
    # the coordinate system decision, which makes unit testing the layout
    # math easier in isolation.

    # DESIGN: We return a 5-tuple rather than a NamedTuple to avoid creating
    # a new type class for a trivial internal return value.
    """
    row_height: float = 16.0
    field_x = LEFT_MARGIN_PT + label_width
    field_width = CONTENT_WIDTH_PT - label_width

    # Label
    c.setFont("Helvetica", FONT_LABEL)
    c.setFillColor(colors.HexColor("#444444"))
    c.drawString(LEFT_MARGIN_PT, y - 11, label)

    # Light box behind the value for visual separation
    c.setFillColor(colors.HexColor("#f7f9fc"))
    c.setStrokeColor(colors.HexColor("#b0bec5"))
    c.setLineWidth(0.5)
    c.rect(field_x, y - row_height, field_width, row_height, fill=1, stroke=1)

    # Value text in dark blue to visually mark ground-truth content
    c.setFillColor(VALUE_COLOUR)
    c.setFont("Helvetica-Bold", FONT_VALUE)
    c.drawString(field_x + 4, y - 12, value_text)

    c.setFillColor(colors.black)

    # The bounding box of the value text in PDF coordinates:
    #   x = field_x + 4  (left of text)
    #   y = y - row_height  (bottom edge of the row box)
    text_x = field_x + 4
    text_y = y - row_height
    return (text_x, text_y, field_width - 4, row_height, text_y - 4)


def _place_value(
    state: _CanvasState,
    attribute: str,
    raw_value: object,
    text_rendered: str,
    x_pt: float,
    y_pt: float,
    w_pt: float,
    h_pt: float,
    entity_type: EntityType,
) -> None:
    """Convert PDF coordinates to pixels and append a PlacedValue to the state.

    # WHY: Centralising the coordinate conversion and PlacedValue construction
    # in one function ensures that every ground-truth record uses the same
    # conversion path.  If the conversion logic needs to change (e.g. DPI
    # update), there is exactly one place to fix.
    """
    # Convert bottom-left PDF point to top-left pixel for the bounding box origin
    pixel_origin = pdf_points_to_pixels(x_pt, y_pt + h_pt, PAGE_HEIGHT_PT)
    # Width and height scale linearly (no Y-flip needed for dimensions)
    from planproof.datagen.rendering.coord_utils import SCALE_FACTOR
    w_px = w_pt * SCALE_FACTOR
    h_px = h_pt * SCALE_FACTOR

    bb = BoundingBox(
        x=round(pixel_origin.x, 2),
        y=round(pixel_origin.y, 2),
        width=round(w_px, 2),
        height=round(h_px, 2),
        page=state.page_num,
    )
    pv = PlacedValue(
        attribute=attribute,
        value=raw_value,
        text_rendered=text_rendered,
        page=state.page_num,
        bounding_box=bb,
        entity_type=entity_type,
    )
    state.placed_values.append(pv)


# ---------------------------------------------------------------------------
# Page-drawing functions
# ---------------------------------------------------------------------------

def _draw_page1(
    state: _CanvasState,
    rng: random.Random,
    scenario: Scenario,
    values_map: dict[str, Value],
    address_text: str,
) -> None:
    """Page 1 — Application header, site address, applicant details."""
    c = state.c
    _draw_header(c, "Application Header / Site Address / Applicant Details", 1)
    y = TOP_MARGIN_PT - 40

    y = _draw_section_heading(c, y, "1. Application Reference")
    ref_num = f"APP/{scenario.seed:05d}/HH"
    _draw_field(c, y, "Application Reference:", ref_num)
    y -= 22

    y = _draw_section_heading(c, y, "2. Site Address")
    # Site address is a ground-truth value — track it
    field_vals = _draw_field(c, y, "Site Address:", address_text, label_width=130)
    _place_value(
        state,
        attribute="site_address",
        raw_value=address_text,
        text_rendered=address_text,
        x_pt=field_vals[0],
        y_pt=field_vals[1],
        w_pt=field_vals[2],
        h_pt=field_vals[3],
        entity_type=EntityType.ADDRESS,
    )
    y -= 22

    # form_address — tracked separately for C002 address consistency check.
    # Uses the C002 fixture address if present, otherwise mirrors site_address.
    if "form_address" in values_map:
        fa_val = values_map["form_address"]
        fa_text = fa_val.str_value or fa_val.display_text
        field_vals = _draw_field(c, y, "Form Address:", fa_text, label_width=130)
        _place_value(
            state,
            attribute="form_address",
            raw_value=fa_text,
            text_rendered=fa_text,
            x_pt=field_vals[0],
            y_pt=field_vals[1],
            w_pt=field_vals[2],
            h_pt=field_vals[3],
            entity_type=EntityType.ADDRESS,
        )
        y -= 22

    # site_location — area/suburb name for C006 conservation area check
    if "site_location" in values_map:
        sl_val = values_map["site_location"]
        sl_text = sl_val.str_value or sl_val.display_text
        field_vals = _draw_field(c, y, "Site Location:", sl_text, label_width=130)
        _place_value(
            state,
            attribute="site_location",
            raw_value=sl_text,
            text_rendered=sl_text,
            x_pt=field_vals[0],
            y_pt=field_vals[1],
            w_pt=field_vals[2],
            h_pt=field_vals[3],
            entity_type=EntityType.ADDRESS,
        )
        y -= 22

    # zone_category — planning zone classification for R001/R002/R003
    if "zone_category" in values_map:
        zc_val = values_map["zone_category"]
        zc_text = zc_val.str_value or zc_val.display_text
        field_vals = _draw_field(c, y, "Zone Classification:", zc_text, label_width=150)
        _place_value(
            state,
            attribute="zone_category",
            raw_value=zc_text,
            text_rendered=zc_text,
            x_pt=field_vals[0],
            y_pt=field_vals[1],
            w_pt=field_vals[2],
            h_pt=field_vals[3],
            entity_type=EntityType.ZONE,
        )
        y -= 22

    y = _draw_section_heading(c, y, "3. Applicant Details")
    first = rng.choice(_FIRST_NAMES)
    last = rng.choice(_LAST_NAMES)
    applicant_name = f"{first} {last}"
    _draw_field(c, y, "Full Name:", applicant_name)
    y -= 20

    house_num = rng.randint(1, 150)
    street = rng.choice(_STREET_NAMES)
    city = rng.choice(_CITIES)
    postcode = rng.choice(_POSTCODES)
    corr_addr = f"{house_num} {street}, {city}, {postcode}"
    _draw_field(c, y, "Correspondence Address:", corr_addr, label_width=170)
    y -= 20

    _draw_field(c, y, "Telephone:", f"0{rng.randint(1000000000, 1999999999)}")
    y -= 20

    _draw_field(c, y, "Email:", f"{first.lower()}.{last.lower()}@email.co.uk")
    y -= 30

    y = _draw_section_heading(c, y, "4. Type of Application")
    _draw_field(c, y, "Application Type:", "Householder (HH)")
    y -= 20
    _draw_field(c, y, "Works Type:", "Extension / Alteration")


def _draw_page2(
    state: _CanvasState,
    rng: random.Random,
) -> None:
    """Page 2 — Agent details, description of proposed works."""
    c = state.c
    _draw_header(c, "Agent Details / Description of Proposed Works", 2)
    y = TOP_MARGIN_PT - 40

    y = _draw_section_heading(c, y, "5. Agent / Representative Details")
    company = rng.choice(_AGENT_COMPANIES)
    _draw_field(c, y, "Company Name:", company)
    y -= 20
    contact_first = rng.choice(_FIRST_NAMES)
    contact_last = rng.choice(_LAST_NAMES)
    _draw_field(c, y, "Contact Name:", f"{contact_first} {contact_last}")
    y -= 20
    _draw_field(c, y, "Agent Telephone:", f"0{rng.randint(1000000000, 1999999999)}")
    y -= 20
    _draw_field(
        c, y, "Agent Email:",
        f"planning@{company.split()[0].lower()}.co.uk",
        label_width=140,
    )
    y -= 30

    y = _draw_section_heading(c, y, "6. Description of Proposed Works")
    desc = rng.choice(_WORK_DESCRIPTIONS)
    # Multi-line description — draw as wrapped text
    c.setFont("Helvetica", FONT_LABEL)
    c.setFillColor(colors.HexColor("#333333"))

    # Draw a box for the description field
    box_h = 60.0
    c.setFillColor(colors.HexColor("#f7f9fc"))
    c.setStrokeColor(colors.HexColor("#b0bec5"))
    c.setLineWidth(0.5)
    c.rect(LEFT_MARGIN_PT, y - box_h, CONTENT_WIDTH_PT, box_h, fill=1, stroke=1)

    # Label above box
    c.setFillColor(colors.HexColor("#444444"))
    c.setFont("Helvetica", FONT_LABEL)
    c.drawString(LEFT_MARGIN_PT, y + 3, "Description:")

    # Text inside box (simple wrapping for display purposes)
    c.setFillColor(colors.HexColor("#222222"))
    c.setFont("Helvetica", FONT_VALUE - 1)
    # Naive wrapping: break description into two lines if too long
    if len(desc) > 65:
        mid = desc.rfind(" ", 0, 65)
        line1, line2 = desc[:mid], desc[mid:].strip()
    else:
        line1, line2 = desc, ""
    c.drawString(LEFT_MARGIN_PT + 4, y - 14, line1)
    if line2:
        c.drawString(LEFT_MARGIN_PT + 4, y - 26, line2)
    c.setFillColor(colors.black)
    y -= box_h + 14

    y = _draw_section_heading(c, y, "7. Pre-Application Advice")
    _draw_field(c, y, "Pre-application reference:", "N/A")
    y -= 20
    _draw_field(c, y, "Date of advice:", "N/A")


def _draw_page3(
    state: _CanvasState,
    rng: random.Random,
    values_map: dict[str, Value],
) -> None:
    """Page 3 — Materials and measurements.

    # WHY: Page 3 is the most important page for compliance rule evaluation
    # because it contains numeric measurements (building_height, site_coverage,
    # etc.).  We place every value from values_to_place that appears in
    # values_map on this page so the ground-truth labels are concentrated on
    # the page most likely to be targeted by the extraction pipeline.
    """
    c = state.c
    _draw_header(c, "Materials and Measurements", 3)
    y = TOP_MARGIN_PT - 40

    y = _draw_section_heading(c, y, "8. Materials")
    materials = rng.choice(_MATERIALS)
    c.setFont("Helvetica", FONT_LABEL)
    c.setFillColor(colors.HexColor("#444444"))
    c.drawString(LEFT_MARGIN_PT, y - 3, "Proposed external materials:")
    c.setFont("Helvetica", FONT_VALUE - 1)
    c.setFillColor(colors.HexColor("#222222"))
    # Simple wrap
    if len(materials) > 70:
        mid = materials.rfind(" ", 0, 70)
        c.drawString(LEFT_MARGIN_PT, y - 16, materials[:mid])
        c.drawString(LEFT_MARGIN_PT, y - 28, materials[mid:].strip())
        y -= 44
    else:
        c.drawString(LEFT_MARGIN_PT, y - 16, materials)
        y -= 32
    c.setFillColor(colors.black)

    y = _draw_section_heading(c, y, "9. Measurements")

    # --- Ground-truth value placement ---
    # We iterate over a fixed ordered list of measurement attributes so the
    # layout is deterministic.  Values not present in values_map are filled
    # with synthetic plausible data.

    # WHY: Defining the display order here (not in the scenario) keeps layout
    # concerns separate from the scenario data model.
    MEASUREMENT_ROWS: list[tuple[str, str, str]] = [
        ("building_height",        "Building Height (m):",         "m"),
        ("ridge_height",           "Ridge Height (m):",            "m"),
        ("eaves_height",           "Eaves Height (m):",            "m"),
        ("rear_garden_depth",      "Rear Garden Depth (m):",       "m"),
        ("site_coverage",          "Site Coverage (%):",           "%"),
        ("building_footprint_area","Building Footprint Area (m²):", "m²"),
        ("total_site_area",        "Total Site Area (m²):",        "m²"),
        ("stated_site_area",       "Stated Site Area (m²):",       "m²"),
        ("floor_area",             "Floor Area (m²):",             "m²"),
        ("extension_length",       "Extension Length (m):",        "m"),
        ("extension_depth",        "Extension Depth (m):",         "m"),
        ("extension_height",       "Extension Height (m):",        "m"),
    ]

    for attr, label, unit_suffix in MEASUREMENT_ROWS:
        if attr in values_map:
            val_obj = values_map[attr]
            display = val_obj.display_text
        else:
            # Synthetic placeholder — realistic range for the attribute
            placeholder_map: dict[str, str] = {
                "building_height":         f"{rng.uniform(4.5, 9.0):.1f}m",
                "ridge_height":            f"{rng.uniform(6.0, 10.0):.1f}m",
                "eaves_height":            f"{rng.uniform(2.5, 5.5):.1f}m",
                "rear_garden_depth":       f"{rng.uniform(8.0, 25.0):.1f}m",
                "site_coverage":           f"{rng.uniform(20.0, 50.0):.0f}%",
                "building_footprint_area": f"{rng.uniform(40.0, 200.0):.0f}m²",
                "total_site_area":         f"{rng.uniform(200.0, 800.0):.0f}m²",
                "stated_site_area":        f"{rng.uniform(200.0, 800.0):.0f}m²",
                "floor_area":              f"{rng.uniform(20.0, 120.0):.0f}m²",
                "extension_length":        f"{rng.uniform(2.0, 8.0):.1f}m",
                "extension_depth":         f"{rng.uniform(1.5, 6.0):.1f}m",
                "extension_height":        f"{rng.uniform(2.4, 4.0):.1f}m",
            }
            display = placeholder_map.get(attr, "N/A")

        field_vals = _draw_field(c, y, label, display, label_width=200)

        if attr in values_map:
            # Record a PlacedValue only for ground-truth values
            _place_value(
                state,
                attribute=attr,
                raw_value=values_map[attr].value,
                text_rendered=display,
                x_pt=field_vals[0],
                y_pt=field_vals[1],
                w_pt=field_vals[2],
                h_pt=field_vals[3],
                entity_type=EntityType.MEASUREMENT,
            )

        y -= 20

        if y < 100:
            # Safety guard: stop drawing if we've run off the page
            break


def _draw_page4(state: _CanvasState, rng: random.Random) -> None:
    """Page 4 — Trees, parking, access."""
    c = state.c
    _draw_header(c, "Trees / Parking / Access", 4)
    y = TOP_MARGIN_PT - 40

    y = _draw_section_heading(c, y, "10. Trees and Hedges")
    _draw_field(c, y, "Protected trees on site:", "No")
    y -= 20
    _draw_field(c, y, "Trees within 5m of works:", rng.choice(["Yes", "No"]))
    y -= 20
    species = rng.choice(["Oak", "Ash", "Beech", "Sycamore", "N/A"])
    _draw_field(c, y, "Species (if applicable):", species)
    y -= 30

    y = _draw_section_heading(c, y, "11. Parking")
    spaces_before = rng.randint(1, 3)
    spaces_after = rng.randint(1, 3)
    _draw_field(c, y, "Parking spaces before works:", str(spaces_before))
    y -= 20
    _draw_field(c, y, "Parking spaces after works:", str(spaces_after))
    y -= 30

    y = _draw_section_heading(c, y, "12. Access")
    _draw_field(c, y, "Vehicle access change:", "No")
    y -= 20
    _draw_field(c, y, "New access required:", "No")
    y -= 20
    _draw_field(c, y, "Highway comments:", "Works do not affect highway.")


def _draw_page5(state: _CanvasState, rng: random.Random) -> None:
    """Page 5 — Flooding, drainage, waste."""
    c = state.c
    _draw_header(c, "Flooding / Drainage / Waste", 5)
    y = TOP_MARGIN_PT - 40

    y = _draw_section_heading(c, y, "13. Flooding")
    _draw_field(c, y, "Flood zone:", rng.choice(["Zone 1", "Zone 2", "Zone 3"]))
    y -= 20
    _draw_field(c, y, "Flood risk assessment required:", "No")
    y -= 20
    _draw_field(c, y, "SuDS applicable:", "No")
    y -= 30

    y = _draw_section_heading(c, y, "14. Foul Sewage")
    _draw_field(c, y, "Foul drainage connection:", "Mains sewer")
    y -= 20
    _draw_field(c, y, "Surface water connection:", "Soakaway / existing drainage")
    y -= 30

    y = _draw_section_heading(c, y, "15. Biodiversity")
    _draw_field(c, y, "Ecological survey required:", "No")
    y -= 20
    _draw_field(c, y, "Bat/bird habitat on site:", rng.choice(["Yes", "No"]))
    y -= 30

    y = _draw_section_heading(c, y, "16. Waste Storage")
    _draw_field(c, y, "Waste storage provision:", "Existing bin store retained")
    y -= 20
    _draw_field(c, y, "Recycling provision:", "Existing provision adequate")


def _draw_page6(
    state: _CanvasState,
    rng: random.Random,
    values_map: dict[str, Value],
) -> None:
    """Page 6 — Ownership certificate (Certificate A or B)."""
    c = state.c
    _draw_header(c, "Ownership Certificate", 6)
    y = TOP_MARGIN_PT - 40

    # Use scenario value for certificate_type if available; otherwise random.
    if "certificate_type" in values_map:
        cert_val = values_map["certificate_type"]
        cert_letter = cert_val.str_value or cert_val.display_text
        cert_type = f"Certificate {cert_letter}"
    else:
        cert_type = rng.choice(["Certificate A", "Certificate B"])
        cert_letter = cert_type.split()[-1]

    y = _draw_section_heading(c, y, f"17. {cert_type}")

    if "A" in cert_letter:
        blurb = (
            "I certify that on the date this application was made, no person other "
            "than the applicant was the owner of any part of the land to which the "
            "application relates."
        )
    else:
        blurb = (
            "I certify that the applicant has notified all other owners of the land "
            "to which the application relates, in accordance with the requirements "
            "of Article 11 of the Town and Country Planning (Development Management "
            "Procedure) Order 2010."
        )

    c.setFont("Helvetica", FONT_LABEL)
    c.setFillColor(colors.HexColor("#333333"))
    # Naive wrapping at 90 chars
    words = blurb.split()
    lines: list[str] = []
    current = ""
    for w in words:
        if len(current) + len(w) + 1 > 88:
            lines.append(current)
            current = w
        else:
            current = (current + " " + w).strip()
    if current:
        lines.append(current)
    for line in lines:
        c.drawString(LEFT_MARGIN_PT, y - 3, line)
        y -= 13

    y -= 20
    y = _draw_section_heading(c, y, "18. Signature")
    first = rng.choice(_FIRST_NAMES)
    last = rng.choice(_LAST_NAMES)
    _draw_field(c, y, "Signed (Applicant/Agent):", f"{first} {last}")
    y -= 20
    _draw_field(c, y, "Date:", "25/03/2026")
    y -= 20

    # Track certificate_type as a PlacedValue (C001)
    field_vals = _draw_field(c, y, "Certificate type:", cert_type)
    if "certificate_type" in values_map:
        _place_value(
            state,
            attribute="certificate_type",
            raw_value=cert_letter,
            text_rendered=cert_type,
            x_pt=field_vals[0],
            y_pt=field_vals[1],
            w_pt=field_vals[2],
            h_pt=field_vals[3],
            entity_type=EntityType.CERTIFICATE,
        )
    y -= 22

    # Render ownership_declaration if present (C001 companion)
    if "ownership_declaration" in values_map:
        od_val = values_map["ownership_declaration"]
        od_text = od_val.str_value or od_val.display_text
        field_vals = _draw_field(c, y, "Ownership Declaration:", od_text)
        _place_value(
            state,
            attribute="ownership_declaration",
            raw_value=od_text,
            text_rendered=od_text,
            x_pt=field_vals[0],
            y_pt=field_vals[1],
            w_pt=field_vals[2],
            h_pt=field_vals[3],
            entity_type=EntityType.OWNERSHIP,
        )


def _draw_page7(state: _CanvasState, rng: random.Random) -> None:
    """Page 7 — Declaration and signature."""
    c = state.c
    _draw_header(c, "Declaration and Signature", 7)
    y = TOP_MARGIN_PT - 40

    y = _draw_section_heading(c, y, "19. Declaration")

    declaration = (
        "I/We hereby apply for planning permission as described in this application "
        "and in accordance with the accompanying plans. The information given in this "
        "application is correct and accurate to the best of my/our knowledge. "
        "I/We understand that if planning permission is granted this does not affect "
        "the need to obtain any other approvals required under separate legislation "
        "or other planning consents that may be required."
    )

    c.setFont("Helvetica", FONT_LABEL)
    c.setFillColor(colors.HexColor("#333333"))
    words = declaration.split()
    lines_decl: list[str] = []
    current = ""
    for w in words:
        if len(current) + len(w) + 1 > 88:
            lines_decl.append(current)
            current = w
        else:
            current = (current + " " + w).strip()
    if current:
        lines_decl.append(current)
    for line in lines_decl:
        c.drawString(LEFT_MARGIN_PT, y - 3, line)
        y -= 13

    y -= 20
    y = _draw_section_heading(c, y, "20. Applicant Signature")
    first = rng.choice(_FIRST_NAMES)
    last = rng.choice(_LAST_NAMES)
    _draw_field(c, y, "Full Name:", f"{first} {last}")
    y -= 20
    _draw_field(c, y, "Signature:", "____________________________")
    y -= 20
    _draw_field(c, y, "Date:", "25/03/2026")
    y -= 30

    y = _draw_section_heading(c, y, "21. Agent Signature")
    agent_first = rng.choice(_FIRST_NAMES)
    agent_last = rng.choice(_LAST_NAMES)
    _draw_field(c, y, "Agent Name:", f"{agent_first} {agent_last}")
    y -= 20
    _draw_field(c, y, "Signature:", "____________________________")
    y -= 20
    _draw_field(c, y, "Date:", "25/03/2026")
    y -= 30

    # Reference box at bottom
    c.setFont("Helvetica-Oblique", FONT_LABEL - 1)
    c.setFillColor(colors.HexColor("#888888"))
    c.drawString(
        LEFT_MARGIN_PT,
        50,
        "For office use only — DO NOT WRITE BELOW THIS LINE",
    )
    c.line(LEFT_MARGIN_PT, 47, RIGHT_MARGIN_PT, 47)


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class FormGenerator:
    """Generates a 7-page planning application form PDF.

    Implements the DocumentGenerator Protocol via structural subtyping.
    Every ground-truth value listed in doc_spec.values_to_place is rendered
    on the appropriate page and tracked as a PlacedValue with a pixel-space
    bounding box (300 DPI, origin top-left).

    # DESIGN: The class has no __init__ parameters because all configuration
    # is supplied at generate() call time via the Scenario and DocumentSpec.
    # This makes FormGenerator stateless and therefore safe for concurrent use
    # if the corpus generation pipeline is parallelised.
    """

    def generate(
        self,
        scenario: Scenario,
        doc_spec: DocumentSpec,
        seed: int,
    ) -> GeneratedDocument:
        """Render a 7-page planning application form and return its bytes + placements.

        Args:
            scenario:  Parent scenario supplying ground-truth values and set_id.
            doc_spec:  Per-document instructions (must have doc_type == "FORM").
            seed:      Random seed for deterministic layout and placeholder content.

        Returns:
            A GeneratedDocument with content_bytes (valid PDF) and every
            ground-truth value tracked in placed_values.

        # WHY: seed is accepted as an explicit parameter (in addition to being
        # available via scenario.seed) because the DocumentGenerator Protocol
        # requires it.  This lets the registry override the seed for targeted
        # document reproduction without constructing a new Scenario object.
        """
        # WHY: Seeding a dedicated Random instance rather than using the global
        # random state means this function is side-effect-free with respect to
        # other components that use random.  Parallel corpus generation is safe.
        rng = random.Random(seed)

        # Build a lookup from attribute name → Value for O(1) access inside page draws.
        # WHY: Iterating over scenario.values for every row on page 3 would be O(n*m);
        # pre-building the dict makes it O(n + m).
        values_map: dict[str, Value] = {v.attribute: v for v in scenario.values}

        # Generate a deterministic site address from the seeded RNG.
        # WHY: site_address is always placed on the form regardless of whether
        # a compliance rule references it, because real planning applications
        # always identify the site.  Generating it here (rather than expecting
        # a Value in the scenario) makes every generated form self-contained.
        house_num = rng.randint(1, 200)
        street = rng.choice(_STREET_NAMES)
        city = rng.choice(_CITIES)
        postcode = rng.choice(_POSTCODES)
        address_text = f"{house_num} {street}, {city}, {postcode}"

        # --- Build the PDF in memory ---
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # Page 1 — Application header / site address / applicant details
        state_p1 = _CanvasState(c, page_num=1)
        _draw_page1(state_p1, rng, scenario, values_map, address_text)
        c.showPage()

        # Page 2 — Agent details / description of works
        state_p2 = _CanvasState(c, page_num=2)
        _draw_page2(state_p2, rng)
        c.showPage()

        # Page 3 — Materials and measurements (most ground-truth values land here)
        state_p3 = _CanvasState(c, page_num=3)
        _draw_page3(state_p3, rng, values_map)
        c.showPage()

        # Page 4 — Trees / parking / access
        state_p4 = _CanvasState(c, page_num=4)
        _draw_page4(state_p4, rng)
        c.showPage()

        # Page 5 — Flooding / drainage / waste
        state_p5 = _CanvasState(c, page_num=5)
        _draw_page5(state_p5, rng)
        c.showPage()

        # Page 6 — Ownership certificate
        state_p6 = _CanvasState(c, page_num=6)
        _draw_page6(state_p6, rng, values_map)
        c.showPage()

        # Page 7 — Declaration and signature
        state_p7 = _CanvasState(c, page_num=7)
        _draw_page7(state_p7, rng)
        c.save()

        pdf_bytes = buffer.getvalue()

        # Merge all placed_values from every page state into a single tuple.
        # WHY: Converting to tuple here (not list) ensures the returned
        # GeneratedDocument is deeply immutable, matching the frozen dataclass
        # contract defined in rendering/models.py.
        all_placed: list[PlacedValue] = (
            state_p1.placed_values
            + state_p2.placed_values
            + state_p3.placed_values
            + state_p4.placed_values
            + state_p5.placed_values
            + state_p6.placed_values
            + state_p7.placed_values
        )

        return GeneratedDocument(
            filename=f"{scenario.set_id}_form.pdf",
            doc_type=DocumentType.FORM,
            content_bytes=pdf_bytes,
            file_format="pdf",
            placed_values=tuple(all_placed),
        )
