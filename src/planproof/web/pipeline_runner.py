"""Pipeline runner for the web demo — yields stage results for SSE streaming."""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Generator

from planproof.infrastructure.logging import get_logger

logger = get_logger(__name__)


def run_pipeline_stages(input_dir: Path) -> Generator[dict[str, Any], None, None]:
    """Run the full pipeline on input_dir, yielding one dict per stage.

    Each dict has: stage (str), title (str), data (dict with stage-specific results).
    """
    configs_dir = Path("configs")

    # -- Stage 1: Classification --
    yield _stage_classify(input_dir, configs_dir)

    # Get classified docs for subsequent stages
    classified_docs = _classify_all(input_dir, configs_dir)

    # -- Stage 2: Extraction --
    extraction_result = _stage_extract(classified_docs, configs_dir)
    yield extraction_result
    entities = extraction_result.get("data", {}).get("_entities", [])

    # -- Stage 3: Normalisation (silent — merged into extraction output) --
    from planproof.representation.normalisation import Normaliser

    normaliser = Normaliser()
    entities = normaliser.normalise_all(entities)

    # -- Stage 4: SNKG Graph --
    yield _stage_snkg(entities)

    # -- Stage 5: Reconciliation --
    reconciled, recon_result = _stage_reconcile(entities)
    yield recon_result

    # -- Stage 6: SABLE Assessability --
    assessability_results, sable_result = _stage_sable(entities, reconciled, configs_dir)
    yield sable_result

    # -- Stage 7: Rule Evaluation --
    yield _stage_evaluate(assessability_results, reconciled, configs_dir)

    # -- Stage 8: Ablation Comparison --
    yield _stage_ablation_comparison()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_all(input_dir: Path, configs_dir: Path) -> list[tuple[Path, Any]]:
    """Classify all documents in input_dir."""
    from planproof.ingestion.classifier import RuleBasedClassifier

    patterns_path = configs_dir / "classifier_patterns.yaml"
    classifier = RuleBasedClassifier(patterns_path)

    results = []
    for f in sorted(input_dir.iterdir()):
        if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"):
            try:
                classified = classifier.classify(f)
                results.append((f, classified))
            except Exception:
                logger.warning("classification_failed", file=f.name)
    return results


def _stage_classify(input_dir: Path, configs_dir: Path) -> dict:
    """Stage 1: Document Classification."""
    classified = _classify_all(input_dir, configs_dir)
    docs = []
    for path, c in classified:
        docs.append({
            "filename": path.name,
            "doc_type": c.doc_type.value,
            "confidence": round(c.confidence, 2),
            "has_text_layer": c.has_text_layer,
        })
    return {
        "stage": "classification",
        "title": "Document Upload & Classification (M1)",
        "data": {"documents": docs},
    }


def _stage_extract(classified_docs: list, configs_dir: Path) -> dict:
    """Stage 2: LLM/VLM Entity Extraction."""
    from planproof.ingestion.entity_extractor import LLMEntityExtractor
    from planproof.ingestion.text_extractor import PdfPlumberExtractor

    entities = []
    entity_dicts: list[dict] = []

    llm_client = _build_llm_client()
    text_extractor = PdfPlumberExtractor()

    for doc_path, classified in classified_docs:
        doc_type = classified.doc_type.value
        suffix = doc_path.suffix.lower()
        is_image = suffix in (".png", ".jpg", ".jpeg")

        try:
            if not is_image and classified.has_text_layer and llm_client:
                raw_text = text_extractor.extract_text(doc_path)
                extractor = LLMEntityExtractor(
                    llm=llm_client,
                    prompts_dir=configs_dir / "prompts",
                    doc_type=doc_type,
                )
                extracted = extractor.extract_entities(raw_text, doc_type=doc_type)
                entities.extend(extracted)
                for e in extracted:
                    entity_dicts.append({
                        "attribute": e.attribute,
                        "value": e.value,
                        "unit": e.unit,
                        "confidence": round(e.confidence, 2) if e.confidence else None,
                        "source": doc_path.name,
                        "method": (
                            e.extraction_method.value
                            if e.extraction_method
                            else "UNKNOWN"
                        ),
                    })
        except Exception as exc:
            logger.warning("extraction_failed", doc=doc_path.name, error=str(exc))

    if not entity_dicts:
        entity_dicts.append({
            "attribute": "(none)",
            "value": "No entities extracted — API key may be missing",
            "unit": None,
            "confidence": None,
            "source": "N/A",
            "method": "N/A",
        })

    return {
        "stage": "extraction",
        "title": "LLM/VLM Entity Extraction (M2+M3)",
        "data": {"entities": entity_dicts, "_entities": entities},
    }


def _stage_snkg(entities: list) -> dict:
    """Stage 3: SNKG Knowledge Graph visualisation."""
    nodes = []
    edges = []

    # Central property node
    nodes.append({"id": "property", "label": "Property", "type": "property"})

    seen_attrs: set[str] = set()
    for e in entities:
        attr = e.attribute or e.entity_type.value
        if attr in seen_attrs:
            continue
        seen_attrs.add(attr)
        value = e.value if e.value else ""
        unit = e.unit or ""
        nodes.append({
            "id": attr,
            "label": f"{attr}: {value} {unit}".strip(),
            "type": e.entity_type.value.lower(),
        })
        edges.append({"from": "property", "to": attr, "label": "HAS_ATTRIBUTE"})

    return {
        "stage": "snkg",
        "title": "SNKG Knowledge Graph (M5 — Neo4j)",
        "data": {"nodes": nodes, "edges": edges},
    }


def _stage_reconcile(entities: list) -> tuple[dict, dict]:
    """Stage 4: Cross-Document Reconciliation."""
    from planproof.reasoning.reconciliation import PairwiseReconciler

    reconciler = PairwiseReconciler()

    groups: dict[str, list] = defaultdict(list)
    for e in entities:
        key = e.attribute if e.attribute else e.entity_type.value
        groups[key].append(e)

    reconciled: dict = {}
    recon_items: list[dict] = []
    for attr, group in groups.items():
        result = reconciler.reconcile(group, attr)
        reconciled[attr] = result
        recon_items.append({
            "attribute": attr,
            "status": result.status.value,
            "best_value": str(result.best_value) if result.best_value is not None else None,
            "source_count": len(group),
        })

    return reconciled, {
        "stage": "reconciliation",
        "title": "Cross-Document Reconciliation (M6)",
        "data": {"items": recon_items},
    }


def _stage_sable(
    entities: list, reconciled: dict, configs_dir: Path
) -> tuple[list, dict]:
    """Stage 5: SABLE Assessability Engine."""
    from planproof.reasoning.assessability import DefaultAssessabilityEvaluator
    from planproof.reasoning.confidence import ThresholdConfidenceGate
    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.reasoning.reconciliation import PairwiseReconciler
    from planproof.representation.flat_evidence import FlatEvidenceProvider

    _register_all_evaluators()

    factory = RuleFactory()
    loaded_rules = factory.load_rules(configs_dir / "rules")
    rules_dict = {cfg.rule_id: cfg for cfg, _ in loaded_rules}

    evidence_provider = FlatEvidenceProvider(entities)
    conf_path = configs_dir / "confidence_thresholds.yaml"
    confidence_gate = (
        ThresholdConfidenceGate.from_yaml(conf_path)
        if conf_path.exists()
        else ThresholdConfidenceGate(thresholds={})
    )
    reconciler = PairwiseReconciler()

    evaluator = DefaultAssessabilityEvaluator(
        evidence_provider=evidence_provider,
        confidence_gate=confidence_gate,
        reconciler=reconciler,
        rules=rules_dict,
    )

    results = []
    sable_items: list[dict] = []
    for rule_id in sorted(rules_dict.keys()):
        try:
            result = evaluator.evaluate(rule_id)
            results.append(result)
            sable_items.append({
                "rule_id": result.rule_id,
                "status": result.status,
                "belief": round(result.belief, 3),
                "plausibility": round(result.plausibility, 3),
                "conflict_mass": round(result.conflict_mass, 3),
                "blocking_reason": (
                    result.blocking_reason.value if result.blocking_reason else "NONE"
                ),
            })
        except Exception as exc:
            sable_items.append({
                "rule_id": rule_id,
                "status": "ERROR",
                "belief": 0.0,
                "plausibility": 0.0,
                "conflict_mass": 0.0,
                "blocking_reason": str(exc),
            })

    return results, {
        "stage": "sable",
        "title": "SABLE Assessability Engine (M8 — Dempster-Shafer)",
        "data": {"rules": sable_items},
    }


def _stage_evaluate(
    assessability_results: list, reconciled: dict, configs_dir: Path
) -> dict:
    """Stage 6: Rule Evaluation & Verdicts."""
    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus

    _register_all_evaluators()
    factory = RuleFactory()
    loaded_rules = factory.load_rules(configs_dir / "rules")

    assessable_ids = {
        r.rule_id for r in assessability_results if r.status == "ASSESSABLE"
    }

    fallback = ReconciledEvidence(
        attribute="__fallback__",
        status=ReconciliationStatus.MISSING,
        sources=[],
    )

    verdicts: list[dict] = []
    for config, evaluator in loaded_rules:
        rule_id = config.rule_id
        ar = next((r for r in assessability_results if r.rule_id == rule_id), None)

        if rule_id in assessable_ids:
            attrs_list = config.parameters.get("attributes", [])
            primary_attr = (
                config.parameters.get("attribute")
                or config.parameters.get("numerator_attribute")
                or config.parameters.get("attribute_a")
                or config.parameters.get("zone_attribute")
                or (f"proposed_{attrs_list[0]}" if attrs_list else None)
                or rule_id
            )
            evidence = reconciled.get(primary_attr, fallback)
            params = {**config.parameters, "rule_id": rule_id}
            try:
                verdict = evaluator.evaluate(evidence, params)
                verdicts.append({
                    "rule_id": rule_id,
                    "outcome": verdict.outcome.value,
                    "explanation": verdict.explanation,
                    "description": config.description,
                })
            except Exception as exc:
                verdicts.append({
                    "rule_id": rule_id,
                    "outcome": "ERROR",
                    "explanation": str(exc),
                    "description": config.description,
                })
        else:
            status = ar.status if ar else "NOT_ASSESSABLE"
            missing_desc = ""
            if ar and ar.missing_evidence:
                missing_desc = ", ".join(req.attribute for req in ar.missing_evidence)
            verdicts.append({
                "rule_id": rule_id,
                "outcome": status,
                "explanation": (
                    f"Missing evidence: {missing_desc}"
                    if missing_desc
                    else "Insufficient evidence"
                ),
                "description": config.description,
            })

    return {
        "stage": "verdicts",
        "title": "Rule Evaluation & Verdicts (M9)",
        "data": {"verdicts": verdicts},
    }


def _stage_ablation_comparison() -> dict:
    """Stage 7: Load pre-computed ablation results for comparison."""
    from planproof.evaluation.results import load_all_results

    comparison: dict[str, dict] = {}
    for config in ["full_system", "ablation_d"]:
        config_dir = Path(f"data/results/{config}")
        if not config_dir.exists():
            continue
        experiments = load_all_results(config_dir)
        pass_count = sum(
            1
            for exp in experiments
            for rr in exp.rule_results
            if rr.predicted_outcome == "PASS"
        )
        true_fail = sum(
            1
            for exp in experiments
            for rr in exp.rule_results
            if rr.predicted_outcome == "FAIL" and rr.ground_truth_outcome == "FAIL"
        )
        false_fail = sum(
            1
            for exp in experiments
            for rr in exp.rule_results
            if rr.predicted_outcome == "FAIL" and rr.ground_truth_outcome == "PASS"
        )
        pa = sum(
            1
            for exp in experiments
            for rr in exp.rule_results
            if rr.predicted_outcome == "PARTIALLY_ASSESSABLE"
        )
        na = sum(
            1
            for exp in experiments
            for rr in exp.rule_results
            if rr.predicted_outcome == "NOT_ASSESSABLE"
        )
        comparison[config] = {
            "pass": pass_count,
            "true_fail": true_fail,
            "false_fail": false_fail,
            "pa": pa,
            "na": na,
        }

    return {
        "stage": "ablation",
        "title": "Ablation Comparison — With vs Without SABLE",
        "data": comparison,
    }


def _build_llm_client():
    """Build LLM client from env vars."""
    api_key = os.environ.get("PLANPROOF_LLM_API_KEY") or os.environ.get("GROQ_API_KEY") or ""
    if not api_key:
        return None
    try:
        from planproof.infrastructure.groq_client import GroqClient

        return GroqClient(api_key=api_key)
    except Exception:
        return None


def _register_all_evaluators() -> None:
    """Register all evaluator types in RuleFactory."""
    from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
    from planproof.reasoning.evaluators.boundary_verification import (
        BoundaryVerificationEvaluator,
    )
    from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
    from planproof.reasoning.evaluators.numeric_threshold import (
        NumericThresholdEvaluator,
    )
    from planproof.reasoning.evaluators.numeric_tolerance import (
        NumericToleranceEvaluator,
    )
    from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator
    from planproof.reasoning.evaluators.spatial_containment import (
        SpatialContainmentEvaluator,
    )

    RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
    RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
    RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
    RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
    RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
    RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)
    RuleFactory.register_evaluator("boundary_verification", BoundaryVerificationEvaluator)
    RuleFactory.register_evaluator("spatial_containment", SpatialContainmentEvaluator)
