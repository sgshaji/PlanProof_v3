"""Composition root — the ONLY file that knows about concrete types.

# DESIGN: All dependency wiring happens here. No module ever instantiates its
# own dependencies. The bootstrap reads configuration, creates concrete
# instances, and registers pipeline steps. Ablation toggles are handled via
# conditional step registration — modules are unaware ablations exist.
#
# See: docs/adr/010-composition-root-di.md
"""

from __future__ import annotations

from pathlib import Path

from planproof.infrastructure.cached_llm import CachedLLMClient
from planproof.infrastructure.llm_cache import SQLiteLLMCache
from planproof.infrastructure.logging import configure_logging, get_logger
from planproof.interfaces.llm import LLMClient
from planproof.pipeline.pipeline import Pipeline
from planproof.pipeline.steps.assessability import AssessabilityStep
from planproof.pipeline.steps.classification import ClassificationStep
from planproof.pipeline.steps.confidence_gating import ConfidenceGatingStep
from planproof.pipeline.steps.evidence_request import EvidenceRequestStep
from planproof.pipeline.steps.graph_population import GraphPopulationStep
from planproof.pipeline.steps.normalisation import NormalisationStep
from planproof.pipeline.steps.reconciliation import ReconciliationStep
from planproof.pipeline.steps.rule_evaluation import RuleEvaluationStep
from planproof.pipeline.steps.scoring import ScoringStep
from planproof.pipeline.steps.text_extraction import TextExtractionStep
from planproof.pipeline.steps.vlm_extraction import VLMExtractionStep
from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
from planproof.reasoning.evaluators.factory import RuleFactory
from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator
from planproof.schemas.config import PipelineConfig

logger = get_logger(__name__)


def _create_llm_client(config: PipelineConfig) -> LLMClient:
    """Instantiate the correct LLM client based on config.

    # DESIGN: Provider selection happens here and ONLY here. No module
    # downstream knows which provider is in use — they see LLMClient Protocol.
    """
    provider = config.llm_provider.lower()

    if provider == "ollama":
        from planproof.infrastructure.ollama_client import OllamaClient

        return OllamaClient(base_url=config.ollama_base_url)

    if provider == "groq":
        from planproof.infrastructure.groq_client import GroqClient

        return GroqClient(api_key=config.llm_api_key)

    if provider == "openai":
        from planproof.infrastructure.openai_client import OpenAIClient

        return OpenAIClient(api_key=config.llm_api_key)

    msg = (
        f"Unknown LLM provider: '{provider}'. "
        "Supported: ollama (free), groq (free tier), openai (paid)"
    )
    raise ValueError(msg)


def _register_evaluators() -> RuleFactory:
    """Register all built-in rule evaluation types with the factory.

    # DESIGN: OCP — adding a new evaluation type requires only a new class
    # and one line here. Existing evaluators are never modified.
    """
    factory = RuleFactory()
    RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
    RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
    RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
    RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
    RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
    RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)
    return factory


def build_pipeline(config: PipelineConfig) -> Pipeline:
    """Wire all dependencies and return a configured pipeline.

    This is the single integration point for the entire system. Every concrete
    class is instantiated here and injected into the components that need it.

    Parameters
    ----------
    config:
        Validated pipeline configuration (from env vars / YAML).

    Returns
    -------
    Pipeline:
        A fully wired pipeline ready to process application sets.
    """
    configure_logging()

    # --- Infrastructure layer ---
    llm_client = _create_llm_client(config)
    cache = SQLiteLLMCache(cache_dir=config.cache_dir)
    _cached_llm = CachedLLMClient(client=llm_client, cache=cache)

    # --- Rule factory ---
    rule_factory = _register_evaluators()

    logger.info(
        "llm_provider_configured",
        provider=config.llm_provider,
        model=config.llm_model,
    )

    # --- Build pipeline with conditional step registration ---
    # DESIGN: Ablation toggles are handled here via conditional registration.
    # Pipeline steps themselves are unaware that ablations exist.
    pipeline = Pipeline(config=config)

    # Layer 1: Ingestion — always active
    # WHY: Concrete extractors are placeholder stubs until their respective
    # phases are implemented. The pipeline skeleton runs with NotImplementedError
    # steps during early development — this is intentional.
    pipeline.register(ClassificationStep(classifier=_stub_classifier()))
    pipeline.register(
        TextExtractionStep(
            ocr=_stub_ocr(),
            entity_extractor=_stub_entity_extractor(),
        )
    )

    if config.ablation.use_vlm:
        pipeline.register(VLMExtractionStep(vlm_extractor=_stub_vlm()))

    # Layer 2: Representation
    pipeline.register(NormalisationStep())

    if config.ablation.use_snkg:
        pipeline.register(
            GraphPopulationStep(populator=_stub_populator())
        )

    # Layer 3: Reasoning
    if config.ablation.use_evidence_reconciliation:
        pipeline.register(
            ReconciliationStep(reconciler=_stub_reconciler())
        )

    if config.ablation.use_confidence_gating:
        pipeline.register(ConfidenceGatingStep(gate=_stub_gate()))

    if config.ablation.use_assessability_engine:
        pipeline.register(
            AssessabilityStep(evaluator=_stub_assessability())
        )

    if config.ablation.use_rule_engine:
        pipeline.register(
            RuleEvaluationStep(
                rule_factory=rule_factory,
                rules_dir=config.configs_dir / "rules",
            )
        )

    # Layer 4: Output — always active
    pipeline.register(ScoringStep())
    pipeline.register(EvidenceRequestStep())

    logger.info(
        "pipeline_built",
        total_steps=len(pipeline._steps),
        ablation=config.ablation.model_dump(),
    )

    return pipeline


# ---------------------------------------------------------------------------
# Stub factories — return placeholder objects until concrete implementations
# are built in later phases. These satisfy Protocol interfaces structurally.
# ---------------------------------------------------------------------------


class _StubClassifier:
    """Placeholder until Phase 2."""

    def classify(self, file_path: Path) -> None:  # type: ignore[override]
        raise NotImplementedError("Concrete classifier implemented in Phase 2")


class _StubOCR:
    """Placeholder until Phase 2."""

    def extract_text(self, document: Path) -> None:  # type: ignore[override]
        raise NotImplementedError("Concrete OCR implemented in Phase 2")


class _StubEntityExtractor:
    """Placeholder until Phase 2."""

    def extract_entities(self, text: object) -> list:  # type: ignore[override]
        raise NotImplementedError("Concrete entity extractor implemented in Phase 2")


class _StubVLM:
    """Placeholder until Phase 2."""

    def extract_spatial_attributes(self, image: Path) -> list:  # type: ignore[override]
        raise NotImplementedError("Concrete VLM extractor implemented in Phase 2")


class _StubPopulator:
    """Placeholder until Phase 3."""

    def populate_from_entities(self, entities: list) -> None:
        raise NotImplementedError("Concrete graph populator implemented in Phase 3")


class _StubReconciler:
    """Placeholder until Phase 4."""

    def reconcile(self, entities: list, attribute: str) -> None:  # type: ignore[override]
        raise NotImplementedError("Concrete reconciler implemented in Phase 4")


class _StubGate:
    """Placeholder until Phase 4."""

    def is_trustworthy(self, entity: object) -> bool:
        raise NotImplementedError("Concrete confidence gate implemented in Phase 4")

    def filter_trusted(self, entities: list) -> list:
        raise NotImplementedError("Concrete confidence gate implemented in Phase 4")


class _StubAssessability:
    """Placeholder until Phase 4."""

    def evaluate(self, rule_id: str) -> None:  # type: ignore[override]
        msg = "Concrete assessability evaluator implemented in Phase 4"
        raise NotImplementedError(msg)


def _stub_classifier() -> _StubClassifier:
    return _StubClassifier()


def _stub_ocr() -> _StubOCR:
    return _StubOCR()


def _stub_entity_extractor() -> _StubEntityExtractor:
    return _StubEntityExtractor()


def _stub_vlm() -> _StubVLM:
    return _StubVLM()


def _stub_populator() -> _StubPopulator:
    return _StubPopulator()


def _stub_reconciler() -> _StubReconciler:
    return _StubReconciler()


def _stub_gate() -> _StubGate:
    return _StubGate()


def _stub_assessability() -> _StubAssessability:
    return _StubAssessability()
