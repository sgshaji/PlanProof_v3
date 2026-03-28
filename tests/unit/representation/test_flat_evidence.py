"""Tests for FlatEvidenceProvider (Ablation B)."""
from __future__ import annotations

from datetime import datetime

from planproof.representation.flat_evidence import FlatEvidenceProvider
from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)


def _make_entity(
    entity_type: EntityType = EntityType.MEASUREMENT,
    value: object = 7.5,
    source_document: str = "doc_a.pdf",
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        confidence=0.9,
        source_document=source_document,
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=datetime(2024, 1, 1),
    )


class TestGetEvidenceForRule:
    def test_returns_all_entities_regardless_of_rule_id(self) -> None:
        entities = [_make_entity(), _make_entity(value=8.0)]
        provider = FlatEvidenceProvider(entities)
        result = provider.get_evidence_for_rule("rule_height_001")
        assert result == entities

    def test_different_rule_ids_return_same_full_list(self) -> None:
        entities = [
            _make_entity(),
            _make_entity(entity_type=EntityType.ADDRESS, value="1 Main St"),
        ]
        provider = FlatEvidenceProvider(entities)
        assert provider.get_evidence_for_rule("rule_a") == entities
        assert provider.get_evidence_for_rule("rule_b") == entities

    def test_empty_entities_returns_empty_list(self) -> None:
        provider = FlatEvidenceProvider([])
        result = provider.get_evidence_for_rule("any_rule")
        assert result == []


class TestGetConflictingEvidence:
    def test_finds_conflict_same_type_different_value_different_source(self) -> None:
        entity_a = _make_entity(
            entity_type=EntityType.MEASUREMENT, value=7.5, source_document="doc_a.pdf"
        )
        entity_b = _make_entity(
            entity_type=EntityType.MEASUREMENT, value=9.0, source_document="doc_b.pdf"
        )
        provider = FlatEvidenceProvider([entity_a, entity_b])

        conflicts = provider.get_conflicting_evidence("MEASUREMENT")
        assert len(conflicts) == 1
        pair = conflicts[0]
        assert entity_a in pair and entity_b in pair

    def test_no_conflict_when_values_agree(self) -> None:
        entity_a = _make_entity(value=7.5, source_document="doc_a.pdf")
        entity_b = _make_entity(value=7.5, source_document="doc_b.pdf")
        provider = FlatEvidenceProvider([entity_a, entity_b])

        conflicts = provider.get_conflicting_evidence("MEASUREMENT")
        assert conflicts == []

    def test_no_conflict_when_same_source_document(self) -> None:
        entity_a = _make_entity(value=7.5, source_document="doc_a.pdf")
        entity_b = _make_entity(value=9.0, source_document="doc_a.pdf")
        provider = FlatEvidenceProvider([entity_a, entity_b])

        conflicts = provider.get_conflicting_evidence("MEASUREMENT")
        assert conflicts == []

    def test_no_conflict_when_different_entity_types(self) -> None:
        entity_a = _make_entity(
            entity_type=EntityType.MEASUREMENT, value=7.5, source_document="doc_a.pdf"
        )
        entity_b = _make_entity(
            entity_type=EntityType.ADDRESS, value=7.5, source_document="doc_b.pdf"
        )
        provider = FlatEvidenceProvider([entity_a, entity_b])

        # attribute filter applies only to MEASUREMENT; ADDRESS entity excluded
        conflicts = provider.get_conflicting_evidence("MEASUREMENT")
        assert conflicts == []

    def test_empty_entities_returns_empty_conflicts(self) -> None:
        provider = FlatEvidenceProvider([])
        assert provider.get_conflicting_evidence("MEASUREMENT") == []

    def test_single_entity_returns_no_conflicts(self) -> None:
        provider = FlatEvidenceProvider([_make_entity()])
        assert provider.get_conflicting_evidence("MEASUREMENT") == []

    def test_multiple_conflicts_found(self) -> None:
        entity_a = _make_entity(value=7.5, source_document="doc_a.pdf")
        entity_b = _make_entity(value=9.0, source_document="doc_b.pdf")
        entity_c = _make_entity(value=10.0, source_document="doc_c.pdf")
        provider = FlatEvidenceProvider([entity_a, entity_b, entity_c])

        conflicts = provider.get_conflicting_evidence("MEASUREMENT")
        # 3 pairs: (a,b), (a,c), (b,c) — all different values, different sources
        assert len(conflicts) == 3

    def test_attribute_filter_uses_entity_type_string(self) -> None:
        entity_a = _make_entity(
            entity_type=EntityType.ADDRESS, value="1 Main", source_document="doc_a.pdf"
        )
        entity_b = _make_entity(
            entity_type=EntityType.ADDRESS, value="2 High", source_document="doc_b.pdf"
        )
        entity_c = _make_entity(
            entity_type=EntityType.MEASUREMENT, value=7.5, source_document="doc_c.pdf"
        )
        provider = FlatEvidenceProvider([entity_a, entity_b, entity_c])

        conflicts = provider.get_conflicting_evidence("ADDRESS")
        assert len(conflicts) == 1
        assert entity_a in conflicts[0] and entity_b in conflicts[0]
