"""Rendering output models — immutable records of what was placed and where.

# DESIGN: These dataclasses are the bridge between the scenario layer (which
# describes *what* to generate) and the evaluation layer (which checks *what
# was extracted*).  By recording every placed value alongside its bounding box
# at generation time, the evaluation harness can directly compare OCR/VLM
# output against ground truth without re-parsing the document.  Frozen
# dataclasses with tuple collections ensure the ground-truth corpus is never
# mutated after generation, preventing silent data corruption in long pipeline
# runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from planproof.schemas.entities import BoundingBox, DocumentType, EntityType


@dataclass(frozen=True)
class PlacedValue:
    """A single value that was physically rendered onto a document page.

    # WHY: Storing the rendered text alongside the canonical value lets the
    # evaluation layer detect cases where OCR extracted the display string
    # correctly but the parser failed to convert it to the numeric value.
    # The bounding_box gives a pixel-precise location (300 DPI, top-left
    # origin) so the evaluation harness can crop the exact region and feed it
    # directly to a VLM for targeted re-extraction if the main pipeline fails.

    # DESIGN: `value` is typed `Any` because the scenario layer allows strings,
    # floats, ints, and structured objects (e.g. address dicts).  Downstream
    # consumers should cast to the expected type using entity_type as a hint
    # rather than relying on isinstance checks here.
    """

    # The canonical attribute name, matching Value.attribute in the scenario.
    attribute: str
    # The ground-truth value in its native Python type (float, str, dict, …).
    value: Any
    # The exact text string as rendered into the document (e.g. "7.5m").
    # May differ from str(value) due to formatting, locale, or abbreviation.
    text_rendered: str
    # 1-based page number on which this value was placed.
    page: int
    # Pixel-space bounding box at CANONICAL_DPI (300 DPI), origin top-left.
    # WHY: All bounding boxes use a single unified coordinate system so the
    # evaluation harness never needs to know the source document format.
    bounding_box: BoundingBox
    # Entity category that classifies this value for extraction routing.
    entity_type: EntityType


@dataclass(frozen=True)
class GeneratedDocument:
    """A fully rendered document and its complete ground-truth placement record.

    # WHY: Bundling content_bytes with placed_values in one immutable object
    # means a generator always returns a self-describing artefact.  The caller
    # never has to correlate a file on disk with a separate metadata store —
    # the ground truth travels with the bytes, which is critical for
    # reproducibility when generating large corpora in parallel.

    # DESIGN: `content_bytes` holds the raw file content (PDF bytes, PNG bytes,
    # etc.) rather than a file path so this model is storage-agnostic.  Writers
    # that need to persist to disk should extract the bytes and derive the path
    # from `filename` themselves, keeping I/O concerns outside this model.
    """

    # Suggested output filename (e.g. "SET_C001_form.pdf").
    filename: str
    # Document category, matching the DocumentType enum.
    doc_type: DocumentType
    # Raw file bytes ready for writing to disk or passing to an ingestion step.
    content_bytes: bytes
    # Lowercase format identifier (e.g. "pdf", "png", "tiff").
    file_format: str
    # Ordered record of every value placed in this document.
    # Using tuple (not list) preserves deep immutability of the frozen dataclass.
    placed_values: tuple[PlacedValue, ...]
