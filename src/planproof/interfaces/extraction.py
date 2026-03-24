"""Protocols for document ingestion and entity extraction (Layer 1)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from planproof.schemas.entities import (
    ClassifiedDocument,
    ExtractedEntity,
    RawTextResult,
)


class DocumentClassifier(Protocol):
    """Contract: determine document type (e.g. site-plan, SOE, DA report)."""

    def classify(self, file_path: Path) -> ClassifiedDocument: ...


class OCRExtractor(Protocol):
    """Contract: convert PDF/image bytes to raw text."""

    def extract_text(self, document: Path) -> RawTextResult: ...


class EntityExtractor(Protocol):
    """Contract: convert raw text into structured entities via LLM."""

    def extract_entities(self, text: RawTextResult) -> list[ExtractedEntity]: ...


class VLMExtractor(Protocol):
    """Contract: extract spatial attributes from architectural drawings."""

    def extract_spatial_attributes(self, image: Path) -> list[ExtractedEntity]: ...
