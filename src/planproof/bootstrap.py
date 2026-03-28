"""Composition root — the ONLY file that knows about concrete types.

# DESIGN: All dependency wiring happens here. No module ever instantiates its
# own dependencies. The bootstrap reads configuration, creates concrete
# instances, and registers pipeline steps. Ablation toggles are handled via
# conditional step registration — modules are unaware ablations exist.
#
# See: docs/adr/010-composition-root-di.md
"""

from __future__ import annotations

from collections.abc import Mapping

from planproof.infrastructure.cached_llm import CachedLLMClient
from planproof.infrastructure.llm_cache import SQLiteLLMCache
from planproof.infrastructure.logging import configure_logging, get_logger
from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.ingestion.entity_extractor import LLMEntityExtractor
from planproof.ingestion.text_extractor import PdfPlumberExtractor
from planproof.ingestion.vision_extractor import VisionExtractor
from planproof.ingestion.vlm_spatial_extractor import VLMSpatialExtractor
from planproof.interfaces.llm import LLMClient
from planproof.output.evidence_request import MinEvidenceRequestGenerator
from planproof.output.scoring import ComplianceScorer  # noqa: F401
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
from planproof.reasoning.assessability import DefaultAssessabilityEvaluator
from planproof.reasoning.confidence import ThresholdConfidenceGate
from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
from planproof.reasoning.evaluators.factory import RuleFactory
from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator
from planproof.reasoning.reconciliation import PairwiseReconciler
from planproof.representation.flat_evidence import FlatEvidenceProvider
from planproof.representation.normalisation import Normaliser
from planproof.representation.snkg import Neo4jSNKG
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
    classifier = _create_classifier(config)
    ocr = _create_ocr()
    entity_extractor = _create_entity_extractor(config, _cached_llm)
    vision_extractor = _create_vision_extractor(config)

    pipeline.register(ClassificationStep(classifier=classifier))
    pipeline.register(
        TextExtractionStep(
            ocr=ocr,
            entity_extractor=entity_extractor,
            vision_extractor=vision_extractor,
        )
    )

    if config.ablation.use_vlm:
        vlm_spatial = _create_vlm_spatial_extractor(config)
        if vlm_spatial is not None:
            pipeline.register(VLMExtractionStep(vlm=vlm_spatial))

    # --- Reasoning layer components (constructed before pipeline registration) ---
    reconciler = _create_reconciler()
    confidence_gate = _create_confidence_gate(config)

    # Load rules once — used by both AssessabilityStep and RuleEvaluationStep
    rules_dir = config.configs_dir / "rules"
    rule_factory = _register_evaluators()
    loaded_rule_pairs = rule_factory.load_rules(rules_dir)
    rules_dict = {cfg.rule_id: cfg for cfg, _ in loaded_rule_pairs}

    # Layer 2: Representation
    pipeline.register(NormalisationStep(normaliser=Normaliser()))

    # Determine evidence_provider — SNKG if available, stub otherwise
    snkg_instance: Neo4jSNKG | None = None
    if config.ablation.use_snkg:
        snkg_instance = _create_snkg(config)
        if snkg_instance is not None:
            pipeline.register(GraphPopulationStep(populator=snkg_instance))

    # Select evidence provider: SNKG (graph) or FlatEvidenceProvider (Ablation B).
    # FlatEvidenceProvider is initialised empty here; ReconciliationStep calls
    # update_entities() once extraction has populated context["entities"].
    # Typed as object because Neo4jSNKG and FlatEvidenceProvider satisfy the
    # EvidenceProvider Protocol structurally — mypy cannot verify this without
    # explicit Protocol subclassing, so we use object and suppress below.
    evidence_provider: object
    if snkg_instance is not None:
        evidence_provider = snkg_instance
    else:
        evidence_provider = FlatEvidenceProvider([])

    # Layer 3: Reasoning
    if config.ablation.use_evidence_reconciliation:
        pipeline.register(
            ReconciliationStep(
                reconciler=reconciler,
                evidence_provider=evidence_provider,
            )
        )

    if config.ablation.use_confidence_gating:
        pipeline.register(ConfidenceGatingStep(gate=confidence_gate))

    if config.ablation.use_assessability_engine:
        pipeline.register(
            AssessabilityStep(
                evaluator=_create_assessability_evaluator(
                    evidence_provider=evidence_provider,
                    confidence_gate=confidence_gate,
                    reconciler=reconciler,
                    rules=rules_dict,
                )
            )
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
    pipeline.register(EvidenceRequestStep(generator=_create_evidence_request_generator(config)))

    logger.info(
        "pipeline_built",
        total_steps=len(pipeline._steps),
        ablation=config.ablation.model_dump(),
    )

    return pipeline


# ---------------------------------------------------------------------------
# Component factories — each returns a concrete implementation wired from
# config.  Keeping them as named functions makes the build_pipeline body easy
# to read and the individual factories independently testable.
# ---------------------------------------------------------------------------


def _create_classifier(config: PipelineConfig) -> RuleBasedClassifier:
    return RuleBasedClassifier(
        patterns_path=config.configs_dir / "classifier_patterns.yaml"
    )

def _create_ocr() -> PdfPlumberExtractor:
    return PdfPlumberExtractor()

def _create_entity_extractor(
    config: PipelineConfig, cached_llm: CachedLLMClient
) -> LLMEntityExtractor:
    return LLMEntityExtractor(
        llm=cached_llm,
        prompts_dir=config.configs_dir / "prompts",
        model=config.llm_model,
    )

def _create_vlm_client(config: PipelineConfig) -> object | None:
    """Return a VLM client (OpenAI or GeminiVisionAdapter) based on config.

    Resolution order:
    1. vlm_provider == "gemini" AND gemini_api_key set  → GeminiVisionAdapter
    2. vlm_provider == "openai" AND llm_api_key set     → openai.OpenAI
    3. No key available                                  → None (VLM disabled)
    """
    provider = config.vlm_provider.lower()

    if provider == "gemini":
        if not config.gemini_api_key:
            logger.warning("no_gemini_key_vlm_disabled")
            return None
        from planproof.infrastructure.gemini_client import GeminiVisionAdapter

        logger.info("vlm_client_gemini", model=config.vlm_model)
        return GeminiVisionAdapter(
            api_key=config.gemini_api_key,
            model=config.vlm_model,
        )

    # Default: OpenAI
    api_key = config.openai_api_key or config.llm_api_key
    if not api_key:
        logger.warning("no_openai_key_vlm_disabled")
        return None
    import openai

    logger.info("vlm_client_openai", model=config.vlm_model)
    return openai.OpenAI(api_key=api_key)


def _create_vision_extractor(config: PipelineConfig) -> VisionExtractor | None:
    client = _create_vlm_client(config)
    if client is None:
        return None
    return VisionExtractor(
        openai_client=client,
        prompts_dir=config.configs_dir / "prompts",
        model=config.vlm_model,
    )


def _create_vlm_spatial_extractor(config: PipelineConfig) -> VLMSpatialExtractor | None:
    client = _create_vlm_client(config)
    if client is None:
        return None
    return VLMSpatialExtractor(
        openai_client=client,
        prompts_dir=config.configs_dir / "prompts",
        model=config.vlm_model,
        method=config.vlm_extraction_method,
    )


def _create_snkg(config: PipelineConfig) -> Neo4jSNKG | None:
    """Instantiate a Neo4jSNKG from config, or return None if unconfigured.

    # DESIGN: Follows the same lazy-import pattern as VLMSpatialExtractor so
    # that neo4j driver creation is deferred and the module stays importable
    # even when Neo4j is not available in the test environment.
    """
    if not config.neo4j_uri:
        logger.warning("neo4j_uri_not_set_snkg_disabled")
        return None
    import neo4j
    driver = neo4j.GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_user, config.neo4j_password),
    )
    return Neo4jSNKG(driver=driver)


def _create_reconciler() -> PairwiseReconciler:
    """Return a PairwiseReconciler with default tolerances."""
    return PairwiseReconciler()


def _create_confidence_gate(config: PipelineConfig) -> ThresholdConfidenceGate:
    """Load ThresholdConfidenceGate from configs/confidence_thresholds.yaml."""
    yaml_path = config.configs_dir / "confidence_thresholds.yaml"
    return ThresholdConfidenceGate.from_yaml(yaml_path)


def _create_assessability_evaluator(
    *,
    evidence_provider: object,
    confidence_gate: ThresholdConfidenceGate,
    reconciler: PairwiseReconciler,
    rules: Mapping[str, object],
) -> DefaultAssessabilityEvaluator:
    """Wire a DefaultAssessabilityEvaluator with all reasoning dependencies.

    ``evidence_provider`` and ``rules`` are typed as ``object`` because the
    concrete values (Neo4jSNKG or FlatEvidenceProvider, RuleConfig dicts)
    satisfy the Protocols structurally — mypy cannot verify structural
    compatibility without explicit Protocol annotations on those classes.
    """
    return DefaultAssessabilityEvaluator(
        evidence_provider=evidence_provider,  # type: ignore[arg-type]
        confidence_gate=confidence_gate,
        reconciler=reconciler,
        rules=rules,  # type: ignore[arg-type]
    )


def _create_evidence_request_generator(
    config: PipelineConfig,
) -> MinEvidenceRequestGenerator:
    """Load evidence guidance from YAML and return a MinEvidenceRequestGenerator."""
    yaml_path = config.configs_dir / "evidence_guidance.yaml"
    return MinEvidenceRequestGenerator.from_yaml(yaml_path)
