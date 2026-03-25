"""Tests for the DocumentGenerator protocol and DocumentGeneratorRegistry.

# WHY: The registry is the single integration point between the scenario layer
# and the format-specific rendering plugins.  Testing it in isolation (with
# lightweight stub generators) keeps tests fast and independent of any PDF or
# image library.
"""
from __future__ import annotations

import pytest

from planproof.datagen.rendering.registry import (
    DocumentGenerator,
    DocumentGeneratorRegistry,
)
from planproof.datagen.rendering.models import GeneratedDocument
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict
from planproof.schemas.entities import DocumentType


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _make_minimal_scenario(seed: int = 42) -> Scenario:
    """Return the smallest valid Scenario for test purposes."""
    return Scenario(
        set_id="TEST_001",
        category="compliant",
        seed=seed,
        profile_id="minimal",
        difficulty="low",
        degradation_preset="clean",
        values=(Value(attribute="height", value=7.5, unit="m", display_text="7.5m"),),
        verdicts=(
            Verdict(rule_id="R001", outcome="PASS", evaluated_value=7.5, threshold=8.0),
        ),
        documents=(
            DocumentSpec(doc_type="FORM", file_format="pdf", values_to_place=("height",)),
        ),
        edge_case_strategy=None,
    )


def _make_minimal_doc_spec() -> DocumentSpec:
    return DocumentSpec(doc_type="FORM", file_format="pdf", values_to_place=("height",))


class StubFormGenerator:
    """Minimal Protocol-conforming generator that returns a canned document."""

    def generate(
        self, scenario: Scenario, doc_spec: DocumentSpec, seed: int
    ) -> GeneratedDocument:
        from planproof.datagen.rendering.models import PlacedValue
        from planproof.schemas.entities import BoundingBox, EntityType

        bb = BoundingBox(x=0.0, y=0.0, width=100.0, height=20.0, page=1)
        pv = PlacedValue(
            attribute="height",
            value=7.5,
            text_rendered="7.5m",
            page=1,
            bounding_box=bb,
            entity_type=EntityType.MEASUREMENT,
        )
        return GeneratedDocument(
            filename="test_form.pdf",
            doc_type=DocumentType.FORM,
            content_bytes=b"%PDF-stub",
            file_format="pdf",
            placed_values=(pv,),
        )


class StubDrawingGenerator:
    """Second stub for multi-type registration tests."""

    def generate(
        self, scenario: Scenario, doc_spec: DocumentSpec, seed: int
    ) -> GeneratedDocument:
        return GeneratedDocument(
            filename="test_drawing.pdf",
            doc_type=DocumentType.DRAWING,
            content_bytes=b"drawing-stub",
            file_format="pdf",
            placed_values=(),
        )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestRegisterAndGet:
    def test_register_and_get(self) -> None:
        """A registered generator can be retrieved by its DocumentType key."""
        registry = DocumentGeneratorRegistry()
        stub = StubFormGenerator()

        registry.register(DocumentType.FORM, stub)
        retrieved = registry.get(DocumentType.FORM)

        # WHY: Verify identity so we know the registry stores the exact object,
        # not a copy.  This is important for generators that carry config state.
        assert retrieved is stub

    def test_registered_generator_is_callable(self) -> None:
        """The retrieved generator must satisfy the DocumentGenerator protocol."""
        registry = DocumentGeneratorRegistry()
        registry.register(DocumentType.FORM, StubFormGenerator())

        gen = registry.get(DocumentType.FORM)
        scenario = _make_minimal_scenario()
        doc_spec = _make_minimal_doc_spec()

        result = gen.generate(scenario, doc_spec, seed=42)

        assert isinstance(result, GeneratedDocument)
        assert result.filename == "test_form.pdf"


class TestUnknownTypeRaisesKeyError:
    def test_unknown_type_raises_key_error(self) -> None:
        """Getting an unregistered DocumentType must raise KeyError."""
        # WHY: A silent None return would let callers proceed with no generator
        # and produce cryptic downstream errors.  Failing loudly at lookup time
        # makes the problem obvious and the call site clear.
        registry = DocumentGeneratorRegistry()

        with pytest.raises(KeyError):
            registry.get(DocumentType.REPORT)

    def test_empty_registry_raises_key_error(self) -> None:
        """Even with no registrations at all, KeyError must be raised."""
        registry = DocumentGeneratorRegistry()

        with pytest.raises(KeyError):
            registry.get(DocumentType.FORM)


class TestRegisterMultipleTypes:
    def test_register_multiple_types(self) -> None:
        """Multiple types can be registered and each resolves independently."""
        registry = DocumentGeneratorRegistry()
        form_gen = StubFormGenerator()
        drawing_gen = StubDrawingGenerator()

        registry.register(DocumentType.FORM, form_gen)
        registry.register(DocumentType.DRAWING, drawing_gen)

        assert registry.get(DocumentType.FORM) is form_gen
        assert registry.get(DocumentType.DRAWING) is drawing_gen

    def test_registering_second_type_does_not_affect_first(self) -> None:
        """Adding a new type must not overwrite or shadow an existing one."""
        registry = DocumentGeneratorRegistry()
        form_gen = StubFormGenerator()
        drawing_gen = StubDrawingGenerator()

        registry.register(DocumentType.FORM, form_gen)
        registry.register(DocumentType.DRAWING, drawing_gen)

        # Unregistered type still raises
        with pytest.raises(KeyError):
            registry.get(DocumentType.REPORT)

        # Existing registrations intact
        assert registry.get(DocumentType.FORM) is form_gen

    def test_overwrite_registration(self) -> None:
        """Re-registering a type replaces the previous generator."""
        registry = DocumentGeneratorRegistry()
        gen_v1 = StubFormGenerator()
        gen_v2 = StubFormGenerator()

        registry.register(DocumentType.FORM, gen_v1)
        registry.register(DocumentType.FORM, gen_v2)

        assert registry.get(DocumentType.FORM) is gen_v2
