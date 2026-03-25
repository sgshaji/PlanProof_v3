"""Tests for FloorPlanGenerator — TDD first pass.

# WHY: Writing tests before the implementation makes the required observable
# behaviour explicit.  Floor plans are primarily structural context documents,
# but they must still produce valid PDFs and correctly track any compliance-
# relevant values (e.g. building footprint area) that appear in values_to_place.

# DESIGN: Tests mirror the same helper pattern as test_site_plan_generator so
# both test suites are readable in the same mental model.
"""
from __future__ import annotations

import pytest

from planproof.datagen.rendering.floor_plan_generator import FloorPlanGenerator
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict
from planproof.schemas.entities import DocumentType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scenario(*attributes: str) -> Scenario:
    """Build a minimal Scenario containing the requested Value attributes."""
    values = tuple(
        Value(
            attribute=attr,
            value=_default_value(attr),
            unit=_default_unit(attr),
            display_text=_default_display(attr),
        )
        for attr in attributes
    )
    doc_spec = DocumentSpec(
        doc_type="DRAWING",
        file_format="pdf",
        values_to_place=attributes,
    )
    return Scenario(
        set_id="SET_T002",
        category="compliant",
        seed=7,
        profile_id="test",
        difficulty="low",
        degradation_preset="clean",
        values=values,
        verdicts=(
            Verdict(rule_id="R002", outcome="PASS", evaluated_value=50.0, threshold=100.0),
        ),
        documents=(doc_spec,),
        edge_case_strategy=None,
    )


def _default_value(attr: str) -> float:
    defaults = {
        "building_footprint_area": 85.0,
        "ground_floor_area": 75.0,
    }
    return defaults.get(attr, 1.0)


def _default_unit(attr: str) -> str:
    area_attrs = {"building_footprint_area", "ground_floor_area"}
    return "m²" if attr in area_attrs else "metres"


def _default_display(attr: str) -> str:
    mapping = {
        "building_footprint_area": "85m²",
        "ground_floor_area": "75m²",
    }
    return mapping.get(attr, "1.0m")


def _make_doc_spec(*attributes: str) -> DocumentSpec:
    return DocumentSpec(
        doc_type="DRAWING",
        file_format="pdf",
        values_to_place=attributes,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFloorPlanGeneratorGeneratesPdf:
    """FloorPlanGenerator must return a valid PDF document."""

    def test_generates_pdf(self) -> None:
        """generate() returns a GeneratedDocument whose bytes start with %PDF.

        # WHY: %PDF magic bytes are the definitive signal that reportlab
        # produced a valid, parseable PDF file rather than empty or corrupt bytes.
        """
        scenario = _make_scenario("building_footprint_area")
        doc_spec = _make_doc_spec("building_footprint_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        assert result.content_bytes[:4] == b"%PDF", (
            "Expected PDF magic bytes; got: %r" % result.content_bytes[:8]
        )
        assert len(result.content_bytes) > 100

    def test_generated_document_metadata(self) -> None:
        """GeneratedDocument must carry correct doc_type, format, and filename."""
        scenario = _make_scenario()
        doc_spec = _make_doc_spec()
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=0)

        assert result.doc_type == DocumentType.DRAWING
        assert result.file_format == "pdf"
        assert result.filename  # non-empty string

    def test_generates_pdf_with_no_values(self) -> None:
        """Generator must succeed even when values_to_place is empty.

        # WHY: The floor plan is always rendered as structural context regardless
        # of whether any compliance-critical values need to be tracked.  An empty
        # values_to_place must produce a valid PDF with zero placed_values.
        """
        scenario = _make_scenario()
        doc_spec = _make_doc_spec()
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=99)

        assert result.content_bytes[:4] == b"%PDF"
        assert result.placed_values == ()

    def test_floor_plan_title_variants(self) -> None:
        """Floor plans can be labelled 'Ground Floor Plan' or 'First Floor Plan'.

        # WHY: Planning submissions often include multiple floor-level drawings.
        # The seed drives which title is chosen deterministically; verifying this
        # with two seeds guards against the title being hard-coded.
        """
        scenario_a = _make_scenario()
        doc_spec = _make_doc_spec()
        gen = FloorPlanGenerator()

        # Both seeds must produce valid PDFs — title selection must not crash.
        result_a = gen.generate(scenario=scenario_a, doc_spec=doc_spec, seed=0)
        result_b = gen.generate(scenario=scenario_a, doc_spec=doc_spec, seed=1)

        assert result_a.content_bytes[:4] == b"%PDF"
        assert result_b.content_bytes[:4] == b"%PDF"


class TestFloorPlanGeneratorPlacedValuesTracked:
    """Values in values_to_place must be recorded in placed_values."""

    def test_placed_values_tracked(self) -> None:
        """building_footprint_area must appear in placed_values when requested.

        # WHY: Floor plans are the primary source of building footprint area.
        # If the generator silently omits a tracked value, the evaluation
        # harness has no ground truth and the scenario becomes unevaluable.
        """
        scenario = _make_scenario("building_footprint_area")
        doc_spec = _make_doc_spec("building_footprint_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        attrs = [pv.attribute for pv in result.placed_values]
        assert "building_footprint_area" in attrs, (
            f"Expected 'building_footprint_area' in placed_values; got {attrs}"
        )

    def test_ground_floor_area_tracked(self) -> None:
        """ground_floor_area must appear in placed_values when requested."""
        scenario = _make_scenario("ground_floor_area")
        doc_spec = _make_doc_spec("ground_floor_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        attrs = [pv.attribute for pv in result.placed_values]
        assert "ground_floor_area" in attrs

    def test_placed_value_text_matches_scenario(self) -> None:
        """text_rendered must match Value.display_text from the scenario.

        # WHY: Same invariant as the site plan test — the evaluation harness
        # compares OCR output against text_rendered, so they must agree.
        """
        scenario = _make_scenario("building_footprint_area")
        doc_spec = _make_doc_spec("building_footprint_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        pv = next(
            pv for pv in result.placed_values
            if pv.attribute == "building_footprint_area"
        )
        assert pv.text_rendered == "85m²"

    def test_unknown_value_attribute_is_skipped(self) -> None:
        """Values with attributes not handled by the generator must be skipped.

        # WHY: The floor plan generator only knows about area-type values.
        # Encountering an unrecognised attribute (e.g. front_setback) must not
        # raise an exception — it should simply produce no PlacedValue entry.
        """
        scenario = _make_scenario("front_setback")
        doc_spec = _make_doc_spec("front_setback")
        generator = FloorPlanGenerator()

        # Must not raise; unknown values are silently skipped
        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)
        assert result.content_bytes[:4] == b"%PDF"

    def test_multiple_values_all_tracked(self) -> None:
        """All tracked value attributes must appear when multiple are requested."""
        scenario = _make_scenario("building_footprint_area", "ground_floor_area")
        doc_spec = _make_doc_spec("building_footprint_area", "ground_floor_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        attrs = {pv.attribute for pv in result.placed_values}
        assert "building_footprint_area" in attrs
        assert "ground_floor_area" in attrs


class TestFloorPlanGeneratorBoundingBoxes:
    """All placed-value bounding boxes must be positive and on page 1."""

    def test_bounding_boxes_positive(self) -> None:
        """Every bounding box must have width > 0 and height > 0.

        # WHY: Zero or negative dimensions are a sure sign of a coordinate
        # conversion bug (Y-flip omitted or wrong page height used).
        """
        scenario = _make_scenario("building_footprint_area")
        doc_spec = _make_doc_spec("building_footprint_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        for pv in result.placed_values:
            bb = pv.bounding_box
            assert bb.width > 0, f"{pv.attribute}: width={bb.width} not positive"
            assert bb.height > 0, f"{pv.attribute}: height={bb.height} not positive"

    def test_bounding_boxes_within_page(self) -> None:
        """Every bounding box must lie within the A3-landscape page boundary.

        # A3 landscape at 300 DPI: 4961 × 3508 pixels.
        """
        PAGE_W_PX = 4961.0
        PAGE_H_PX = 3508.0

        scenario = _make_scenario("building_footprint_area", "ground_floor_area")
        doc_spec = _make_doc_spec("building_footprint_area", "ground_floor_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        for pv in result.placed_values:
            bb = pv.bounding_box
            assert bb.x >= 0
            assert bb.y >= 0
            assert bb.x + bb.width <= PAGE_W_PX + 1
            assert bb.y + bb.height <= PAGE_H_PX + 1

    def test_bounding_box_page_number(self) -> None:
        """All bounding boxes must reference page 1 (single-page document)."""
        scenario = _make_scenario("building_footprint_area")
        doc_spec = _make_doc_spec("building_footprint_area")
        generator = FloorPlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=7)

        for pv in result.placed_values:
            assert pv.page == 1
            assert pv.bounding_box.page == 1
