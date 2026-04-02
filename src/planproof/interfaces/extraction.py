"""Protocols for document ingestion and entity extraction (Layer 1)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from planproof.schemas.entities import (
    ClassifiedDocument,
    ExtractedEntity,
    RawTextResult,
)


@runtime_checkable
class DocumentClassifier(Protocol):
    """Contract: determine document type (e.g. site-plan, SOE, DA report)."""

    def classify(self, file_path: Path) -> ClassifiedDocument: ...


@runtime_checkable
class OCRExtractor(Protocol):
    """Contract: convert PDF/image bytes to raw text."""

    def extract_text(self, document: Path) -> RawTextResult: ...


@runtime_checkable
class EntityExtractor(Protocol):
    """Contract: convert raw text into structured entities via LLM."""

    def extract_entities(self, text: RawTextResult) -> list[ExtractedEntity]: ...


@runtime_checkable
class VLMExtractor(Protocol):
    """Contract: extract spatial attributes from architectural drawings."""

    def extract_spatial_attributes(self, image: Path) -> list[ExtractedEntity]: ...
