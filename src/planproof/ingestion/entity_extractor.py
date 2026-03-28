"""LLM-based structured entity extraction from raw text.

Implements the ``EntityExtractor`` Protocol — takes raw text and produces
structured ``ExtractedEntity`` objects via LLM with prompt templates.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
    RawTextResult,
)

logger = get_logger(__name__)

DEFAULT_CONFIDENCE: dict[str, float] = {
    "ADDRESS": 0.85,
    "MEASUREMENT": 0.80,
    "CERTIFICATE": 0.90,
    "BOUNDARY": 0.75,
    "ZONE": 0.85,
    "OWNERSHIP": 0.80,
}

DOC_TYPE_TO_TEMPLATE: dict[str, str] = {
    "FORM": "form_extraction",
    "REPORT": "report_extraction",
    "CERTIFICATE": "certificate_extraction",
    "DRAWING": "drawing_extraction",
}


class LLMEntityExtractor:
    """Extract structured entities from raw text using an LLM.

    Uses prompt templates loaded from YAML files and parses the LLM's JSON
    response into validated ``ExtractedEntity`` objects.
    """

    def __init__(
        self,
        llm: Any,
        prompts_dir: Path,
        model: str = "llama-3.1-70b-versatile",
        doc_type: str = "FORM",
    ) -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)
        self._model = model
        self._doc_type = doc_type

    def extract_entities(
        self, text: RawTextResult, doc_type: str | None = None
    ) -> list[ExtractedEntity]:
        """Extract entities from raw text via LLM completion.

        Args:
            text: The raw text result from the text extraction step.
            doc_type: Optional override for the document type (determines
                which prompt template to use).

        Returns:
            A list of extracted entities, or an empty list on failure.
        """
        effective_type = doc_type or self._doc_type
        template_name = DOC_TYPE_TO_TEMPLATE.get(effective_type, "form_extraction")

        try:
            template = self._loader.load(template_name)
        except FileNotFoundError:
            logger.warning(
                "prompt_template_missing",
                template=template_name,
                fallback="form_extraction",
            )
            template = self._loader.load("form_extraction")

        prompt = template.render(text=text.text)
        doc_hash = hashlib.sha256(text.text.encode("utf-8")).hexdigest()

        try:
            response = self._llm.complete(
                prompt=prompt, model=self._model, doc_hash=doc_hash
            )
        except Exception as e:
            logger.error("llm_call_failed", error=str(e))
            return []

        return self._parse_response(response, text)

    def _parse_response(
        self, response: str, source: RawTextResult
    ) -> list[ExtractedEntity]:
        """Parse LLM JSON response into ExtractedEntity objects."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "llm_json_parse_failed",
                error=str(e),
                response_preview=response[:200],
            )
            return []

        raw_entities: list[dict[str, Any]] = data.get("entities", [])
        entities: list[ExtractedEntity] = []
        now = datetime.now(UTC)

        for raw in raw_entities:
            try:
                entity_type_str = raw.get("entity_type", "")
                entity_type = EntityType(entity_type_str)
                confidence = DEFAULT_CONFIDENCE.get(entity_type_str, 0.70)

                entity = ExtractedEntity(
                    entity_type=entity_type,
                    attribute=raw.get("attribute"),
                    value=raw.get("value"),
                    unit=raw.get("unit"),
                    confidence=confidence,
                    source_document=source.source_document,
                    source_page=raw.get("source_page"),
                    source_region=None,
                    extraction_method=ExtractionMethod.OCR_LLM,
                    timestamp=now,
                )
                entities.append(entity)
            except (ValueError, KeyError) as e:
                logger.warning("entity_parse_skipped", error=str(e), raw=raw)
                continue

        logger.info(
            "entities_extracted", count=len(entities), source=source.source_document
        )
        return entities
