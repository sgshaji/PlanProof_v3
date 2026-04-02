"""Ablation experiment runner.

Runs all (or a selected) ablation configuration against all discovered test
sets and writes per-(config, set) result files to the output directory.

Usage examples::

    python scripts/run_ablation.py
    python scripts/run_ablation.py --data-dir data/synthetic_diverse --output-dir data/results
    python scripts/run_ablation.py --config ablation_b --data-dir data/synthetic_diverse
    python scripts/run_ablation.py --resume
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal logging to stdout so the script is useful standalone
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger("run_ablation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_CONFIGS: list[str] = [
    "naive_baseline",
    "strong_baseline",
    "ablation_a",
    "ablation_b",
    "ablation_c",
    "ablation_d",
    "full_system",
]

# Configs that use the pipeline reasoning path (not raw LLM baselines)
PIPELINE_CONFIGS: set[str] = {
    "ablation_a",
    "ablation_b",
    "ablation_c",
    "ablation_d",
    "full_system",
}

BASELINE_CONFIGS: set[str] = {"naive_baseline", "strong_baseline"}

# Sub-directories under data_dir that may contain test sets
TEST_SET_SUBDIRS: list[str] = ["compliant", "noncompliant", "edge_case"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ablation experiments for PlanProof.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
        default=Path("data/results"),
        help="Root directory for result JSON files.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        choices=ALL_CONFIGS,
        help="Run only this single ablation configuration.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip experiment combinations where a result file already exists.",
    )
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=Path("configs"),
        help="Directory containing ablation YAML configs and rules sub-directory.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable INFO-level logging.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Test-set discovery
# ---------------------------------------------------------------------------


def discover_test_sets(data_dir: Path) -> list[Path]:
    """Return all directories under *data_dir* that contain ground_truth.json.

    Searches the direct sub-directories defined in TEST_SET_SUBDIRS, then
    falls back to a recursive search of the entire tree so the script works
    with flat layouts too.
    """
    found: list[Path] = []

    # Preferred: look inside the canonical sub-directories
    for subdir_name in TEST_SET_SUBDIRS:
        subdir = data_dir / subdir_name
        if not subdir.is_dir():
            continue
        for gt_path in sorted(subdir.rglob("ground_truth.json")):
            found.append(gt_path.parent)

    # Fallback: search the whole tree if nothing found in the canonical dirs
    if not found:
        for gt_path in sorted(data_dir.rglob("ground_truth.json")):
            found.append(gt_path.parent)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


# ---------------------------------------------------------------------------
# Ground truth loading
# ---------------------------------------------------------------------------


def load_ground_truth(test_set_dir: Path) -> dict[str, Any]:
    """Load and return the parsed ground_truth.json for a test set directory."""
    gt_path = test_set_dir / "ground_truth.json"
    with gt_path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Entity construction from ground truth
# ---------------------------------------------------------------------------


def _build_entities_from_ground_truth(
    ground_truth: dict[str, Any],
    test_set_dir: Path | None = None,
) -> list[Any]:
    """Construct ExtractedEntity objects from ground truth document extractions.

    Each document's ``extractions`` list is converted to an ExtractedEntity so
    the pipeline reasoning steps can run without re-invoking the LLM.

    The ``source_document`` field is prefixed with the document's ``doc_type``
    (e.g. ``"DRAWING_site_plan.pdf"``) so that the assessability evaluator's
    substring match against ``acceptable_sources`` (e.g. ``"DRAWING"``,
    ``"FORM"``) works correctly.

    If *test_set_dir* is provided and contains ``reference/zone.json``, a
    synthetic ZONE entity is appended with ``source_document`` set to
    ``"EXTERNAL_DATA_zone.json"`` so rules that require a zone from
    ``EXTERNAL_DATA`` sources are assessable.

    Parameters
    ----------
    ground_truth:
        Parsed ground_truth.json dict.
    test_set_dir:
        Optional path to the test set directory used to locate reference data.

    Returns
    -------
    list[ExtractedEntity]
    """
    from datetime import datetime, timezone

    from planproof.schemas.entities import (
        BoundingBox,
        EntityType,
        ExtractedEntity,
        ExtractionMethod,
    )

    entities: list[ExtractedEntity] = []
    extraction_ts = datetime.now(timezone.utc)

    for doc in ground_truth.get("documents", []):
        filename: str = doc.get("filename", "unknown")
        doc_type: str = doc.get("doc_type", "").upper()
        # Prefix the filename with the doc_type so that assessability source
        # matching (substring of acceptable_sources against source_document)
        # can find tokens like "DRAWING" or "FORM" in the field value.
        source_document = f"{doc_type}_{filename}" if doc_type else filename

        for extraction in doc.get("extractions", []):
            raw_entity_type = str(extraction.get("entity_type", "MEASUREMENT")).upper()
            try:
                entity_type = EntityType(raw_entity_type)
            except ValueError:
                entity_type = EntityType.MEASUREMENT

            raw_bbox = extraction.get("bounding_box")
            source_region: BoundingBox | None = None
            if raw_bbox:
                try:
                    source_region = BoundingBox(
                        x=float(raw_bbox.get("x", 0)),
                        y=float(raw_bbox.get("y", 0)),
                        width=float(raw_bbox.get("width", 0)),
                        height=float(raw_bbox.get("height", 0)),
                        page=int(raw_bbox.get("page", extraction.get("page", 1))),
                    )
                except (TypeError, ValueError):
                    source_region = None

            raw_attr: str | None = extraction.get("attribute") or None

            entities.append(
                ExtractedEntity(
                    entity_type=entity_type,
                    attribute=raw_attr,
                    value=extraction.get("value"),
                    unit=extraction.get("unit"),
                    confidence=1.0,  # ground truth data is considered perfect
                    source_document=source_document,
                    source_page=extraction.get("page"),
                    source_region=source_region,
                    extraction_method=ExtractionMethod.MANUAL,
                    timestamp=extraction_ts,
                )
            )

    # --- Synthetic ZONE entity from reference/zone.json ---
    if test_set_dir is not None:
        zone_path = test_set_dir / "reference" / "zone.json"
        if zone_path.exists():
            try:
                with zone_path.open(encoding="utf-8") as fh:
                    zone_data = json.load(fh)
                zone_code = zone_data.get("zone_code")
                if zone_code is not None:
                    entities.append(
                        ExtractedEntity(
                            entity_type=EntityType.ZONE,
                            value=zone_code,
                            # Store "attr:zone_category" in unit so the ablation
                            # runner can group this entity correctly for
                            # reconciliation, and the assessability evaluator
                            # recognises it as an attribute tag (not a unit).
                            unit="attr:zone_category",
                            confidence=1.0,
                            source_document="EXTERNAL_DATA_zone.json",
                            source_page=None,
                            source_region=None,
                            extraction_method=ExtractionMethod.MANUAL,
                            timestamp=extraction_ts,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                _log.warning("Could not load zone reference data from %s: %s", zone_path, exc)

    return entities


# ---------------------------------------------------------------------------
# Ablation YAML loading
# ---------------------------------------------------------------------------


def _load_ablation_config(configs_dir: Path, config_name: str) -> dict[str, Any]:
    """Load and return the ablation YAML for *config_name*."""
    import yaml

    yaml_path = configs_dir / "ablation" / f"{config_name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"Ablation config not found: {yaml_path}")
    with yaml_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Pipeline config construction
# ---------------------------------------------------------------------------


def _build_pipeline_config(
    ablation_yaml: dict[str, Any],
    configs_dir: Path,
) -> Any:
    """Return a PipelineConfig with ablation flags from *ablation_yaml*.

    All LLM / DB settings are left at their defaults; no actual LLM calls
    will be made during pipeline-config experiments because we inject
    ground-truth entities directly into the context.
    """
    from planproof.schemas.config import AblationConfig, PipelineConfig

    ablation = AblationConfig(
        use_snkg=ablation_yaml.get("use_snkg", False),
        use_rule_engine=ablation_yaml.get("use_rule_engine", True),
        use_confidence_gating=ablation_yaml.get("use_confidence_gating", True),
        use_assessability_engine=ablation_yaml.get("use_assessability_engine", True),
        use_evidence_reconciliation=ablation_yaml.get("use_evidence_reconciliation", True),
        use_vlm=ablation_yaml.get("use_vlm", False),
    )
    return PipelineConfig(
        configs_dir=configs_dir,
        ablation=ablation,
        # Prevent pydantic-settings from reading the real env so tests are
        # hermetic.  We explicitly set llm_api_key to empty to avoid any
        # accidental LLM calls.
        llm_api_key="",
        neo4j_uri="",
    )


# ---------------------------------------------------------------------------
# Pipeline reasoning runner (ablation_a through full_system)
# ---------------------------------------------------------------------------


def _run_pipeline_config(
    config_name: str,
    ground_truth: dict[str, Any],
    ablation_yaml: dict[str, Any],
    configs_dir: Path,
    test_set_dir: Path | None = None,
) -> tuple[list[Any], list[Any]]:
    """Run the reasoning pipeline steps against ground-truth entities.

    Returns a tuple of (verdicts, assessability_results).  verdicts may be
    empty for ablation_a which has use_rule_engine=False.
    """
    from planproof.reasoning.assessability import DefaultAssessabilityEvaluator
    from planproof.reasoning.confidence import ThresholdConfidenceGate
    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.reasoning.reconciliation import PairwiseReconciler
    from planproof.representation.flat_evidence import FlatEvidenceProvider
    from planproof.representation.normalisation import Normaliser
    from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus

    # --- Register evaluators ---
    from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
    from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
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

    # --- Build entities from ground truth ---
    entities = _build_entities_from_ground_truth(ground_truth, test_set_dir=test_set_dir)

    # --- Normalisation ---
    normaliser = Normaliser()
    entities = normaliser.normalise_all(entities)

    # --- Evidence provider ---
    # We always use FlatEvidenceProvider in the ablation runner: SNKG requires
    # a live Neo4j connection which is not available in a batch experiment run.
    evidence_provider = FlatEvidenceProvider(entities)

    # --- Reconciler ---
    reconciler = PairwiseReconciler()

    # --- Confidence gate ---
    confidence_thresholds_path = configs_dir / "confidence_thresholds.yaml"
    if confidence_thresholds_path.exists():
        confidence_gate = ThresholdConfidenceGate.from_yaml(confidence_thresholds_path)
    else:
        confidence_gate = ThresholdConfidenceGate(thresholds={})

    # --- Confidence gating (optional) ---
    if ablation_yaml.get("use_confidence_gating", True):
        entities = confidence_gate.filter_trusted(entities)
        evidence_provider.update_entities(entities)

    # --- Reconciliation ---
    # Group entities by attribute name (stored in the unit field by
    # _build_entities_from_ground_truth) rather than by entity_type, so that
    # building_height and rear_garden_depth entities are reconciled separately.
    # Fall back to entity_type.value for entities without an attribute tag.
    reconciled_evidence: dict[str, ReconciledEvidence] = {}
    if ablation_yaml.get("use_evidence_reconciliation", True):
        from planproof.schemas.entities import ExtractedEntity

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

    # --- Assessability ---
    assessability_results: list[Any] = []
    assessable_ids: set[str]

    if ablation_yaml.get("use_assessability_engine", True):
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
        # No assessability engine: treat all rules as assessable
        assessable_ids = set(all_rule_ids)

    # --- Rule evaluation ---
    verdicts: list[Any] = []

    if not ablation_yaml.get("use_rule_engine", True):
        # ablation_a: no rule engine, return empty verdicts
        return verdicts, assessability_results

    fallback_missing = ReconciledEvidence(
        attribute="__fallback__",
        status=ReconciliationStatus.MISSING,
        sources=[],
    )

    for config, evaluator in loaded_rule_pairs:
        if config.rule_id not in assessable_ids:
            continue
        # Look up reconciled evidence by the primary attribute of this rule
        # (stored in parameters["attribute"] for single-attribute rules, or
        # parameters["numerator_attribute"] for ratio rules).  Fall back to
        # rule_id if no attribute key is found (should not happen in practice).
        primary_attr = (
            config.parameters.get("attribute")
            or config.parameters.get("numerator_attribute")
            or config.rule_id
        )
        evidence = reconciled_evidence.get(primary_attr, fallback_missing)
        # Inject rule_id into params so evaluators can produce correctly-labelled
        # RuleVerdict objects.  Evaluators read rule_id from self._params first,
        # then fall back to the passed params dict.
        params_with_id = {**config.parameters, "rule_id": config.rule_id}
        verdict = evaluator.evaluate(evidence, params_with_id)
        verdicts.append(verdict)

    return verdicts, assessability_results


# ---------------------------------------------------------------------------
# Result construction helpers
# ---------------------------------------------------------------------------


def _verdicts_to_rule_results(
    verdicts: list[Any],
    assessable_rule_ids: set[str],
    all_rule_ids: list[str],
    config_name: str,
    set_id: str,
) -> list[Any]:
    """Convert RuleVerdict objects + assessability info to RuleResult objects.

    Rules that were not evaluated (not assessable) get a NOT_ASSESSABLE
    predicted outcome.
    """
    from planproof.evaluation.results import RuleResult

    # Map verdict rule_id -> predicted outcome
    verdict_map: dict[str, str] = {v.rule_id: str(v.outcome) for v in verdicts}

    rule_results: list[RuleResult] = []
    for rule_id in all_rule_ids:
        if rule_id in verdict_map:
            predicted = verdict_map[rule_id]
        elif rule_id in assessable_rule_ids:
            # Assessable but no verdict produced (e.g. ablation_a)
            predicted = "NOT_ASSESSABLE"
        else:
            predicted = "NOT_ASSESSABLE"

        rule_results.append(
            RuleResult(
                rule_id=rule_id,
                # Ground truth outcome is looked up below; placeholder for now
                ground_truth_outcome="PASS",
                predicted_outcome=predicted,  # type: ignore[arg-type]
                config_name=config_name,
                set_id=set_id,
            )
        )

    return rule_results


def _apply_ground_truth_outcomes(
    rule_results: list[Any],
    ground_truth: dict[str, Any],
) -> list[Any]:
    """Patch ground_truth_outcome on each RuleResult from the ground truth."""
    gt_verdicts: dict[str, str] = {
        v["rule_id"]: v["outcome"]
        for v in ground_truth.get("rule_verdicts", [])
    }
    for rr in rule_results:
        gt_outcome = gt_verdicts.get(rr.rule_id, "PASS")
        # RuleResult is a Pydantic model — rebuild with correct ground truth
        from planproof.evaluation.results import RuleResult

        idx = rule_results.index(rr)
        rule_results[idx] = RuleResult(
            rule_id=rr.rule_id,
            ground_truth_outcome=gt_outcome,  # type: ignore[arg-type]
            predicted_outcome=rr.predicted_outcome,
            config_name=rr.config_name,
            set_id=rr.set_id,
        )
    return rule_results


# ---------------------------------------------------------------------------
# Baseline runners
# ---------------------------------------------------------------------------


def _llm_api_key_available() -> bool:
    """Return True if at least one supported LLM API key is set in the env."""
    import os

    return bool(
        os.environ.get("PLANPROOF_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GROQ_API_KEY")
    )


def _run_baseline(
    config_name: str,
    ground_truth: dict[str, Any],
    configs_dir: Path,
    ablation_yaml: dict[str, Any],
) -> list[Any]:
    """Run naive or strong baseline against ground-truth text.

    Returns a list of RuleVerdict objects.  If no LLM API key is configured
    this function logs a warning and returns an empty list so the caller can
    still create a result record with no verdicts.
    """
    if not _llm_api_key_available():
        warnings.warn(
            f"Skipping {config_name}: no LLM API key configured. "
            "Set PLANPROOF_LLM_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY.",
            stacklevel=2,
        )
        return []

    import os

    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
    from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
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

    rules_dir = configs_dir / "rules"
    loaded_rule_pairs = factory.load_rules(rules_dir)
    rule_configs = [cfg for cfg, _ in loaded_rule_pairs]

    # Use ground-truth text values as a proxy for extracted text
    extracted_text = _ground_truth_to_text(ground_truth)

    # Build an LLM client from environment variables
    llm_client = _build_llm_client_from_env()

    if config_name == "naive_baseline":
        from planproof.evaluation.baselines.naive import NaiveBaselineRunner

        runner = NaiveBaselineRunner(llm_client=llm_client, rules=rule_configs)
        return runner.run(extracted_text)

    if config_name == "strong_baseline":
        from planproof.evaluation.baselines.strong import StrongBaselineRunner

        runner = StrongBaselineRunner(llm_client=llm_client, rules=rule_configs)
        return runner.run(extracted_text)

    raise ValueError(f"Unknown baseline config: {config_name!r}")


def _ground_truth_to_text(ground_truth: dict[str, Any]) -> str:
    """Produce a plain-text representation of ground truth values.

    Used as a proxy for real OCR text when running baselines in the ablation
    study so that the LLM receives something sensible without re-running
    document extraction.
    """
    lines: list[str] = []
    lines.append(f"Planning Application Set: {ground_truth.get('set_id', 'unknown')}")
    lines.append("")
    for val in ground_truth.get("values", []):
        lines.append(
            f"{val['attribute']}: {val.get('display_text', val.get('value'))} "
            f"({val.get('unit', '')})"
        )
    lines.append("")
    for doc in ground_truth.get("documents", []):
        lines.append(f"Document: {doc.get('filename', '')}")
        for ext in doc.get("extractions", []):
            text = ext.get("text_rendered") or str(ext.get("value", ""))
            lines.append(f"  {ext.get('attribute', '')}: {text}")
    return "\n".join(lines)


def _build_llm_client_from_env() -> Any:
    """Instantiate the best available LLM client from environment variables."""
    import os

    api_key = (
        os.environ.get("PLANPROOF_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or ""
    )

    if os.environ.get("OPENAI_API_KEY") or (
        os.environ.get("PLANPROOF_LLM_API_KEY")
        and os.environ.get("PLANPROOF_LLM_PROVIDER", "").lower() == "openai"
    ):
        from planproof.infrastructure.openai_client import OpenAIClient

        return OpenAIClient(api_key=api_key)

    if os.environ.get("GROQ_API_KEY") or (
        os.environ.get("PLANPROOF_LLM_API_KEY")
        and os.environ.get("PLANPROOF_LLM_PROVIDER", "groq").lower() == "groq"
    ):
        from planproof.infrastructure.groq_client import GroqClient

        return GroqClient(api_key=api_key)

    # Default: Groq
    from planproof.infrastructure.groq_client import GroqClient

    return GroqClient(api_key=api_key)


# ---------------------------------------------------------------------------
# Per-experiment runner
# ---------------------------------------------------------------------------


def run_experiment(
    config_name: str,
    test_set_dir: Path,
    output_dir: Path,
    configs_dir: Path,
    resume: bool,
) -> dict[str, Any] | None:
    """Run one (config_name, test_set) experiment and save the result.

    Returns a summary dict with keys: config_name, set_id, skipped, error,
    n_rules, n_pass, n_fail, n_not_assessable.  Returns None if an
    unrecoverable setup error occurred before any processing.
    """
    from planproof.evaluation.results import ExperimentResult, RuleResult, result_exists, save_result

    ground_truth = load_ground_truth(test_set_dir)
    set_id: str = ground_truth.get("set_id", test_set_dir.name)

    summary: dict[str, Any] = {
        "config_name": config_name,
        "set_id": set_id,
        "skipped": False,
        "error": None,
        "n_rules": 0,
        "n_pass": 0,
        "n_fail": 0,
        "n_not_assessable": 0,
    }

    if resume and result_exists(config_name, set_id, output_dir):
        _log.debug("Skipping %s / %s (result exists)", config_name, set_id)
        summary["skipped"] = True
        return summary

    try:
        ablation_yaml = _load_ablation_config(configs_dir, config_name)
    except FileNotFoundError as exc:
        summary["error"] = str(exc)
        _log.error("Config load error: %s", exc)
        return summary

    try:
        # --- Load rules to know which rule IDs exist ---
        from planproof.reasoning.evaluators.factory import RuleFactory
        from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
        from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
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

        all_rule_ids = [
            cfg.rule_id for cfg, _ in factory.load_rules(configs_dir / "rules")
        ]

        # --- Dispatch to the correct runner ---
        if config_name in PIPELINE_CONFIGS:
            verdicts, assessability_results = _run_pipeline_config(
                config_name, ground_truth, ablation_yaml, configs_dir,
                test_set_dir=test_set_dir,
            )
        else:
            verdicts = _run_baseline(config_name, ground_truth, configs_dir, ablation_yaml)
            assessability_results = []

        # --- Build RuleResult list ---
        evaluated_rule_ids = {v.rule_id for v in verdicts}
        # Rules listed in the ground truth that did not appear in verdicts are
        # considered NOT_ASSESSABLE (not evaluated by this config).
        rule_results: list[RuleResult] = []
        gt_verdicts: dict[str, str] = {
            v["rule_id"]: v["outcome"]
            for v in ground_truth.get("rule_verdicts", [])
        }

        # Build lookup from assessability results for SABLE metric extraction
        assessability_map: dict[str, Any] = {
            ar.rule_id: ar for ar in assessability_results
        }

        for rule_id in all_rule_ids:
            gt_outcome = gt_verdicts.get(rule_id, "PASS")
            if rule_id in evaluated_rule_ids:
                verdict_obj = next(v for v in verdicts if v.rule_id == rule_id)
                predicted = str(verdict_obj.outcome)
            else:
                predicted = "NOT_ASSESSABLE"

            # Extract SABLE metrics from assessability result
            ar = assessability_map.get(rule_id)
            belief = ar.belief if ar else None
            plausibility = ar.plausibility if ar else None
            conflict_mass_val = ar.conflict_mass if ar else None
            blocking_reason_val = str(ar.blocking_reason) if ar else None

            # Map PARTIALLY_ASSESSABLE through
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

        # --- Counts for summary ---
        n_pass = sum(1 for r in rule_results if r.predicted_outcome == "PASS")
        n_fail = sum(1 for r in rule_results if r.predicted_outcome == "FAIL")
        n_na = sum(1 for r in rule_results if r.predicted_outcome in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"))

        # --- Build and save ExperimentResult ---
        exp_result = ExperimentResult(
            config_name=config_name,
            set_id=set_id,
            rule_results=rule_results,
            metadata={
                "ablation_config": ablation_yaml,
                "category": ground_truth.get("category", "unknown"),
                "difficulty": ground_truth.get("difficulty", "unknown"),
                "seed": ground_truth.get("seed"),
                "n_documents": len(ground_truth.get("documents", [])),
            },
            timestamp=datetime.now(timezone.utc),
        )
        dest = save_result(exp_result, output_dir)
        _log.info("Saved result to %s", dest)

        summary.update(
            n_rules=len(rule_results),
            n_pass=n_pass,
            n_fail=n_fail,
            n_not_assessable=n_na,
        )

    except Exception as exc:  # noqa: BLE001
        summary["error"] = f"{type(exc).__name__}: {exc}"
        _log.exception("Error running %s / %s: %s", config_name, set_id, exc)

    return summary


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


def _print_summary_table(summaries: list[dict[str, Any]]) -> None:
    """Print a human-readable summary table of all experiment runs."""
    col_widths = {
        "config": max(len("Config"), max((len(s["config_name"]) for s in summaries), default=0)),
        "set_id": max(len("Set ID"), max((len(s["set_id"]) for s in summaries), default=0)),
        "status": 12,
        "pass": 6,
        "fail": 6,
        "na": 6,
    }

    header = (
        f"{'Config':<{col_widths['config']}}  "
        f"{'Set ID':<{col_widths['set_id']}}  "
        f"{'Status':<{col_widths['status']}}  "
        f"{'Pass':>{col_widths['pass']}}  "
        f"{'Fail':>{col_widths['fail']}}  "
        f"{'N/A':>{col_widths['na']}}"
    )
    sep = "-" * len(header)

    print("\n" + sep)
    print(header)
    print(sep)

    for s in summaries:
        if s.get("skipped"):
            status = "SKIPPED"
        elif s.get("error"):
            status = "ERROR"
        else:
            status = "OK"

        print(
            f"{s['config_name']:<{col_widths['config']}}  "
            f"{s['set_id']:<{col_widths['set_id']}}  "
            f"{status:<{col_widths['status']}}  "
            f"{s['n_pass']:>{col_widths['pass']}}  "
            f"{s['n_fail']:>{col_widths['fail']}}  "
            f"{s['n_not_assessable']:>{col_widths['na']}}"
        )

    print(sep)

    total = len(summaries)
    ok = sum(1 for s in summaries if not s.get("skipped") and not s.get("error"))
    skipped = sum(1 for s in summaries if s.get("skipped"))
    errors = sum(1 for s in summaries if s.get("error"))
    print(f"\nTotal: {total}  OK: {ok}  Skipped: {skipped}  Errors: {errors}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = _parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        _log.setLevel(logging.INFO)

    data_dir: Path = args.data_dir
    output_dir: Path = args.output_dir
    configs_dir: Path = args.configs_dir

    if not data_dir.exists():
        print(f"ERROR: data directory does not exist: {data_dir}", file=sys.stderr)
        return 1

    # Discover test sets
    test_sets = discover_test_sets(data_dir)
    if not test_sets:
        print(
            f"WARNING: no test sets (directories with ground_truth.json) found under {data_dir}",
            file=sys.stderr,
        )
        return 0

    print(f"Discovered {len(test_sets)} test set(s) under {data_dir}")

    # Determine which configs to run
    configs_to_run = [args.config] if args.config else ALL_CONFIGS
    print(f"Running configs: {', '.join(configs_to_run)}")
    print(f"Output directory: {output_dir}")
    if args.resume:
        print("Resume mode: skipping existing results.")

    all_summaries: list[dict[str, Any]] = []

    total_combinations = len(configs_to_run) * len(test_sets)
    done = 0

    for config_name in configs_to_run:
        for test_set_dir in test_sets:
            done += 1
            # Quick set_id preview (without loading the file)
            set_id_preview = test_set_dir.name
            print(
                f"  [{done}/{total_combinations}] {config_name} / {set_id_preview} ...",
                end="",
                flush=True,
            )

            summary = run_experiment(
                config_name=config_name,
                test_set_dir=test_set_dir,
                output_dir=output_dir,
                configs_dir=configs_dir,
                resume=args.resume,
            )

            if summary is None:
                print(" FATAL")
                all_summaries.append(
                    {
                        "config_name": config_name,
                        "set_id": set_id_preview,
                        "skipped": False,
                        "error": "Fatal setup error",
                        "n_rules": 0,
                        "n_pass": 0,
                        "n_fail": 0,
                        "n_not_assessable": 0,
                    }
                )
            elif summary.get("skipped"):
                print(" skipped")
                all_summaries.append(summary)
            elif summary.get("error"):
                print(f" ERROR: {summary['error']}")
                all_summaries.append(summary)
            else:
                print(
                    f" OK  (pass={summary['n_pass']} fail={summary['n_fail']}"
                    f" na={summary['n_not_assessable']})"
                )
                all_summaries.append(summary)

    _print_summary_table(all_summaries)

    # Return non-zero if any experiment failed (not just skipped)
    n_errors = sum(1 for s in all_summaries if s.get("error"))
    return 1 if n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
