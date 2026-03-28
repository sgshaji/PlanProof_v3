"""Configuration schemas for the PlanProof pipeline.

PipelineConfig uses pydantic-settings to load values from environment
variables (prefixed PLANPROOF_) with fallback to .env files.
AblationConfig controls which system components are active, enabling
the ablation study infrastructure described in Layer 5.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ConfidenceThresholds(BaseModel):
    """Per-method, per-entity-type confidence thresholds.

    # WHY: Different extraction methods have different reliability profiles.
    # VLM_FINETUNED on measurements may be highly accurate (low threshold),
    # while OCR_LLM on handwritten certificates needs a higher bar.
    # Structure: { "OCR_LLM": { "MEASUREMENT": 0.8, "ADDRESS": 0.7 }, ... }
    """

    thresholds: dict[str, dict[str, float]]

    model_config = {"from_attributes": True}


class AblationConfig(BaseModel):
    """Toggles for each major system component.

    # WHY: The ablation study (Layer 5) measures the contribution of each
    # component by selectively disabling them. These flags are read by the
    # pipeline orchestrator to skip or include steps.
    #
    # DESIGN: evaluation_strategy distinguishes three fundamentally different
    # code paths. "pipeline" runs the normal step-registry pipeline.
    # "naive_llm" and "strong_llm" bypass it entirely — they concatenate OCR
    # text and call the LLM directly. The component toggles below only apply
    # when evaluation_strategy is "pipeline".
    """

    # Which evaluation approach to use
    # "pipeline" = normal pipeline with component toggles below
    # "naive_llm" = single LLM call on concatenated OCR text (naive baseline)
    # "strong_llm" = per-rule CoT LLM calls with evidence citation (strong baseline)
    evaluation_strategy: str = "pipeline"

    # Component toggles — only apply when evaluation_strategy = "pipeline"
    use_snkg: bool = True
    use_rule_engine: bool = True
    use_confidence_gating: bool = True
    use_assessability_engine: bool = True
    use_evidence_reconciliation: bool = True
    use_vlm: bool = True

    model_config = {"from_attributes": True}


class PipelineConfig(BaseSettings):
    """Top-level configuration for the PlanProof pipeline.

    Reads from environment variables prefixed with PLANPROOF_ (e.g.
    PLANPROOF_LLM_PROVIDER) and falls back to defaults where provided.
    """

    # --- LLM Provider ---
    # WHY: Default to Groq (free tier, cloud) for development.
    # Ollama available as local fallback. OpenAI for production evaluation.
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # --- VLM Provider (can differ from LLM for multimodal tasks) ---
    vlm_provider: str = "openai"
    vlm_model: str = "gpt-4o"
    vlm_extraction_method: str = "zeroshot"  # "zeroshot" | "structured"

    # --- Neo4j Aura (cloud) ---
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # --- Paths ---
    cache_dir: Path = Path("data/.llm_cache")
    configs_dir: Path = Path("configs")

    # --- Performance ---
    max_concurrent_llm_calls: int = 5

    # --- Nested configs ---
    confidence: ConfidenceThresholds = ConfidenceThresholds(
        thresholds={}
    )
    ablation: AblationConfig = AblationConfig()

    model_config = {
        "env_prefix": "PLANPROOF_",
        "from_attributes": True,
    }
