"""Tests for ElevationGenerator — raster building elevation with height annotation.

# WHY: Following strict TDD: tests are written before the implementation so that
# the contract is defined by the tests, not inferred from the code.  Each test
# exercises a distinct requirement stated in the task spec so failures are
# immediately actionable.
"""
from __future__ import annotations

import pytest

from planproof.datagen.rendering.elevation_generator import ElevationGenerator
from planproof.datagen.rendering.models import GeneratedDocument, PlacedValue
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict
from planproof.schemas.entities import EntityType


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_scenario(building_height: float = 7.5, seed: int = 42) -> Scenario:
    """Build a minimal Scenario that includes a building_height Value.

    # WHY: We construct the smallest valid Scenario rather than using mocks so
    # that the generator's value-lookup logic is exercised under realistic
    # conditions without any external dependencies (no YAML, no filesystem).
    """
    return Scenario(
        set_id="SET_TEST001",
        category="compliant",
        seed=seed,
        profile_id="standard_3file",
        difficulty="low",
        degradation_preset="none",
        values=(
            Value(
                attribute="building_height",
                value=building_height,
                unit="m",
                display_text=f"{building_height}m",
            ),
        ),
        verdicts=(
            Verdict(
                rule_id="R001",
                outcome="PASS",
                evaluated_value=building_height,
                threshold=9.0,
            ),
        ),
        documents=(
            DocumentSpec(
                doc_type="DRAWING",
                file_format="png",
                values_to_place=("building_height",),
            ),
        ),
        edge_case_strategy=None,
    )


def _make_doc_spec() -> DocumentSpec:
    return DocumentSpec(
        doc_type="DRAWING",
        file_format="png",
        values_to_place=("building_height",),
    )


@pytest.fixture()
def generator() -> ElevationGenerator:
    return ElevationGenerator()


@pytest.fixture()
def generated(generator: ElevationGenerator) -> GeneratedDocument:
    """Generate a document once and reuse across multiple tests."""
    scenario = _make_scenario()
    doc_spec = _make_doc_spec()
    return generator.generate(scenario, doc_spec, seed=42)


# ---------------------------------------------------------------------------
# Test: output is a valid PNG
# ---------------------------------------------------------------------------

class TestGeneratesPng:
    """The generator must produce raw PNG bytes."""

    def test_generates_png(self, generated: GeneratedDocument) -> None:
        """content_bytes must start with the canonical PNG signature.

        # WHY: The PNG signature (8 bytes) is the cheapest possible check that
        # Pillow saved in the correct format.  It avoids importing a full image
        # library in the test while still verifying the encoding contract.
        """
        PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
        assert generated.content_bytes[:8] == PNG_SIGNATURE

    def test_file_format_is_png(self, generated: GeneratedDocument) -> None:
        """GeneratedDocument.file_format must be the string 'png'."""
        assert generated.file_format == "png"

    def test_content_bytes_non_empty(self, generated: GeneratedDocument) -> None:
        """A valid image must produce a non-trivially small byte payload."""
        # WHY: An A4@300DPI PNG is comfortably > 10 kB even for a blank canvas.
        assert len(generated.content_bytes) > 10_000


# ---------------------------------------------------------------------------
# Test: placed values are tracked
# ---------------------------------------------------------------------------

class TestPlacedValuesTracked:
    """The generator must record at least one PlacedValue for building_height."""

    def test_placed_values_tracked(self, generated: GeneratedDocument) -> None:
        """At least one PlacedValue must have attribute == 'building_height'.

        # WHY: This is the core contract of the generator — every rendered
        # measurement must be present in the ground-truth record so the
        # evaluation harness can locate it without re-parsing the image.
        """
        attributes = {pv.attribute for pv in generated.placed_values}
        assert "building_height" in attributes

    def test_placed_values_non_empty(self, generated: GeneratedDocument) -> None:
        """The placed_values tuple must have at least one entry."""
        assert len(generated.placed_values) >= 1

    def test_placed_value_text_contains_height(
        self, generated: GeneratedDocument
    ) -> None:
        """The rendered text for building_height must include the numeric value."""
        pv = next(
            p for p in generated.placed_values if p.attribute == "building_height"
        )
        # WHY: The display_text is "7.5m"; we check the numeric part is present
        # without prescribing the exact format (units may be abbreviated, etc.).
        assert "7.5" in pv.text_rendered


# ---------------------------------------------------------------------------
# Test: bounding boxes are valid positive coordinates
# ---------------------------------------------------------------------------

class TestBoundingBoxesPositive:
    """All PlacedValue bounding boxes must have positive, non-zero dimensions.

    # WHY: A negative or zero-size bounding box would silently corrupt evaluation
    # — the crop region would be empty or outside the canvas.  Checking this
    # here catches off-by-one errors in coordinate arithmetic early.
    """

    def test_bounding_boxes_positive(self, generated: GeneratedDocument) -> None:
        """All x and y coordinates must be >= 0; width and height must be > 0."""
        for pv in generated.placed_values:
            bb = pv.bounding_box
            assert bb.x >= 0, f"Negative x for {pv.attribute}: {bb.x}"
            assert bb.y >= 0, f"Negative y for {pv.attribute}: {bb.y}"
            assert bb.width > 0, f"Zero/negative width for {pv.attribute}: {bb.width}"
            assert bb.height > 0, f"Zero/negative height for {pv.attribute}: {bb.height}"

    def test_bounding_box_within_canvas(self, generated: GeneratedDocument) -> None:
        """Bounding boxes must not extend beyond the A4@300DPI canvas dimensions.

        # WHY: A bounding box outside the canvas would be unreachable by any
        # OCR or VLM crop, making that ground-truth entry useless or misleading.
        """
        CANVAS_W = 2480
        CANVAS_H = 3508
        for pv in generated.placed_values:
            bb = pv.bounding_box
            assert bb.x + bb.width <= CANVAS_W, (
                f"{pv.attribute} bbox right edge {bb.x + bb.width} > canvas width"
            )
            assert bb.y + bb.height <= CANVAS_H, (
                f"{pv.attribute} bbox bottom edge {bb.y + bb.height} > canvas height"
            )


# ---------------------------------------------------------------------------
# Test: entity type is MEASUREMENT
# ---------------------------------------------------------------------------

class TestEntityTypeIsMeasurement:
    """building_height must be classified as EntityType.MEASUREMENT.

    # WHY: The evaluation harness routes extracted entities by entity_type.
    # If building_height is tagged with the wrong type it will be sent to the
    # wrong extractor and silently missed during compliance checking.
    """

    def test_entity_type_is_measurement(self, generated: GeneratedDocument) -> None:
        """PlacedValue.entity_type for building_height must be MEASUREMENT."""
        pv = next(
            p for p in generated.placed_values if p.attribute == "building_height"
        )
        assert pv.entity_type == EntityType.MEASUREMENT

    def test_placed_value_page_is_one(self, generated: GeneratedDocument) -> None:
        """A single-page PNG must record page == 1 for all placed values."""
        for pv in generated.placed_values:
            assert pv.page == 1


# ---------------------------------------------------------------------------
# Test: determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Identical seed must produce byte-identical output."""

    def test_same_seed_same_bytes(self, generator: ElevationGenerator) -> None:
        """Two calls with the same seed must return identical PNG bytes.

        # WHY: Determinism is critical for the evaluation harness — regenerating
        # a corpus member must always yield the same file so diffs are meaningful.
        """
        scenario = _make_scenario(seed=99)
        doc_spec = _make_doc_spec()
        doc1 = generator.generate(scenario, doc_spec, seed=99)
        doc2 = generator.generate(scenario, doc_spec, seed=99)
        assert doc1.content_bytes == doc2.content_bytes

    def test_different_seeds_differ(self, generator: ElevationGenerator) -> None:
        """Two calls with different seeds should produce different images."""
        scenario1 = _make_scenario(seed=1)
        scenario2 = _make_scenario(seed=2)
        doc_spec = _make_doc_spec()
        doc1 = generator.generate(scenario1, doc_spec, seed=1)
        doc2 = generator.generate(scenario2, doc_spec, seed=2)
        # WHY: Different seeds may choose different roof styles or layout
        # variations; the images should not be identical.
        assert doc1.content_bytes != doc2.content_bytes


# ---------------------------------------------------------------------------
# Test: Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    """ElevationGenerator must satisfy the DocumentGenerator Protocol."""

    def test_is_document_generator(self, generator: ElevationGenerator) -> None:
        """isinstance check via runtime_checkable Protocol must succeed."""
        from planproof.datagen.rendering.registry import DocumentGenerator

        assert isinstance(generator, DocumentGenerator)
