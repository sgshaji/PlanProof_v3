"""Tests for entity schema models — round-trip serialisation and validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from planproof.schemas.entities import (
    BoundingBox,
    ClassifiedDocument,
    DocumentType,
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)


class TestExtractedEntity:
    """Tests for the ExtractedEntity Pydantic model."""

    def test_valid_entity_creation(self, sample_entity: ExtractedEntity) -> None:
        assert sample_entity.entity_type == EntityType.MEASUREMENT
        assert sample_entity.confidence == 0.85
        assert sample_entity.unit == "metres"

    def test_json_round_trip(self, sample_entity: ExtractedEntity) -> None:
        """Serialise to JSON and back — all fields must survive."""
        json_str = sample_entity.model_dump_json()
        restored = ExtractedEntity.model_validate_json(json_str)
        assert restored == sample_entity

    def test_dict_round_trip(self, sample_entity: ExtractedEntity) -> None:
        """Serialise to dict and back."""
        data = sample_entity.model_dump()
        restored = ExtractedEntity.model_validate(data)
        assert restored == sample_entity

    def test_confidence_must_be_between_0_and_1(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEntity(
                entity_type=EntityType.MEASUREMENT,
                value=7.5,
                unit="metres",
                confidence=1.5,  # Invalid: > 1.0
                source_document="test.pdf",
                source_page=1,
                source_region=None,
                extraction_method=ExtractionMethod.OCR_LLM,
                timestamp=datetime.now(UTC),
            )

    def test_confidence_zero_is_valid(self) -> None:
        """confidence=0.0 is valid — represents extraction failure."""
        entity = ExtractedEntity(
            entity_type=EntityType.MEASUREMENT,
            value=None,
            unit=None,
            confidence=0.0,
            source_document="test.pdf",
            source_page=None,
            source_region=None,
            extraction_method=ExtractionMethod.VLM_ZEROSHOT,
            timestamp=datetime.now(UTC),
        )
        assert entity.confidence == 0.0

    def test_optional_fields_can_be_none(self) -> None:
        entity = ExtractedEntity(
            entity_type=EntityType.ADDRESS,
            value="BS1 1AA",
            unit=None,
            confidence=0.9,
            source_document="form.pdf",
            source_page=None,
            source_region=None,
            extraction_method=ExtractionMethod.OCR_LLM,
            timestamp=datetime.now(UTC),
        )
        assert entity.source_page is None
        assert entity.source_region is None
        assert entity.unit is None


class TestClassifiedDocument:
    def test_valid_creation(
        self, sample_classified_doc: ClassifiedDocument
    ) -> None:
        assert sample_classified_doc.doc_type == DocumentType.FORM

    def test_json_round_trip(
        self, sample_classified_doc: ClassifiedDocument
    ) -> None:
        json_str = sample_classified_doc.model_dump_json()
        restored = ClassifiedDocument.model_validate_json(json_str)
        assert restored == sample_classified_doc


class TestBoundingBox:
    def test_valid_creation(self) -> None:
        bb = BoundingBox(x=10.0, y=20.0, width=100.0, height=50.0, page=1)
        assert bb.page == 1

    def test_json_round_trip(self) -> None:
        bb = BoundingBox(x=0, y=0, width=50, height=50, page=0)
        restored = BoundingBox.model_validate_json(bb.model_dump_json())
        assert restored == bb
