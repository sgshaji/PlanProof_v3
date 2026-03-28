"""Sidecar writer — assembles and persists ground_truth.json for one application set.

The ground_truth.json file is the primary evaluation artefact.  It contains
everything the rule engine needs to verify an extraction pipeline run:
  - set metadata (set_id, category, seed, difficulty)
  - ground-truth values (attribute, numeric value, unit, display text)
  - expected rule verdicts (rule_id, outcome, evaluated_value, threshold)
  - per-document extraction records (filename, doc_type, placed values + bboxes)
  - degradation parameters applied to this set

# DESIGN: This module is a pure I/O adapter — it has no business logic.  The
# Scenario and GeneratedDocument objects carry all the facts; this module's job
# is to project those facts into the JSON schema defined in spec Section 7 and
# write the result to disk.
#
# WHY a dedicated writer module rather than embedding serialisation in the models:
# keeping I/O out of domain models lets the models be used in memory-only
# pipelines (e.g. unit tests) without triggering file system side-effects.
# The writer is the single place that knows the on-disk format, which makes
# format changes easy to locate and review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from planproof.datagen.rendering.models import GeneratedDocument
from planproof.datagen.scenario.models import Scenario


def _serialise_bounding_box(bbox: object) -> dict[str, Any]:
    """Convert a BoundingBox to a plain dict for JSON serialisation.

    # WHY: BoundingBox is a Pydantic model — we use model_dump() to get a
    # plain dict instead of calling vars() or __dict__, which may include
    # Pydantic internals.  This keeps the output format stable even if the
    # Pydantic model gains new internal attributes.
    """
    # BoundingBox is a Pydantic BaseModel, so model_dump() is available.
    return cast(dict[str, Any], bbox.model_dump())  # type: ignore[attr-defined]


def _serialise_placed_value(pv: object) -> dict[str, Any]:
    """Convert a PlacedValue to a ground-truth extraction record dict.

    # WHY: PlacedValue is a frozen dataclass (not Pydantic), so we access
    # fields directly rather than calling model_dump().  The output schema
    # is a documented subset of PlacedValue fields — we don't expose the
    # entity_type here because the sidecar consumer only needs the spatial
    # and textual ground truth.
    """
    from planproof.datagen.rendering.models import PlacedValue

    assert isinstance(pv, PlacedValue)
    return {
        "attribute": pv.attribute,
        "value": pv.value,
        "text_rendered": pv.text_rendered,
        "page": pv.page,
        "bounding_box": _serialise_bounding_box(pv.bounding_box),
        "entity_type": pv.entity_type,  # StrEnum — serialises as its string value
    }


def _serialise_document(doc: GeneratedDocument) -> dict[str, Any]:
    """Convert a GeneratedDocument to its ground-truth document record.

    # WHY: We record both 'extractions' (original placed values before
    # degradation) and 'degraded_extractions' (adjusted bboxes after geometric
    # transforms).  In this writer we use the placed_values from the supplied
    # GeneratedDocument for both fields — bbox adjustment is the caller's
    # responsibility if needed.  This keeps the writer's contract narrow.
    #
    # DESIGN: content_bytes are intentionally excluded from the sidecar — the
    # actual file bytes live in the corresponding document file on disk.
    # Including them here would inflate the ground_truth.json to PDF-file size.
    """
    extractions = [_serialise_placed_value(pv) for pv in doc.placed_values]
    return {
        "filename": doc.filename,
        # doc_type is a StrEnum — its value is the string (e.g. "FORM")
        "doc_type": str(doc.doc_type),
        "file_format": doc.file_format,
        "extractions": extractions,
        # degraded_extractions is the same as extractions unless the caller
        # has provided a degraded GeneratedDocument with adjusted bboxes.
        # WHY: The spec requires the field to exist even for clean presets.
        "degraded_extractions": extractions,
    }


def write_ground_truth(
    scenario: Scenario,
    generated_docs: list[GeneratedDocument],
    degradation_params: dict[str, Any],
    output_dir: Path,
) -> Path:
    """Assemble and write ground_truth.json for one application set.

    Produces a JSON file matching spec Section 7 with the following structure::

        {
            "set_id": str,
            "category": str,
            "seed": int,
            "difficulty": str,
            "values": [ {attribute, value, unit, display_text}, ... ],
            "rule_verdicts": [ {rule_id, outcome, evaluated_value, threshold}, ... ],
            "documents": [ {filename, doc_type, ...}, ... ],
            "degradation": { <preset params> }
        }

    Args:
        scenario:          The fully built Scenario for this application set.
        generated_docs:    GeneratedDocument instances from the rendering layer.
                           PlacedValues are used to populate extractions.
        degradation_params: Arbitrary dict of degradation settings to embed
                            verbatim in the "degradation" section.  Pass {} for
                            clean presets.
        output_dir:        Directory in which to write ground_truth.json.
                           The directory must already exist.

    Returns:
        Path to the written ground_truth.json file.

    # WHY: Returning the path (rather than None) lets callers log or verify the
    # output without having to reconstruct the path themselves.
    """
    # Serialise Values — these are frozen dataclasses so we read fields directly.
    values_data = [
        {
            "attribute": v.attribute,
            "value": v.value,
            "unit": v.unit,
            "display_text": v.display_text,
        }
        for v in scenario.values
    ]

    # Serialise Verdicts.
    # WHY: Storing evaluated_value and threshold here lets the evaluator show
    # a diagnostic table (value vs threshold) without re-computing anything.
    verdicts_data = [
        {
            "rule_id": v.rule_id,
            "outcome": v.outcome,
            "evaluated_value": v.evaluated_value,
            "threshold": v.threshold,
        }
        for v in scenario.verdicts
    ]

    # Serialise each generated document.
    documents_data = [_serialise_document(doc) for doc in generated_docs]

    payload: dict[str, Any] = {
        "set_id": scenario.set_id,
        "category": scenario.category,
        "seed": scenario.seed,
        "difficulty": scenario.difficulty,
        "values": values_data,
        "rule_verdicts": verdicts_data,
        "documents": documents_data,
        # WHY: Embedding degradation params verbatim (not normalised) means
        # the sidecar captures the exact parameters used, even if the preset
        # YAML changes later.  The sidecar is an immutable record of what ran.
        "degradation": degradation_params,
        # WHY: edge_case_strategy is None for compliant/non_compliant sets and
        # a string identifier (e.g. "missing_evidence") for edge_case sets.
        # Including it here lets the corpus coverage test verify that every
        # strategy variant appears at least once without parsing filenames or
        # directory names.
        "edge_case_strategy": scenario.edge_case_strategy,
    }

    gt_path = output_dir / "ground_truth.json"
    gt_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return gt_path
