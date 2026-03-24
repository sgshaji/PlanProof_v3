"""Core entity schemas for PlanProof extraction pipeline.

These models represent the fundamental data types that flow through every layer
of the system — from raw OCR output through to final compliance verdicts.
Defined in Section 0.4 of the implementation plan.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EntityType(StrEnum):
    """Categories of information extracted from planning documents."""

    ADDRESS = "ADDRESS"
    MEASUREMENT = "MEASUREMENT"
    CERTIFICATE = "CERTIFICATE"
    BOUNDARY = "BOUNDARY"
    ZONE = "ZONE"
    OWNERSHIP = "OWNERSHIP"


class ExtractionMethod(StrEnum):
    """How an entity was extracted from a source document.

    # WHY: Tracking extraction method enables confidence calibration —
    # different methods have different error profiles, and the confidence
    # gating layer uses this to apply method-specific thresholds.
    """

    OCR_LLM = "OCR_LLM"
    VLM_ZEROSHOT = "VLM_ZEROSHOT"
    VLM_STRUCTURED = "VLM_STRUCTURED"
    VLM_FINETUNED = "VLM_FINETUNED"
    MANUAL = "MANUAL"


class DocumentType(StrEnum):
    """Classification of planning application documents."""

    FORM = "FORM"
    DRAWING = "DRAWING"
    REPORT = "REPORT"
    CERTIFICATE = "CERTIFICATE"
    OTHER = "OTHER"


class BoundingBox(BaseModel):
    """Spatial region within a document page.

    # WHY: Bounding boxes enable spatial grounding — linking extracted values
    # back to their exact location in the source document, which is critical
    # for audit trails and conflict resolution when the same attribute appears
    # in multiple places.
    """

    x: float
    y: float
    width: float
    height: float
    page: int

    model_config = {"from_attributes": True}


class RawTextResult(BaseModel):
    """Output from the text extraction step before entity parsing."""

    text: str
    source_document: str
    source_pages: list[int]
    extraction_method: str

    model_config = {"from_attributes": True}


class ClassifiedDocument(BaseModel):
    """A document that has been classified into a known type."""

    file_path: str
    doc_type: DocumentType
    confidence: float = Field(ge=0, le=1)

    model_config = {"from_attributes": True}


class ExtractedEntity(BaseModel):
    """A single piece of evidence extracted from a planning document.

    This is the primary unit of evidence that flows through reconciliation,
    assessability checking, and rule evaluation.
    """

    entity_type: EntityType
    value: Any
    unit: str | None = None
    # WHY: Confidence is bounded [0, 1] so downstream gating logic can apply
    # method-specific thresholds without worrying about unbounded scores.
    confidence: float = Field(ge=0, le=1)
    source_document: str
    source_page: int | None = None
    source_region: BoundingBox | None = None
    extraction_method: ExtractionMethod
    timestamp: datetime

    model_config = {"from_attributes": True}
