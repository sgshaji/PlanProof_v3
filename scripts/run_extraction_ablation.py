"""Real extraction ablation runner with error attribution.

Feeds v2 real extraction results through the reasoning pipeline, compares
against oracle (full_system) results, and attributes errors to either
extraction failures or reasoning failures.

Usage::

    python scripts/run_extraction_ablation.py
    python scripts/run_extraction_ablation.py --extraction-dir data/results/extraction/v2
    python scripts/run_extraction_ablation.py --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger("run_extraction_ablation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_NAME = "extraction_ablation"

# Confidence assigned to all real-extraction entities (realistic OCR/VLM estimate)
DEFAULT_CONFIDENCE = 0.80

# Outcome categories for error attribution
ATTRIBUTION_LABELS = (
    "end_to_end_success",
    "extraction_failure",
    "reasoning_failure",
    "serendipitous",
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real extraction ablation with oracle vs real SABLE comparison.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--extraction-dir",
        type=Path,
        default=Path("data/results/extraction/v2"),
        help="Directory containing v2 extraction result JSONs.",
    )
    parser.add_argument(
        "--oracle-dir",
        type=Path,
        default=Path("data/results/full_system"),
        help="Directory containing oracle (full_system) ExperimentResult JSONs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/results/extraction_ablation"),
        help="Directory to write extraction ablation (full_system) result JSONs.",
    )
    parser.add_argument(
        "--output-dir-abl-d",
        type=Path,
        default=Path("data/results/extraction_ablation_d"),
        help="Directory to write extraction ablation_d result JSONs.",
    )
    parser.add_argument(
        "--oracle-abl-d-dir",
        type=Path,
        default=Path("data/results/ablation_d"),
        help="Directory containing oracle ablation_d ExperimentResult JSONs.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/synthetic_diverse"),
        help="Root directory containing test set sub-directories.",
    )
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=Path("configs"),
        help="Directory containing rule configs and confidence thresholds.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable INFO-level logging.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Part 1: Build ExtractedEntity objects from v2 extraction results
# ---------------------------------------------------------------------------


def _source_document_prefix(doc_type: str, extraction_method: str) -> str:
    """Return the source_document prefix (FORM_ or DRAWING_) for an entity.

    The assessability evaluator matches substrings like "FORM" or "DRAWING"
    against the source_document field to validate acceptable sources.
    """
    doc_type_upper = doc_type.upper()

    # Map extraction doc_type tokens to canonical prefixes
    if any(tok in doc_type_upper for tok in ("FORM", "ADDRESS", "CERTIFICATE", "OWNERSHIP")):
        return "FORM"
    if any(tok in doc_type_upper for tok in ("DRAWING", "MEASUREMENT", "BOUNDARY", "SITE_PLAN")):
        return "DRAWING"

    # Fall back based on extraction method: OCR_LLM = form text, VLM = drawing
    if extraction_method.upper() == "OCR_LLM":
        return "FORM"
    return "DRAWING"


def _extraction_method_enum(raw: str) -> Any:
    """Map a string extraction method to the ExtractionMethod enum value."""
    from planproof.schemas.entities import ExtractionMethod

    mapping = {
        "OCR_LLM": ExtractionMethod.OCR_LLM,
        "VLM_ZEROSHOT": ExtractionMethod.VLM_ZEROSHOT,
        "VLM_STRUCTURED": ExtractionMethod.VLM_STRUCTURED,
        "VLM_FINETUNED": ExtractionMethod.VLM_FINETUNED,
        "MANUAL": ExtractionMethod.MANUAL,
    }
    return mapping.get(raw.upper(), ExtractionMethod.VLM_ZEROSHOT)


def _entity_type_enum(doc_type: str) -> Any:
    """Map extraction doc_type to the EntityType enum value."""
    from planproof.schemas.entities import EntityType

    doc_type_upper = doc_type.upper()
    if "ADDRESS" in doc_type_upper:
        return EntityType.ADDRESS
    if "CERTIFICATE" in doc_type_upper:
        return EntityType.CERTIFICATE
    if "BOUNDARY" in doc_type_upper:
        return EntityType.BOUNDARY
    if "ZONE" in doc_type_upper:
        return EntityType.ZONE
    if "OWNERSHIP" in doc_type_upper:
        return EntityType.OWNERSHIP
    return EntityType.MEASUREMENT


def build_entities_from_extraction(
    extraction_data: dict[str, Any],
) -> list[Any]:
    """Convert predicted_entities in *extraction_data* to ExtractedEntity objects.

    Applies realistic confidence (DEFAULT_CONFIDENCE) and normalises
    source_document to carry the FORM_ or DRAWING_ prefix needed by the
    assessability evaluator.
    """
    from planproof.schemas.entities import ExtractedEntity

    entities: list[ExtractedEntity] = []
    ts = datetime.now(timezone.utc)

    for raw in extraction_data.get("predicted_entities", []):
        attribute: str | None = raw.get("attribute") or None
        value = raw.get("value")
        doc_type: str = str(raw.get("doc_type", "MEASUREMENT"))
        raw_method: str = str(raw.get("extraction_method", "VLM_ZEROSHOT"))
        raw_source: str = str(raw.get("source_document", "unknown"))

        prefix = _source_document_prefix(doc_type, raw_method)
        # Use the basename of the source path as the document name
        basename = Path(raw_source).name if raw_source else "unknown"
        source_document = f"{prefix}_{basename}"

        entity_type = _entity_type_enum(doc_type)
        extraction_method = _extraction_method_enum(raw_method)

        entities.append(
            ExtractedEntity(
                entity_type=entity_type,
                attribute=attribute,
                value=value,
                unit=None,
                confidence=DEFAULT_CONFIDENCE,
                source_document=source_document,
                source_page=raw.get("source_page"),
                source_region=None,
                extraction_method=extraction_method,
                timestamp=ts,
            )
        )

    return entities


# ---------------------------------------------------------------------------
# Part 2: Run the reasoning pipeline on real entities
# ---------------------------------------------------------------------------


def _register_evaluators() -> Any:
    """Register all evaluator types and return a RuleFactory instance."""
    from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
    from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
    from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
    from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
    from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator

    factory = RuleFactory()
    RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
    RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
    RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
    RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
    RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
    RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)
    return factory


def run_pipeline_on_entities(
    entities: list[Any],
    configs_dir: Path,
    use_assessability: bool = True,
) -> tuple[list[Any], list[Any], list[Any]]:
    """Run the full reasoning pipeline on pre-built entities.

    When *use_assessability* is False (ablation_d mode), the SABLE step is
    skipped and all rules are treated as assessable, forcing binary PASS/FAIL
    verdicts even when evidence is insufficient.

    Returns (verdicts, assessability_results, loaded_rule_pairs).
    """
    from planproof.reasoning.confidence import ThresholdConfidenceGate
    from planproof.reasoning.reconciliation import PairwiseReconciler
    from planproof.representation.flat_evidence import FlatEvidenceProvider
    from planproof.representation.normalisation import Normaliser
    from planproof.schemas.entities import ExtractedEntity
    from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus

    factory = _register_evaluators()

    # --- Normalise entities ---
    normaliser = Normaliser()
    entities = normaliser.normalise_all(entities)

    # --- Evidence provider ---
    evidence_provider = FlatEvidenceProvider(entities)

    # --- Confidence gate ---
    confidence_thresholds_path = configs_dir / "confidence_thresholds.yaml"
    if confidence_thresholds_path.exists():
        confidence_gate = ThresholdConfidenceGate.from_yaml(confidence_thresholds_path)
    else:
        confidence_gate = ThresholdConfidenceGate(thresholds={})

    # --- Confidence gating ---
    entities = confidence_gate.filter_trusted(entities)
    evidence_provider.update_entities(entities)

    # --- Reconciliation by attribute ---
    reconciler = PairwiseReconciler()
    reconciled_evidence: dict[str, ReconciledEvidence] = {}
    groups: dict[str, list[ExtractedEntity]] = {}
    for entity in entities:
        key = entity.attribute if entity.attribute is not None else entity.entity_type.value
        groups.setdefault(key, []).append(entity)
    for attr, group in groups.items():
        reconciled_evidence[attr] = reconciler.reconcile(group, attr)

    # --- Load rules ---
    rules_dir = configs_dir / "rules"
    loaded_rule_pairs = factory.load_rules(rules_dir)
    rules_dict = {cfg.rule_id: cfg for cfg, _ in loaded_rule_pairs}
    all_rule_ids = list(rules_dict.keys())

    # --- Assessability (SABLE) ---
    assessability_results: list[Any] = []
    if use_assessability:
        from planproof.reasoning.assessability import DefaultAssessabilityEvaluator

        assessability_evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=evidence_provider,
            confidence_gate=confidence_gate,
            reconciler=reconciler,
            rules=rules_dict,
        )
        for rule_id in all_rule_ids:
            result = assessability_evaluator.evaluate(rule_id)
            assessability_results.append(result)
        assessable_ids = {r.rule_id for r in assessability_results if r.status == "ASSESSABLE"}
    else:
        # ablation_d: skip SABLE, treat every rule as assessable
        assessable_ids = set(all_rule_ids)

    # --- Rule evaluation on assessable rules ---
    verdicts: list[Any] = []
    fallback_missing = ReconciledEvidence(
        attribute="__fallback__",
        status=ReconciliationStatus.MISSING,
        sources=[],
    )

    for config, evaluator in loaded_rule_pairs:
        if config.rule_id not in assessable_ids:
            continue
        primary_attr = (
            config.parameters.get("attribute")
            or config.parameters.get("numerator_attribute")
            or config.rule_id
        )
        evidence = reconciled_evidence.get(primary_attr, fallback_missing)
        params_with_id = {**config.parameters, "rule_id": config.rule_id}
        verdict = evaluator.evaluate(evidence, params_with_id)
        verdicts.append(verdict)

    return verdicts, assessability_results, loaded_rule_pairs


# ---------------------------------------------------------------------------
# Part 3: Build RuleResult objects and save ExperimentResult
# ---------------------------------------------------------------------------


def find_ground_truth(set_id: str, data_dir: Path) -> dict[str, Any] | None:
    """Search data_dir sub-directories for ground_truth.json matching set_id."""
    for subdir in ("compliant", "noncompliant", "non_compliant", "edge_case"):
        candidate = data_dir / subdir / set_id / "ground_truth.json"
        if candidate.exists():
            with candidate.open(encoding="utf-8") as fh:
                return json.load(fh)

    # Recursive fallback
    for gt_path in data_dir.rglob("ground_truth.json"):
        if gt_path.parent.name == set_id:
            with gt_path.open(encoding="utf-8") as fh:
                return json.load(fh)

    return None


def build_and_save_result(
    set_id: str,
    verdicts: list[Any],
    assessability_results: list[Any],
    loaded_rule_pairs: list[Any],
    ground_truth: dict[str, Any] | None,
    output_dir: Path,
    config_name: str = CONFIG_NAME,
) -> Any:
    """Build an ExperimentResult from pipeline outputs and write it to disk."""
    from planproof.evaluation.results import ExperimentResult, RuleResult, save_result

    all_rule_ids = [cfg.rule_id for cfg, _ in loaded_rule_pairs]

    gt_verdicts: dict[str, str] = {}
    if ground_truth:
        gt_verdicts = {v["rule_id"]: v["outcome"] for v in ground_truth.get("rule_verdicts", [])}

    evaluated_rule_ids = {v.rule_id for v in verdicts}
    assessability_map: dict[str, Any] = {ar.rule_id: ar for ar in assessability_results}

    rule_results: list[RuleResult] = []
    for rule_id in all_rule_ids:
        gt_outcome = gt_verdicts.get(rule_id, "PASS")

        if rule_id in evaluated_rule_ids:
            verdict_obj = next(v for v in verdicts if v.rule_id == rule_id)
            predicted = str(verdict_obj.outcome)
        else:
            predicted = "NOT_ASSESSABLE"

        ar = assessability_map.get(rule_id)
        belief = ar.belief if ar else None
        plausibility = ar.plausibility if ar else None
        conflict_mass_val = ar.conflict_mass if ar else None
        blocking_reason_val = str(ar.blocking_reason) if ar else None

        # Promote PARTIALLY_ASSESSABLE through (only relevant when assessability is enabled)
        if ar and ar.status == "PARTIALLY_ASSESSABLE" and predicted == "NOT_ASSESSABLE":
            predicted = "PARTIALLY_ASSESSABLE"

        rule_results.append(
            RuleResult(
                rule_id=rule_id,
                ground_truth_outcome=gt_outcome,  # type: ignore[arg-type]
                predicted_outcome=predicted,  # type: ignore[arg-type]
                config_name=config_name,
                set_id=set_id,
                belief=belief,
                plausibility=plausibility,
                conflict_mass=conflict_mass_val,
                blocking_reason=blocking_reason_val,
            )
        )

    metadata: dict[str, Any] = {
        "source": "v2_real_extraction",
        "confidence": DEFAULT_CONFIDENCE,
    }
    if ground_truth:
        metadata.update(
            category=ground_truth.get("category", "unknown"),
            difficulty=ground_truth.get("difficulty", "unknown"),
            seed=ground_truth.get("seed"),
            n_documents=len(ground_truth.get("documents", [])),
        )

    exp_result = ExperimentResult(
        config_name=config_name,
        set_id=set_id,
        rule_results=rule_results,
        metadata=metadata,
        timestamp=datetime.now(timezone.utc),
    )

    # Save to output_dir/{set_id}.json (flat, no config sub-dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / f"{set_id}.json"
    dest.write_text(exp_result.model_dump_json(indent=2), encoding="utf-8")
    _log.info("Saved extraction ablation result to %s", dest)

    return exp_result


# ---------------------------------------------------------------------------
# Part 4: Error Attribution
# ---------------------------------------------------------------------------


def _is_correct(predicted: str, gt: str) -> bool:
    """Return True when the predicted outcome is considered correct.

    Acceptable caution: NOT_ASSESSABLE or PARTIALLY_ASSESSABLE when gt=PASS.
    """
    if predicted == gt:
        return True
    # Acceptable caution: assessability uncertainty when ground truth is PASS
    if gt == "PASS" and predicted in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"):
        return True
    return False


def attribute_errors(
    oracle_result: Any,
    real_result: Any,
) -> dict[str, str]:
    """Return a dict mapping rule_id -> attribution label for a single set."""
    oracle_map: dict[str, Any] = {rr.rule_id: rr for rr in oracle_result.rule_results}
    real_map: dict[str, Any] = {rr.rule_id: rr for rr in real_result.rule_results}

    attributions: dict[str, str] = {}
    for rule_id in oracle_map:
        if rule_id not in real_map:
            continue
        o = oracle_map[rule_id]
        r = real_map[rule_id]

        oracle_correct = _is_correct(o.predicted_outcome, o.ground_truth_outcome)
        real_correct = _is_correct(r.predicted_outcome, r.ground_truth_outcome)

        if oracle_correct and real_correct:
            label = "end_to_end_success"
        elif oracle_correct and not real_correct:
            label = "extraction_failure"
        elif not oracle_correct and not real_correct:
            label = "reasoning_failure"
        else:
            # oracle wrong, real correct — unexpected improvement from real extraction
            label = "serendipitous"

        attributions[rule_id] = label

    return attributions


def count_false_fails(results: dict[str, Any]) -> int:
    """Count (rule, set) pairs where ground_truth=PASS and predicted=FAIL."""
    total = 0
    for exp in results.values():
        for rr in exp.rule_results:
            if rr.ground_truth_outcome == "PASS" and rr.predicted_outcome == "FAIL":
                total += 1
    return total


def print_false_fail_matrix(
    oracle_fs_results: dict[str, Any],
    oracle_abl_d_results: dict[str, Any],
    real_fs_results: dict[str, Any],
    real_abl_d_results: dict[str, Any],
) -> None:
    """Print a 2x2 false-FAIL matrix (extraction x assessability mode)."""
    x = count_false_fails(oracle_fs_results)
    y = count_false_fails(oracle_abl_d_results)
    z = count_false_fails(real_fs_results)
    w = count_false_fails(real_abl_d_results)

    col1 = "Full System"
    col2 = "Ablation D (no assessability)"
    print()
    print("=" * 70)
    print("  FALSE-FAIL MATRIX  (ground_truth=PASS, predicted=FAIL)")
    print("=" * 70)
    print(f"  {'':30}  {col1:>14}  {col2:>30}")
    print(f"  {'-'*30}  {'-'*14}  {'-'*30}")
    print(f"  {'Oracle extraction':<30}  {x:>14}  {y:>30}")
    print(f"  {'Real extraction':<30}  {z:>14}  {w:>30}")
    print("=" * 70)
    print()


def print_attribution_summary(
    all_attributions: dict[str, dict[str, str]],
    oracle_results: dict[str, Any],
    real_results: dict[str, Any],
    label: str = "EXTRACTION ABLATION (full_system)",
) -> None:
    """Print summary counts and average SABLE beliefs."""
    counts: dict[str, int] = defaultdict(int)
    oracle_beliefs: list[float] = []
    real_beliefs: list[float] = []

    for set_id, attr_map in all_attributions.items():
        for rule_id, label_val in attr_map.items():
            counts[label_val] += 1

        if set_id in oracle_results and set_id in real_results:
            for rr in oracle_results[set_id].rule_results:
                if rr.belief is not None:
                    oracle_beliefs.append(rr.belief)
            for rr in real_results[set_id].rule_results:
                if rr.belief is not None:
                    real_beliefs.append(rr.belief)

    total = sum(counts.values())

    print()
    print("=" * 60)
    print(f"  {label}")
    print("=" * 60)
    print(f"  Sets processed   : {len(all_attributions)}")
    print(f"  (rule, set) pairs: {total}")
    print()
    print(f"  {'Category':<28}  {'Count':>6}  {'%':>6}")
    print(f"  {'-'*28}  {'------':>6}  {'------':>6}")
    for lbl in ATTRIBUTION_LABELS:
        n = counts.get(lbl, 0)
        pct = 100.0 * n / total if total else 0.0
        print(f"  {lbl:<28}  {n:>6}  {pct:>5.1f}%")

    print()
    print("  SABLE Belief Comparison")
    print(f"  {'Source':<18}  {'Avg Belief':>12}  {'N samples':>10}")
    print(f"  {'-'*18}  {'----------':>12}  {'----------':>10}")
    avg_oracle = sum(oracle_beliefs) / len(oracle_beliefs) if oracle_beliefs else float("nan")
    avg_real = sum(real_beliefs) / len(real_beliefs) if real_beliefs else float("nan")
    print(f"  {'Oracle (full_system)':<18}  {avg_oracle:>12.4f}  {len(oracle_beliefs):>10}")
    print(f"  {'Real extraction':<18}  {avg_real:>12.4f}  {len(real_beliefs):>10}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        _log.setLevel(logging.INFO)

    extraction_dir: Path = args.extraction_dir
    oracle_dir: Path = args.oracle_dir
    oracle_abl_d_dir: Path = args.oracle_abl_d_dir
    output_dir: Path = args.output_dir
    output_dir_abl_d: Path = args.output_dir_abl_d
    data_dir: Path = args.data_dir
    configs_dir: Path = args.configs_dir

    # Discover v2 extraction result files
    extraction_files = sorted(extraction_dir.glob("*.json"))
    if not extraction_files:
        print(f"No extraction result files found in {extraction_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(extraction_files)} extraction result file(s) in {extraction_dir}")

    # Load oracle full_system results indexed by set_id
    oracle_results: dict[str, Any] = {}
    if oracle_dir.exists():
        from planproof.evaluation.results import load_result

        for oracle_path in sorted(oracle_dir.glob("*.json")):
            try:
                res = load_result(oracle_path)
                oracle_results[res.set_id] = res
            except Exception as exc:  # noqa: BLE001
                _log.warning("Could not load oracle result %s: %s", oracle_path, exc)

    print(f"Loaded {len(oracle_results)} oracle (full_system) result(s) from {oracle_dir}")

    # Load oracle ablation_d results indexed by set_id
    oracle_abl_d_results: dict[str, Any] = {}
    if oracle_abl_d_dir.exists():
        from planproof.evaluation.results import load_result

        for oracle_path in sorted(oracle_abl_d_dir.glob("*.json")):
            try:
                res = load_result(oracle_path)
                oracle_abl_d_results[res.set_id] = res
            except Exception as exc:  # noqa: BLE001
                _log.warning("Could not load oracle ablation_d result %s: %s", oracle_path, exc)

    print(f"Loaded {len(oracle_abl_d_results)} oracle (ablation_d) result(s) from {oracle_abl_d_dir}")

    real_results: dict[str, Any] = {}
    real_abl_d_results: dict[str, Any] = {}
    all_attributions: dict[str, dict[str, str]] = {}
    all_abl_d_attributions: dict[str, dict[str, str]] = {}

    for extraction_path in extraction_files:
        with extraction_path.open(encoding="utf-8") as fh:
            extraction_data = json.load(fh)

        set_id: str = extraction_data.get("set_id", extraction_path.stem)
        print(f"  Processing {set_id} ...", end=" ", flush=True)

        try:
            # Part 1: Build entities from real extraction
            entities = build_entities_from_extraction(extraction_data)

            # Find ground truth for this set_id (shared between both passes)
            ground_truth = find_ground_truth(set_id, data_dir)
            if ground_truth is None:
                _log.warning("No ground_truth.json found for %s", set_id)

            # --- Pass A: full_system (with SABLE) ---
            verdicts, assessability_results, loaded_rule_pairs = run_pipeline_on_entities(
                entities, configs_dir, use_assessability=True
            )
            real_result = build_and_save_result(
                set_id=set_id,
                verdicts=verdicts,
                assessability_results=assessability_results,
                loaded_rule_pairs=loaded_rule_pairs,
                ground_truth=ground_truth,
                output_dir=output_dir,
                config_name=CONFIG_NAME,
            )
            real_results[set_id] = real_result

            if set_id in oracle_results:
                attributions = attribute_errors(oracle_results[set_id], real_result)
                all_attributions[set_id] = attributions

            # --- Pass B: ablation_d (no assessability, forced binary verdicts) ---
            verdicts_d, assessability_results_d, loaded_rule_pairs_d = run_pipeline_on_entities(
                entities, configs_dir, use_assessability=False
            )
            real_abl_d_result = build_and_save_result(
                set_id=set_id,
                verdicts=verdicts_d,
                assessability_results=assessability_results_d,
                loaded_rule_pairs=loaded_rule_pairs_d,
                ground_truth=ground_truth,
                output_dir=output_dir_abl_d,
                config_name="extraction_ablation_d",
            )
            real_abl_d_results[set_id] = real_abl_d_result

            if set_id in oracle_abl_d_results:
                attributions_d = attribute_errors(oracle_abl_d_results[set_id], real_abl_d_result)
                all_abl_d_attributions[set_id] = attributions_d

            n_attr = len(all_attributions.get(set_id, {}))
            print(f"OK ({n_attr} rules attributed)")

        except Exception as exc:  # noqa: BLE001
            _log.exception("Error processing %s: %s", set_id, exc)
            print(f"ERROR: {exc}")

    # Print 2x2 false-FAIL matrix
    print_false_fail_matrix(
        oracle_fs_results=oracle_results,
        oracle_abl_d_results=oracle_abl_d_results,
        real_fs_results=real_results,
        real_abl_d_results=real_abl_d_results,
    )

    # Print attribution summaries
    print_attribution_summary(
        all_attributions,
        oracle_results,
        real_results,
        label="EXTRACTION ABLATION — full_system ERROR ATTRIBUTION",
    )
    print_attribution_summary(
        all_abl_d_attributions,
        oracle_abl_d_results,
        real_abl_d_results,
        label="EXTRACTION ABLATION — ablation_d ERROR ATTRIBUTION",
    )


if __name__ == "__main__":
    main()
