"""VLM-based spatial attribute extraction from architectural drawing images."""
from __future__ import annotations

import base64
import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

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
    "pdf": "pdf",
}

_PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})


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
        """Extract spatial entities from an image or PDF drawing.

        For PDF files, each page is converted to a PNG image using pdfplumber
        and sent to the VLM individually. Results from all pages are merged.

        Raises:
            FileNotFoundError: if *image* does not exist on disk.
        """
        if not image.exists():
            msg = f"Image not found: {image}"
            raise FileNotFoundError(msg)

        # Handle PDF drawings by converting pages to images
        if image.suffix.lower() in _PDF_EXTENSIONS:
            return self._extract_from_pdf(image)

        subtype = self._infer_subtype(image)

        if self._method == "zeroshot":
            return self._zeroshot_path(image, subtype)

        return self._structured_path(image, subtype)

    def _extract_from_pdf(self, pdf_path: Path) -> list[ExtractedEntity]:
        """Convert each PDF page to an image and run VLM extraction."""
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not available for PDF→image conversion")
            return []

        all_entities: list[ExtractedEntity] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        # Convert page to PIL Image
                        pil_image = page.to_image(resolution=150).original

                        # Save to temp PNG
                        with tempfile.NamedTemporaryFile(
                            suffix=".png", delete=False
                        ) as tmp:
                            tmp_path = Path(tmp.name)

                        try:
                            pil_image.save(tmp_path, format="PNG")
                            subtype = self._infer_subtype(pdf_path)

                            if self._method == "zeroshot":
                                entities = self._zeroshot_path(tmp_path, subtype)
                            else:
                                entities = self._structured_path(tmp_path, subtype)

                            # Fix source_document to point to original PDF
                            for entity in entities:
                                object.__setattr__(entity, "source_document", str(pdf_path))
                                object.__setattr__(entity, "source_page", page_num)

                            all_entities.extend(entities)
                        finally:
                            tmp_path.unlink(missing_ok=True)

                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "vlm_pdf_page_failed",
                            page=page_num,
                            path=str(pdf_path),
                            error=str(exc),
                        )
                        continue

        except Exception as exc:  # noqa: BLE001
            logger.error("vlm_pdf_open_failed", path=str(pdf_path), error=str(exc))

        return all_entities

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
    ) -> list[ExtractedEntity]:
        # Stage 1: detect regions of interest
        stage1_template = self._loader.load("spatial_structured_stage1")
        user_text = stage1_template.user_message_template.format(subtype=subtype.value)
        messages = self._build_vision_messages(
            system=stage1_template.system_message,
            user_text=user_text,
            image_path=image,
        )
        stage1_response = self._call_vision(messages)
        if stage1_response is None:
            return []

        regions = self._parse_regions(stage1_response)
        if not regions:
            return []

        # Stage 2: extract values from each region crop
        pil_image = Image.open(image)
        stage2_template = self._loader.load("spatial_structured_stage2")
        entities: list[ExtractedEntity] = []

        for region_dict in regions:
            attribute: str = region_dict.get("attribute", "")
            region: dict[str, Any] = region_dict.get("region", {})
            rx = int(region.get("x", 0))
            ry = int(region.get("y", 0))
            rw = int(region.get("width", 0))
            rh = int(region.get("height", 0))

            crop = pil_image.crop((rx, ry, rx + rw, ry + rh))

            with tempfile.NamedTemporaryFile(suffix=image.suffix, delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                crop.save(tmp_path)
                user_text2 = stage2_template.user_message_template.format(
                    attribute=attribute
                )
                messages2 = self._build_vision_messages(
                    system=stage2_template.system_message,
                    user_text=user_text2,
                    image_path=tmp_path,
                )
                stage2_response = self._call_vision(messages2)
                if stage2_response is None:
                    continue
                entity = self._parse_single_entity(
                    response=stage2_response,
                    source_document=str(image),
                    region_x=rx,
                    region_y=ry,
                    method=ExtractionMethod.VLM_STRUCTURED,
                )
                if entity is not None:
                    entities.append(entity)
            finally:
                tmp_path.unlink(missing_ok=True)

        return entities

    # ------------------------------------------------------------------
    # Structured path helpers
    # ------------------------------------------------------------------

    def _parse_regions(self, response: str) -> list[dict[str, Any]]:
        """Parse stage-1 JSON response and return the regions list."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            data: dict[str, Any] = json.loads(cleaned)
            regions: list[dict[str, Any]] = data.get("regions", [])
            return regions
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "vlm_structured_stage1_parse_failed",
                error=str(exc),
                response_preview=response[:200],
            )
            return []

    def _parse_single_entity(
        self,
        response: str,
        source_document: str,
        region_x: int,
        region_y: int,
        method: ExtractionMethod,
    ) -> ExtractedEntity | None:
        """Parse a single-entity JSON from stage-2 response.

        Adjusts the bounding box coordinates to global image coords by adding
        the region's x, y offset.
        """
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            raw: dict[str, Any] = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "vlm_structured_stage2_parse_failed",
                error=str(exc),
                response_preview=response[:200],
            )
            return None

        try:
            entity_type = EntityType(raw.get("entity_type", ""))
            confidence = _DEFAULT_CONFIDENCE.get(entity_type, 0.70)

            source_region: BoundingBox | None = None
            bbox_raw: dict[str, Any] | None = raw.get("bounding_box")
            if bbox_raw:
                source_region = BoundingBox(
                    x=float(bbox_raw["x"]) + region_x,
                    y=float(bbox_raw["y"]) + region_y,
                    width=float(bbox_raw["width"]),
                    height=float(bbox_raw["height"]),
                    page=int(raw.get("source_page", 1)),
                )

            return ExtractedEntity(
                entity_type=entity_type,
                attribute=raw.get("attribute"),
                value=raw.get("value"),
                unit=raw.get("unit"),
                confidence=confidence,
                source_document=source_document,
                source_page=raw.get("source_page"),
                source_region=source_region,
                extraction_method=method,
                timestamp=datetime.now(UTC),
            )
        except (ValueError, KeyError) as exc:
            logger.warning(
                "vlm_structured_entity_parse_skipped",
                error=str(exc),
                raw=raw,
            )
            return None

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
                    attribute=raw.get("attribute"),
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
