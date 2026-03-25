"""Tests for SitePlanGenerator — TDD first pass.

# WHY: Writing tests before implementation forces us to define the exact public
# API and the observable contracts (PDF bytes produced, PlacedValues recorded,
# bounding boxes positive) before any rendering code exists.  This catches
# interface mismatches early and gives a definitive "done" signal.

# DESIGN: Every test constructs its own minimal Scenario/DocumentSpec rather
# than sharing fixtures, so each test is self-contained and its intent is
# readable without cross-referencing conftest files.
"""
from __future__ import annotations

import pytest

from planproof.datagen.rendering.site_plan_generator import SitePlanGenerator
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict
from planproof.schemas.entities import DocumentType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scenario(*attributes: str) -> Scenario:
    """Build a minimal Scenario containing the requested Value attributes.

    # WHY: A factory function avoids repeating the full Scenario constructor
    # in every test, reducing noise so each test focuses on its assertion.
    """
    values = tuple(
        Value(attribute=attr, value=_default_value(attr), unit=_default_unit(attr),
              display_text=_default_display(attr))
        for attr in attributes
    )
    doc_spec = DocumentSpec(
        doc_type="DRAWING",
        file_format="pdf",
        values_to_place=attributes,
    )
    return Scenario(
        set_id="SET_T001",
        category="compliant",
        seed=42,
        profile_id="test",
        difficulty="low",
        degradation_preset="clean",
        values=values,
        verdicts=(
            Verdict(rule_id="R001", outcome="PASS", evaluated_value=3.0, threshold=3.0),
        ),
        documents=(doc_spec,),
        edge_case_strategy=None,
    )


def _default_value(attr: str) -> float:
    # WHY: Provide realistic planning values so the generator can scale
    # geometry meaningfully rather than using zeros.
    defaults = {
        "front_setback": 3.0,
        "rear_garden_depth": 10.5,
        "site_coverage": 35.0,
    }
    return defaults.get(attr, 1.0)


def _default_unit(attr: str) -> str:
    if attr == "site_coverage":
        return "%"
    return "metres"


def _default_display(attr: str) -> str:
    mapping = {
        "front_setback": "3.0m",
        "rear_garden_depth": "10.5m",
        "site_coverage": "35%",
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

class TestSitePlanGeneratorGeneratesPdf:
    """SitePlanGenerator must return non-empty PDF bytes."""

    def test_generates_pdf(self) -> None:
        """generate() returns a GeneratedDocument whose bytes start with %PDF.

        # WHY: The %PDF magic bytes are the definitive signal that reportlab
        # produced a valid PDF file.  Checking only the length would miss cases
        # where garbage bytes are returned.
        """
        scenario = _make_scenario("front_setback")
        doc_spec = _make_doc_spec("front_setback")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        assert result.content_bytes[:4] == b"%PDF", (
            "Expected PDF magic bytes; got: %r" % result.content_bytes[:8]
        )
        assert len(result.content_bytes) > 100  # non-trivial PDF

    def test_generated_document_metadata(self) -> None:
        """GeneratedDocument must have the correct doc_type and file_format."""
        scenario = _make_scenario("front_setback")
        doc_spec = _make_doc_spec("front_setback")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        assert result.doc_type == DocumentType.DRAWING
        assert result.file_format == "pdf"
        assert result.filename  # non-empty filename

    def test_generates_pdf_with_no_values(self) -> None:
        """Generator must succeed even when values_to_place is empty.

        # WHY: Robustness requirement — a drawing without tracked values should
        # still produce a valid PDF (title block, north arrow, scale bar are
        # unconditional elements).
        """
        scenario = _make_scenario()
        doc_spec = _make_doc_spec()
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=0)

        assert result.content_bytes[:4] == b"%PDF"
        assert result.placed_values == ()


class TestSitePlanGeneratorPlacedValuesForSetback:
    """front_setback must produce a PlacedValue when included in values_to_place."""

    def test_placed_values_for_setback(self) -> None:
        """A front_setback Value must appear in placed_values.

        # WHY: Ground-truth coverage is the core deliverable of the generator.
        # If a Value is listed in values_to_place but missing from placed_values,
        # the evaluation harness has no ground truth to compare against.
        """
        scenario = _make_scenario("front_setback")
        doc_spec = _make_doc_spec("front_setback")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        attrs = [pv.attribute for pv in result.placed_values]
        assert "front_setback" in attrs, (
            f"Expected 'front_setback' in placed_values attributes; got {attrs}"
        )

    def test_placed_values_for_rear_garden_depth(self) -> None:
        """rear_garden_depth must produce a PlacedValue when present."""
        scenario = _make_scenario("rear_garden_depth")
        doc_spec = _make_doc_spec("rear_garden_depth")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        attrs = [pv.attribute for pv in result.placed_values]
        assert "rear_garden_depth" in attrs

    def test_placed_values_for_site_coverage(self) -> None:
        """site_coverage must produce a PlacedValue when present."""
        scenario = _make_scenario("site_coverage")
        doc_spec = _make_doc_spec("site_coverage")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        attrs = [pv.attribute for pv in result.placed_values]
        assert "site_coverage" in attrs

    def test_placed_value_text_matches_scenario(self) -> None:
        """The text_rendered field must match Value.display_text from the scenario.

        # WHY: The evaluation harness compares OCR output against text_rendered.
        # If the generator renders a different string than what is recorded in
        # text_rendered, false-positive evaluation failures will occur.
        """
        scenario = _make_scenario("front_setback")
        doc_spec = _make_doc_spec("front_setback")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        pv = next(pv for pv in result.placed_values if pv.attribute == "front_setback")
        assert pv.text_rendered == "3.0m"

    def test_all_three_values_placed(self) -> None:
        """All three site plan values can be placed simultaneously."""
        scenario = _make_scenario("front_setback", "rear_garden_depth", "site_coverage")
        doc_spec = _make_doc_spec("front_setback", "rear_garden_depth", "site_coverage")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        attrs = {pv.attribute for pv in result.placed_values}
        assert {"front_setback", "rear_garden_depth", "site_coverage"} == attrs


class TestSitePlanGeneratorBoundingBoxes:
    """All bounding boxes must have positive dimensions in pixel coordinates."""

    def test_bounding_boxes_positive(self) -> None:
        """Every PlacedValue bounding box must have width > 0 and height > 0.

        # WHY: A zero or negative bounding box indicates a coordinate conversion
        # error (most likely a missed Y-flip).  The evaluation harness would
        # fail to crop any meaningful region from the page for re-extraction.
        """
        scenario = _make_scenario("front_setback", "rear_garden_depth", "site_coverage")
        doc_spec = _make_doc_spec("front_setback", "rear_garden_depth", "site_coverage")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        for pv in result.placed_values:
            bb = pv.bounding_box
            assert bb.width > 0, f"{pv.attribute}: width={bb.width} not positive"
            assert bb.height > 0, f"{pv.attribute}: height={bb.height} not positive"

    def test_bounding_boxes_within_page(self) -> None:
        """Every PlacedValue bounding box must lie within the A3-landscape page.

        # WHY: Bounding boxes that exceed the page dimensions are unclippable
        # and indicate the renderer placed text outside the canvas — a layout bug.
        # A3 landscape at 300 DPI: 4961 × 3508 pixels.
        """
        # A3 landscape: 420 mm × 297 mm → at 300 DPI: 4961 × 3508 px
        PAGE_W_PX = 4961.0
        PAGE_H_PX = 3508.0

        scenario = _make_scenario("front_setback", "rear_garden_depth", "site_coverage")
        doc_spec = _make_doc_spec("front_setback", "rear_garden_depth", "site_coverage")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        for pv in result.placed_values:
            bb = pv.bounding_box
            assert bb.x >= 0, f"{pv.attribute}: x={bb.x} is negative"
            assert bb.y >= 0, f"{pv.attribute}: y={bb.y} is negative"
            assert bb.x + bb.width <= PAGE_W_PX + 1, (
                f"{pv.attribute}: right edge {bb.x + bb.width} exceeds page width"
            )
            assert bb.y + bb.height <= PAGE_H_PX + 1, (
                f"{pv.attribute}: bottom edge {bb.y + bb.height} exceeds page height"
            )

    def test_bounding_box_page_number(self) -> None:
        """All bounding boxes must reference page 1 (single-page document)."""
        scenario = _make_scenario("front_setback")
        doc_spec = _make_doc_spec("front_setback")
        generator = SitePlanGenerator()

        result = generator.generate(scenario=scenario, doc_spec=doc_spec, seed=42)

        for pv in result.placed_values:
            assert pv.page == 1, f"{pv.attribute}: expected page=1, got page={pv.page}"
            assert pv.bounding_box.page == 1
