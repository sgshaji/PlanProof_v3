"""Extraction evaluation runner.

Runs real LLM/VLM extraction on synthetic PDFs and compares against ground
truth, writing per-set result JSON files and printing a summary table.

Usage examples::

    python scripts/run_extraction_eval.py --version v1 --data-dir data/synthetic_diverse --output-dir data/results/extraction -v
    python scripts/run_extraction_eval.py --version v2 --data-dir data/synthetic_diverse --output-dir data/results/extraction
    python scripts/run_extraction_eval.py --version v1 --data-dir data/annotated --output-dir data/results/extraction_bcc --all-sets
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal logging to stderr — -v escalates to INFO
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger("run_extraction_eval")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sub-directories under data_dir that may contain test sets — ordered so that
# category assignment is consistent with the default 5-set selection logic.
CATEGORY_SUBDIRS: list[str] = ["compliant", "non_compliant", "edge_case", "noncompliant"]

# Document types that have a text extraction path (PDF/pdfplumber → LLM)
TEXT_DOC_TYPES: frozenset[str] = frozenset({"FORM", "REPORT", "CERTIFICATE"})

# Document file extensions recognised as images (→ VLM path)
IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif"})

# Document file extensions treated as PDFs
PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run extraction evaluation for PlanProof.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="Version tag for this run (e.g. v1, v2). Used to name the output sub-directory.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/synthetic_diverse"),
        help="Root directory containing test set sub-directories.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/results/extraction"),
        help="Root directory for result JSON files.",
    )
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=Path("configs"),
        help="Directory containing configuration files (e.g. classifier_patterns.yaml).",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=None,
        help=(
            "Separate directory containing the actual PDF/image documents. "
            "When set, ground truth is read from --data-dir but documents are "
            "loaded from --docs-dir/<set_name>/. Useful for BCC evaluation "
            "where ground truth is in data/annotated/ but documents are in data/raw/."
        ),
    )
    parser.add_argument(
        "--all-sets",
        action="store_true",
        help="Run all discovered test sets instead of the default 5.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable INFO-level logging.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Test-set discovery and selection
# ---------------------------------------------------------------------------


def _discover_sets_in_category(data_dir: Path, category: str) -> list[Path]:
    """Return sorted test-set directories for a given category sub-directory."""
    subdir = data_dir / category
    if not subdir.is_dir():
        return []
    found = sorted(
        gt.parent for gt in subdir.rglob("ground_truth.json")
    )
    return found


def discover_test_sets(data_dir: Path) -> dict[str, list[Path]]:
    """Return test-set directories grouped by category, deduplicated.

    The dict preserves the order of CATEGORY_SUBDIRS so that callers can rely
    on consistent ordering when selecting the default 5-set sample.
    """
    sets_by_category: dict[str, list[Path]] = {}
    seen: set[Path] = set()

    for cat in CATEGORY_SUBDIRS:
        paths: list[Path] = []
        for p in _discover_sets_in_category(data_dir, cat):
            if p not in seen:
                seen.add(p)
                paths.append(p)
        if paths:
            sets_by_category[cat] = paths

    # Fallback: if no sets found in canonical dirs, search whole tree
    if not sets_by_category:
        all_paths = sorted(gt.parent for gt in data_dir.rglob("ground_truth.json"))
        if all_paths:
            sets_by_category["unknown"] = all_paths

    return sets_by_category


def select_test_sets(
    sets_by_category: dict[str, list[Path]],
    *,
    all_sets: bool,
) -> list[Path]:
    """Return the list of test-set paths to evaluate.

    Default selection (all_sets=False): first 2 compliant, first 2 non_compliant,
    first 1 edge_case — deterministic by sorted directory name.

    Aliases: non_compliant and noncompliant are treated as the same category.
    """
    if all_sets:
        result: list[Path] = []
        for paths in sets_by_category.values():
            result.extend(paths)
        return result

    # Merge non_compliant / noncompliant aliases
    def _get(cat: str) -> list[Path]:
        return sets_by_category.get(cat, [])

    compliant = _get("compliant")
    non_compliant = _get("non_compliant") or _get("noncompliant")
    edge_case = _get("edge_case")

    selected: list[Path] = []
    selected.extend(compliant[:2])
    selected.extend(non_compliant[:2])
    selected.extend(edge_case[:1])

    # If we have fewer than 5, fill from whatever is available
    if not selected:
        for paths in sets_by_category.values():
            selected.extend(paths[:5])
            break

    return selected


# ---------------------------------------------------------------------------
# Ground truth loading
# ---------------------------------------------------------------------------


def load_ground_truth(test_set_dir: Path) -> dict[str, Any]:
    """Load and return the parsed ground_truth.json for a test set directory."""
    gt_path = test_set_dir / "ground_truth.json"
    with gt_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _gt_entities_from_ground_truth(ground_truth: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten ground-truth document extractions into a list of entity dicts.

    Each item has at minimum: ``attribute`` and ``value``.  Optional fields
    ``doc_type`` and ``source_document`` are included when available.
    """
    entities: list[dict[str, Any]] = []
    for doc in ground_truth.get("documents", []):
        doc_type: str = doc.get("doc_type", "")
        filename: str = doc.get("filename", "")
        for extraction in doc.get("extractions", []):
            attr = extraction.get("attribute")
            if attr is None:
                continue
            entities.append(
                {
                    "attribute": attr,
                    "value": extraction.get("value"),
                    "doc_type": doc_type,
                    "source_document": filename,
                }
            )
    return entities


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def _build_llm_client() -> Any | None:
    """Build a GroqClient from env vars, or return None with a warning."""
    from planproof.infrastructure.groq_client import GroqClient  # noqa: PLC0415

    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("PLANPROOF_LLM_API_KEY")
    if not api_key:
        _log.warning(
            "No LLM API key found. Set GROQ_API_KEY or PLANPROOF_LLM_API_KEY. "
            "LLM extraction will be skipped."
        )
        return None
    try:
        return GroqClient(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Failed to construct GroqClient: %s. LLM extraction skipped.", exc)
        return None


def _build_vlm_client() -> Any | None:
    """Build an OpenAIClient from env vars, or return None with a warning."""
    from planproof.infrastructure.openai_client import OpenAIClient  # noqa: PLC0415

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("PLANPROOF_OPENAI_API_KEY") or ""
    if not api_key:
        _log.warning(
            "OPENAI_API_KEY / PLANPROOF_OPENAI_API_KEY not set. VLM extraction will be skipped."
        )
        return None
    try:
        return OpenAIClient(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Failed to construct OpenAIClient: %s. VLM extraction skipped.", exc)
        return None


# ---------------------------------------------------------------------------
# Per-document extraction
# ---------------------------------------------------------------------------


def _find_documents(test_set_dir: Path) -> list[Path]:
    """Return all PDF and image files directly inside *test_set_dir*."""
    docs: list[Path] = []
    for p in sorted(test_set_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in PDF_EXTENSIONS | IMAGE_EXTENSIONS:
            docs.append(p)
    return docs


def _entity_to_dict(entity: Any) -> dict[str, Any]:
    """Convert an ExtractedEntity to a plain dict for serialisation and metrics."""
    return {
        "attribute": entity.attribute,
        "value": entity.value,
        "doc_type": str(entity.entity_type),
        "source_document": entity.source_document,
        "extraction_method": str(entity.extraction_method),
    }


def _extract_from_document(
    doc_path: Path,
    classified: Any,
    llm_client: Any | None,
    vlm_client: Any | None,
    prompts_dir: Path,
) -> list[Any]:
    """Run extraction on a single document and return ExtractedEntity objects.

    Imports are deferred to keep module startup fast.
    """
    doc_type: str = classified.doc_type.value  # e.g. "FORM", "DRAWING"
    suffix = doc_path.suffix.lower()
    is_image = suffix in IMAGE_EXTENSIONS

    entities: list[Any] = []

    if doc_type in TEXT_DOC_TYPES and not is_image:
        # Text path: pdfplumber → LLM
        if llm_client is None:
            _log.warning(
                "Skipping LLM extraction for %s — no LLM client.", doc_path.name
            )
            return []

        if not classified.has_text_layer:
            _log.info(
                "Document %s has no text layer; skipping text extraction.", doc_path.name
            )
            return []

        from planproof.ingestion.entity_extractor import LLMEntityExtractor  # noqa: PLC0415
        from planproof.ingestion.text_extractor import PdfPlumberExtractor  # noqa: PLC0415

        raw_text = PdfPlumberExtractor().extract_text(doc_path)
        extractor = LLMEntityExtractor(llm=llm_client, prompts_dir=prompts_dir, doc_type=doc_type)
        entities = extractor.extract_entities(raw_text, doc_type=doc_type)

    elif doc_type == "DRAWING" or is_image:
        # Vision path: VLM spatial extractor (handles both images and PDF drawings)
        if vlm_client is None:
            _log.warning(
                "Skipping VLM extraction for %s — no VLM client.", doc_path.name
            )
            return []

        from planproof.ingestion.vlm_spatial_extractor import VLMSpatialExtractor  # noqa: PLC0415

        # VLMSpatialExtractor expects a raw openai.OpenAI client (uses .chat.completions.create),
        # not our OpenAIClient wrapper. Pass the underlying client.
        raw_client = vlm_client._client if hasattr(vlm_client, "_client") else vlm_client
        extractor = VLMSpatialExtractor(openai_client=raw_client, prompts_dir=prompts_dir)
        entities = extractor.extract_spatial_attributes(doc_path)

    else:
        _log.info(
            "Document %s classified as %s — no extraction path configured.",
            doc_path.name,
            doc_type,
        )

    return entities


def _run_extraction_on_set(
    test_set_dir: Path,
    classifier: Any,
    llm_client: Any | None,
    vlm_client: Any | None,
    prompts_dir: Path,
) -> list[dict[str, Any]]:
    """Run extraction over all documents in a test set.

    Returns a flat list of entity dicts (attribute, value, doc_type, …).
    Per-document failures are caught, logged, and skipped.
    """
    docs = _find_documents(test_set_dir)
    if not docs:
        _log.warning("No PDF/image documents found in %s", test_set_dir)

    all_entities: list[dict[str, Any]] = []

    for doc_path in docs:
        try:
            classified = classifier.classify(doc_path)
            _log.info(
                "Classified %s as %s (text_layer=%s)",
                doc_path.name,
                classified.doc_type.value,
                classified.has_text_layer,
            )
            raw_entities = _extract_from_document(
                doc_path=doc_path,
                classified=classified,
                llm_client=llm_client,
                vlm_client=vlm_client,
                prompts_dir=prompts_dir,
            )
            all_entities.extend(_entity_to_dict(e) for e in raw_entities)
        except Exception as exc:  # noqa: BLE001
            _log.warning("Extraction failed for %s: %s", doc_path.name, exc)

    return all_entities


# ---------------------------------------------------------------------------
# Result serialisation
# ---------------------------------------------------------------------------


def _serialise_match(match: Any) -> dict[str, Any]:
    """Convert an ExtractionMatch dataclass to a plain dict."""
    return {
        "gt_attribute": match.gt_attribute,
        "predicted_attribute": match.predicted_attribute,
        "matched": match.matched,
        "value_correct": match.value_correct,
    }


def _build_result_dict(
    set_id: str,
    version: str,
    gt_entities: list[dict[str, Any]],
    predicted_entities: list[dict[str, Any]],
    eval_result: Any,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "set_id": set_id,
        "version": version,
        "timestamp": timestamp,
        "gt_entity_count": len(gt_entities),
        "predicted_entity_count": len(predicted_entities),
        "recall": round(eval_result.recall, 4),
        "precision": round(eval_result.precision, 4),
        "value_accuracy": round(eval_result.value_accuracy, 4),
        "per_attribute": eval_result.per_attribute,
        "gt_entities": gt_entities,
        "predicted_entities": predicted_entities,
        "matches": [_serialise_match(m) for m in eval_result.matches],
    }


# ---------------------------------------------------------------------------
# Per-set orchestration
# ---------------------------------------------------------------------------


def run_set(
    test_set_dir: Path,
    version: str,
    output_dir: Path,
    configs_dir: Path,
    llm_client: Any | None,
    vlm_client: Any | None,
    prompts_dir: Path,
    docs_dir: Path | None = None,
) -> dict[str, float] | None:
    """Process a single test set end-to-end.

    Args:
        docs_dir: If set, documents are loaded from ``docs_dir/<set_name>/``
            instead of from *test_set_dir*.  Ground truth is always read from
            *test_set_dir*.  This supports BCC evaluation where ground truth
            lives in ``data/annotated/`` and documents in ``data/raw/``.

    Returns a dict with recall/precision/value_accuracy on success, or None on
    unrecoverable error.
    """
    from planproof.evaluation.extraction_metrics import compute_extraction_metrics  # noqa: PLC0415
    from planproof.ingestion.classifier import RuleBasedClassifier  # noqa: PLC0415

    set_id = test_set_dir.name
    _log.info("--- Processing set: %s ---", set_id)

    # Load ground truth from the annotation directory
    ground_truth = load_ground_truth(test_set_dir)
    gt_entities = _gt_entities_from_ground_truth(ground_truth)
    _log.info("Ground truth entities: %d", len(gt_entities))

    # Determine where documents live
    doc_search_dir = (docs_dir / set_id) if docs_dir else test_set_dir
    if not doc_search_dir.is_dir():
        _log.warning("Document directory does not exist: %s", doc_search_dir)
        return None

    # Build classifier (per-set so the patterns file path is resolved cleanly)
    patterns_path = configs_dir / "classifier_patterns.yaml"
    classifier = RuleBasedClassifier(patterns_path=patterns_path)

    # Run extraction over all documents in the set
    predicted_entities = _run_extraction_on_set(
        test_set_dir=doc_search_dir,
        classifier=classifier,
        llm_client=llm_client,
        vlm_client=vlm_client,
        prompts_dir=prompts_dir,
    )
    _log.info("Predicted entities: %d", len(predicted_entities))

    # Determine aggregate doc_type for the set (majority type among GT docs)
    doc_types = [doc.get("doc_type", "") for doc in ground_truth.get("documents", [])]
    doc_type = max(set(doc_types), key=doc_types.count) if doc_types else ""

    # Compute metrics
    eval_result = compute_extraction_metrics(
        gt_entities=gt_entities,
        predicted_entities=predicted_entities,
        set_id=set_id,
        doc_type=doc_type,
    )

    # Build output path
    out_dir = output_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{set_id}.json"

    timestamp = datetime.now(timezone.utc).isoformat()
    result_dict = _build_result_dict(
        set_id=set_id,
        version=version,
        gt_entities=gt_entities,
        predicted_entities=predicted_entities,
        eval_result=eval_result,
        timestamp=timestamp,
    )

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(result_dict, fh, indent=2, default=str)

    _log.info(
        "Saved result for %s → %s  recall=%.3f  precision=%.3f  value_acc=%.3f",
        set_id,
        out_path,
        eval_result.recall,
        eval_result.precision,
        eval_result.value_accuracy,
    )

    return {
        "recall": eval_result.recall,
        "precision": eval_result.precision,
        "value_accuracy": eval_result.value_accuracy,
    }


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------


def _print_summary(results: list[tuple[str, dict[str, float]]]) -> None:
    if not results:
        print("No results to summarise.")
        return

    print("\n" + "=" * 60)
    print(f"{'Set':<35} {'Recall':>7} {'Prec':>7} {'ValAcc':>7}")
    print("-" * 60)
    for set_id, metrics in results:
        print(
            f"{set_id:<35} "
            f"{metrics['recall']:>7.3f} "
            f"{metrics['precision']:>7.3f} "
            f"{metrics['value_accuracy']:>7.3f}"
        )

    recalls = [m["recall"] for _, m in results]
    precisions = [m["precision"] for _, m in results]
    value_accs = [m["value_accuracy"] for _, m in results]

    n = len(results)
    avg_recall = sum(recalls) / n
    avg_prec = sum(precisions) / n
    avg_val = sum(value_accs) / n

    print("-" * 60)
    print(
        f"{'AVERAGE':<35} "
        f"{avg_recall:>7.3f} "
        f"{avg_prec:>7.3f} "
        f"{avg_val:>7.3f}"
    )
    print(f"\nSets evaluated: {n}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger("run_extraction_eval").setLevel(logging.INFO)

    data_dir: Path = args.data_dir
    output_dir: Path = args.output_dir
    configs_dir: Path = args.configs_dir
    version: str = args.version
    docs_dir: Path | None = args.docs_dir
    prompts_dir = configs_dir / "prompts"

    if not data_dir.is_dir():
        _log.error("Data directory does not exist: %s", data_dir)
        sys.exit(1)

    # Discover test sets
    sets_by_category = discover_test_sets(data_dir)
    if not sets_by_category:
        _log.error("No test sets found under %s", data_dir)
        sys.exit(1)

    selected_sets = select_test_sets(sets_by_category, all_sets=args.all_sets)
    _log.info("Selected %d test set(s) for evaluation.", len(selected_sets))

    # Build API clients once (deferred import keeps startup fast)
    llm_client: Any | None = None
    vlm_client: Any | None = None
    try:
        llm_client = _build_llm_client()
    except Exception as exc:  # noqa: BLE001
        _log.warning("Could not build LLM client: %s", exc)

    try:
        vlm_client = _build_vlm_client()
    except Exception as exc:  # noqa: BLE001
        _log.warning("Could not build VLM client: %s", exc)

    if llm_client is None and vlm_client is None:
        warnings.warn(
            "Neither LLM nor VLM client is available. "
            "All extraction will return empty predictions. "
            "Set GROQ_API_KEY / PLANPROOF_LLM_API_KEY and/or OPENAI_API_KEY.",
            stacklevel=1,
        )

    # Run evaluation across selected sets
    results: list[tuple[str, dict[str, float]]] = []
    for test_set_dir in selected_sets:
        try:
            metrics = run_set(
                test_set_dir=test_set_dir,
                version=version,
                output_dir=output_dir,
                configs_dir=configs_dir,
                llm_client=llm_client,
                vlm_client=vlm_client,
                prompts_dir=prompts_dir,
                docs_dir=docs_dir,
            )
            if metrics is not None:
                results.append((test_set_dir.name, metrics))
        except Exception as exc:  # noqa: BLE001
            _log.error("Failed to process set %s: %s", test_set_dir.name, exc)

    _print_summary(results)


if __name__ == "__main__":
    main()
