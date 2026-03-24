"""Shared test fixtures for PlanProof."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from planproof.schemas.entities import (
    BoundingBox,
    ClassifiedDocument,
    DocumentType,
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)


@pytest.fixture
def sample_entity() -> ExtractedEntity:
    """A valid ExtractedEntity for testing."""
    return ExtractedEntity(
        entity_type=EntityType.MEASUREMENT,
        value=7.5,
        unit="metres",
        confidence=0.85,
        source_document="test_doc.pdf",
        source_page=1,
        source_region=BoundingBox(x=10, y=20, width=100, height=50, page=1),
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_classified_doc() -> ClassifiedDocument:
    """A valid ClassifiedDocument for testing."""
    return ClassifiedDocument(
        file_path="test_form.pdf",
        doc_type=DocumentType.FORM,
        confidence=0.95,
    )
