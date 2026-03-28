"""VLM-based spatial attribute extraction from architectural drawing images."""
from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.schemas.entities import (
    BoundingBox,
    DrawingSubtype,
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)

logger = get_logger(__name__)

# Default confidence scores per entity type for the zero-shot path
_DEFAULT_CONFIDENCE: dict[str, float] = {
    EntityType.MEASUREMENT: 0.75,
    EntityType.BOUNDARY: 0.70,
}

# Ordered list of (pattern, subtype) — first match wins
_SUBTYPE_PATTERNS: list[tuple[str, DrawingSubtype]] = [
    (r"(?i)elevation", DrawingSubtype.ELEVATION),
    (r"(?i)site.?plan", DrawingSubtype.SITE_PLAN),
    (r"(?i)floor.?plan", DrawingSubtype.FLOOR_PLAN),
]

_MIME_MAP: dict[str, str] = {
    "png": "png",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "tiff": "tiff",
}


class VLMSpatialExtractor:
    """Extract spatial attributes from architectural drawings.

    Implements the VLMExtractor Protocol. Supports two extraction strategies:

    * ``zeroshot``  — single-shot GPT-4o call with the ``spatial_zeroshot`` prompt.
    * ``structured`` — two-stage pipeline (not yet implemented; Task 4).
    """

    def __init__(
        self,
        openai_client: Any,
        prompts_dir: Path,
        model: str = "gpt-4o",
        method: str = "zeroshot",
    ) -> None:
        self._client = openai_client
        self._loader = PromptLoader(prompts_dir)
        self._model = model
        self._method = method

    # ------------------------------------------------------------------
    # Public API (VLMExtractor Protocol)
    # ------------------------------------------------------------------

    def extract_spatial_attributes(self, image: Path) -> list[ExtractedEntity]:
        """Extract spatial entities from *image*.

        Raises:
            FileNotFoundError: if *image* does not exist on disk.
        """
        if not image.exists():
            msg = f"Image not found: {image}"
            raise FileNotFoundError(msg)

        subtype = self._infer_subtype(image)

        if self._method == "zeroshot":
            return self._zeroshot_path(image, subtype)

        return self._structured_path(image, subtype)

    # ------------------------------------------------------------------
    # Subtype inference
    # ------------------------------------------------------------------

    def _infer_subtype(self, image: Path) -> DrawingSubtype:
        """Return DrawingSubtype inferred from the filename."""
        stem = image.name
        for pattern, subtype in _SUBTYPE_PATTERNS:
            if re.search(pattern, stem):
                return subtype
        return DrawingSubtype.OTHER_DRAWING

    # ------------------------------------------------------------------
    # Zero-shot extraction path
    # ------------------------------------------------------------------

    def _zeroshot_path(
        self, image: Path, subtype: DrawingSubtype
    ) -> list[ExtractedEntity]:
        template = self._loader.load("spatial_zeroshot")
        user_text = template.user_message_template.format(subtype=subtype.value)
        messages = self._build_vision_messages(
            system=template.system_message,
            user_text=user_text,
            image_path=image,
        )
        response = self._call_vision(messages)
        if response is None:
            return []
        return self._parse_entities(
            response=response,
            source_document=str(image),
            method=ExtractionMethod.VLM_ZEROSHOT,
        )

    # ------------------------------------------------------------------
    # Structured two-stage path (Task 4)
    # ------------------------------------------------------------------

    def _structured_path(
        self, image: Path, subtype: DrawingSubtype
    ) -> list[ExtractedEntity]:  # pragma: no cover
        raise NotImplementedError("Structured path will be implemented in Task 4")

    # ------------------------------------------------------------------
    # Vision API helpers
    # ------------------------------------------------------------------

    def _build_vision_messages(
        self,
        system: str,
        user_text: str,
        image_path: Path,
    ) -> list[dict[str, Any]]:
        """Build the messages list for a vision chat completion call."""
        image_bytes = image_path.read_bytes()
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        suffix = image_path.suffix.lower().lstrip(".")
        mime_type = f"image/{_MIME_MAP.get(suffix, 'png')}"

        return [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}",
                        },
                    },
                ],
            },
        ]

    def _call_vision(self, messages: list[dict[str, Any]]) -> str | None:
        """Send messages to the vision model and return the raw text response."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                max_tokens=4096,
            )
            content: str = response.choices[0].message.content or ""
            return content
        except Exception as exc:  # noqa: BLE001
            logger.error("vlm_spatial_api_failed", error=str(exc))
            return None

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_entities(
        self,
        response: str,
        source_document: str,
        method: ExtractionMethod,
    ) -> list[ExtractedEntity]:
        """Parse the raw JSON string from the LLM into ExtractedEntity objects."""
        try:
            cleaned = response.strip()
            # Strip markdown code fences if present
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "vlm_spatial_json_parse_failed",
                error=str(exc),
                response_preview=response[:200],
            )
            return []

        raw_entities: list[dict[str, Any]] = data.get("entities", [])
        entities: list[ExtractedEntity] = []
        now = datetime.now(UTC)

        for raw in raw_entities:
            try:
                entity_type_str: str = raw.get("entity_type", "")
                entity_type = EntityType(entity_type_str)
                confidence = _DEFAULT_CONFIDENCE.get(entity_type, 0.70)

                # Build BoundingBox from the optional bounding_box field
                source_region: BoundingBox | None = None
                bbox_raw: dict[str, Any] | None = raw.get("bounding_box")
                if bbox_raw:
                    source_region = BoundingBox(
                        x=float(bbox_raw["x"]),
                        y=float(bbox_raw["y"]),
                        width=float(bbox_raw["width"]),
                        height=float(bbox_raw["height"]),
                        page=int(raw.get("source_page", 1)),
                    )

                entity = ExtractedEntity(
                    entity_type=entity_type,
                    value=raw.get("value"),
                    unit=raw.get("unit"),
                    confidence=confidence,
                    source_document=source_document,
                    source_page=raw.get("source_page"),
                    source_region=source_region,
                    extraction_method=method,
                    timestamp=now,
                )
                entities.append(entity)
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "vlm_spatial_entity_parse_skipped",
                    error=str(exc),
                    raw=raw,
                )
                continue

        logger.info(
            "vlm_spatial_entities_extracted",
            count=len(entities),
            source=source_document,
            method=method,
        )
        return entities
