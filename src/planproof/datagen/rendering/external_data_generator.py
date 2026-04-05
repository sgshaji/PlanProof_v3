"""ExternalDataGenerator — simple reference-data PDF with tracked values.

Generates a single-page PDF representing external/reference data such as
Land Registry parcel areas and conservation area status.  This provides
the EXTERNAL_DATA document type that rules C003 and C006 require.

# DESIGN: The generator produces a minimal, clean PDF with labelled fields.
# Unlike forms and drawings, external data documents are not degraded
# because they represent structured authority records, not scanned paper.
"""

from __future__ import annotations

import io
import random

import reportlab.lib.colors as colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from planproof.datagen.rendering.coord_utils import pdf_points_to_pixels
from planproof.datagen.rendering.models import GeneratedDocument, PlacedValue
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value
from planproof.schemas.entities import BoundingBox, DocumentType, EntityType

PAGE_WIDTH_PT: float = A4[0]
PAGE_HEIGHT_PT: float = A4[1]
LEFT_MARGIN_PT: float = 20 * mm
RIGHT_MARGIN_PT: float = PAGE_WIDTH_PT - 20 * mm
TOP_MARGIN_PT: float = PAGE_HEIGHT_PT - 20 * mm
CONTENT_WIDTH_PT: float = RIGHT_MARGIN_PT - LEFT_MARGIN_PT

# Attribute name → EntityType mapping for placed values.
_ENTITY_TYPE_MAP: dict[str, EntityType] = {
    "reference_parcel_area": EntityType.MEASUREMENT,
    "conservation_area_status": EntityType.ZONE,
    "zone_category": EntityType.ZONE,
}


class ExternalDataGenerator:
    """Generates a single-page external reference data PDF."""

    def generate(
        self,
        scenario: Scenario,
        doc_spec: DocumentSpec,
        seed: int,
    ) -> GeneratedDocument:
        rng = random.Random(seed)

        values_map: dict[str, Value] = {v.attribute: v for v in scenario.values}
        placed_values: list[PlacedValue] = []

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # Header
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.HexColor("#2c2c2c"))
        c.drawString(LEFT_MARGIN_PT, TOP_MARGIN_PT, "EXTERNAL REFERENCE DATA")
        c.setFont("Helvetica", 9)
        c.drawRightString(RIGHT_MARGIN_PT, TOP_MARGIN_PT, "Page 1 of 1")
        c.setStrokeColor(colors.HexColor("#2c2c2c"))
        c.setLineWidth(1.2)
        c.line(LEFT_MARGIN_PT, TOP_MARGIN_PT - 20, RIGHT_MARGIN_PT, TOP_MARGIN_PT - 20)

        y = TOP_MARGIN_PT - 50

        # Section heading
        c.setFillColor(colors.HexColor("#dce6f0"))
        c.rect(LEFT_MARGIN_PT, y - 12, CONTENT_WIDTH_PT, 14, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#1a3a6b"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LEFT_MARGIN_PT + 4, y - 9, "Land Registry & Planning Authority Records")
        c.setFillColor(colors.black)
        y -= 30

        # Render each attribute that is in both values_to_place and values_map
        for attr in doc_spec.values_to_place:
            if attr not in values_map:
                continue

            val_obj = values_map[attr]
            display = val_obj.display_text or val_obj.str_value or str(val_obj.value)
            label = attr.replace("_", " ").title() + ":"
            label_width = 200.0

            # Label
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.HexColor("#444444"))
            c.drawString(LEFT_MARGIN_PT, y - 11, label)

            # Value box
            field_x = LEFT_MARGIN_PT + label_width
            field_width = CONTENT_WIDTH_PT - label_width
            row_height = 16.0
            c.setFillColor(colors.HexColor("#f7f9fc"))
            c.setStrokeColor(colors.HexColor("#b0bec5"))
            c.setLineWidth(0.5)
            c.rect(field_x, y - row_height, field_width, row_height, fill=1, stroke=1)

            c.setFillColor(colors.HexColor("#1a3a6b"))
            c.setFont("Helvetica-Bold", 10)
            c.drawString(field_x + 4, y - 12, display)
            c.setFillColor(colors.black)

            # Track placed value
            text_x = field_x + 4
            text_y = y - row_height
            pixel_origin = pdf_points_to_pixels(text_x, text_y + row_height, PAGE_HEIGHT_PT)
            from planproof.datagen.rendering.coord_utils import SCALE_FACTOR
            w_px = (field_width - 4) * SCALE_FACTOR
            h_px = row_height * SCALE_FACTOR

            bb = BoundingBox(
                x=round(pixel_origin.x, 2),
                y=round(pixel_origin.y, 2),
                width=round(w_px, 2),
                height=round(h_px, 2),
                page=1,
            )
            entity_type = _ENTITY_TYPE_MAP.get(attr, EntityType.MEASUREMENT)
            placed_values.append(
                PlacedValue(
                    attribute=attr,
                    value=val_obj.value if val_obj.value != 0.0 else (val_obj.str_value or val_obj.display_text),
                    text_rendered=display,
                    page=1,
                    bounding_box=bb,
                    entity_type=entity_type,
                )
            )

            y -= 24

        # Footer
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.HexColor("#888888"))
        c.drawString(LEFT_MARGIN_PT, 40, f"Reference: REF/{scenario.seed:05d}")

        c.save()
        pdf_bytes = buffer.getvalue()

        return GeneratedDocument(
            filename=f"{scenario.set_id}_external_data.pdf",
            doc_type=DocumentType.EXTERNAL_DATA,
            content_bytes=pdf_bytes,
            file_format="pdf",
            placed_values=tuple(placed_values),
        )
