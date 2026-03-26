"""GPT-4o vision-based entity extraction from document images."""
from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod

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


class VisionExtractor:
    """Extract structured entities from document images via GPT-4o vision."""

    def __init__(
        self,
        openai_client: Any,
        prompts_dir: Path,
        model: str = "gpt-4o",
    ) -> None:
        self._client = openai_client
        self._loader = PromptLoader(prompts_dir)
        self._model = model

    def extract_from_image(
        self,
        image_path: Path,
        doc_type: str = "DRAWING",
    ) -> list[ExtractedEntity]:
        """Send *image_path* to the vision model and return parsed entities."""
        if not image_path.exists():
            msg = f"Image not found: {image_path}"
            raise FileNotFoundError(msg)

        template_name = DOC_TYPE_TO_TEMPLATE.get(doc_type, "drawing_extraction")
        try:
            template = self._loader.load(template_name)
        except FileNotFoundError:
            template = self._loader.load("drawing_extraction")

        image_bytes = image_path.read_bytes()
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        suffix = image_path.suffix.lower().lstrip(".")
        mime_map = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "tiff": "tiff"}
        mime_type = f"image/{mime_map.get(suffix, 'png')}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": template.system_message},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract all structured entities from this document "
                            "image. Respond with valid JSON containing an "
                            "'entities' array."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}",
                        },
                    },
                ],
            },
        ]

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                max_tokens=4096,
            )
            content: str = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            logger.error("vision_api_failed", error=str(exc), path=str(image_path))
            return []

        return self._parse_response(content, str(image_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        response: str,
        source_document: str,
    ) -> list[ExtractedEntity]:
        """Turn the raw JSON string from the LLM into entity objects."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "vision_json_parse_failed",
                error=str(exc),
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
                    value=raw.get("value"),
                    unit=raw.get("unit"),
                    confidence=confidence,
                    source_document=source_document,
                    source_page=raw.get("source_page"),
                    source_region=None,
                    extraction_method=ExtractionMethod.OCR_LLM,
                    timestamp=now,
                )
                entities.append(entity)
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "vision_entity_parse_skipped",
                    error=str(exc),
                    raw=raw,
                )
                continue

        logger.info(
            "vision_entities_extracted",
            count=len(entities),
            source=source_document,
        )
        return entities
