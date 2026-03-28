"""Integration tests — verify all ablation YAML configs produce valid pipelines.

For each config in configs/ablation/ we:
1. Load the YAML file.
2. Build an AblationConfig from the loaded values.
3. Create a PipelineConfig with that ablation config.
4. Call build_pipeline(config) from planproof.bootstrap.
5. Assert it does not crash and that pipeline._steps is a non-empty list.

Configs that require Neo4j (use_snkg=True) are skipped when the Neo4j URI is
not configured in the environment — that is expected behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from planproof.bootstrap import build_pipeline
from planproof.schemas.config import AblationConfig, PipelineConfig

ABLATION_DIR = Path("configs/ablation")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_ablation_yaml(filename: str) -> dict:
    """Load a YAML file from configs/ablation/ and return its contents as a dict."""
    path = ABLATION_DIR / filename
    with path.open() as fh:
        data = yaml.safe_load(fh)
    # YAML files may return None for empty files; guard against that.
    return data or {}


def _make_config(ablation_data: dict) -> PipelineConfig:
    """Construct a PipelineConfig whose ablation sub-config is built from *ablation_data*."""
    ablation = AblationConfig(**ablation_data)
    # PipelineConfig reads from env vars; override only the ablation sub-config.
    return PipelineConfig(ablation=ablation)


def _needs_neo4j(config: PipelineConfig) -> bool:
    """Return True if this config requires a Neo4j connection."""
    return config.ablation.use_snkg and not config.neo4j_uri


def _needs_llm_key(config: PipelineConfig) -> bool:
    """Return True if this config requires a real LLM API key.

    Ollama is the only provider that works without an API key.
    """
    return config.llm_provider.lower() != "ollama" and not config.llm_api_key


def _skip_if_missing_credentials(config: PipelineConfig) -> None:
    """Call pytest.skip() when required credentials are absent."""
    if _needs_llm_key(config):
        pytest.skip(
            f"LLM API key not configured for provider '{config.llm_provider}' "
            "— set PLANPROOF_LLM_API_KEY or PLANPROOF_LLM_PROVIDER=ollama"
        )
    if _needs_neo4j(config):
        pytest.skip("Neo4j URI not configured — skipping SNKG-dependent config")


# ---------------------------------------------------------------------------
# Test cases — one per YAML file
# ---------------------------------------------------------------------------


class TestAblationConfigs:
    """Validate that every ablation YAML produces a buildable pipeline."""

    def test_full_system_config(self) -> None:
        """All toggles True — should register the maximum set of steps."""
        data = _load_ablation_yaml("full_system.yaml")
        config = _make_config(data)
        _skip_if_missing_credentials(config)

        pipeline = build_pipeline(config)

        assert isinstance(pipeline._steps, list)
        assert len(pipeline._steps) > 0

    def test_ablation_a_config(self) -> None:
        """use_snkg=True, use_rule_engine=False — extraction + graph only."""
        data = _load_ablation_yaml("ablation_a.yaml")
        config = _make_config(data)

        assert config.ablation.use_snkg is True
        assert config.ablation.use_rule_engine is False

        _skip_if_missing_credentials(config)

        pipeline = build_pipeline(config)

        assert isinstance(pipeline._steps, list)
        assert len(pipeline._steps) > 0

    def test_ablation_b_config(self) -> None:
        """use_snkg=False — uses FlatEvidenceProvider; no Neo4j required."""
        data = _load_ablation_yaml("ablation_b.yaml")
        config = _make_config(data)

        assert config.ablation.use_snkg is False

        _skip_if_missing_credentials(config)

        pipeline = build_pipeline(config)

        assert isinstance(pipeline._steps, list)
        assert len(pipeline._steps) > 0

    def test_ablation_c_config(self) -> None:
        """use_confidence_gating=False — ConfidenceGatingStep should be absent."""
        data = _load_ablation_yaml("ablation_c.yaml")
        config = _make_config(data)

        assert config.ablation.use_confidence_gating is False

        _skip_if_missing_credentials(config)

        pipeline = build_pipeline(config)

        assert isinstance(pipeline._steps, list)
        assert len(pipeline._steps) > 0

    def test_ablation_d_config(self) -> None:
        """use_assessability_engine=False — AssessabilityStep should be absent."""
        data = _load_ablation_yaml("ablation_d.yaml")
        config = _make_config(data)

        assert config.ablation.use_assessability_engine is False

        _skip_if_missing_credentials(config)

        pipeline = build_pipeline(config)

        assert isinstance(pipeline._steps, list)
        assert len(pipeline._steps) > 0

    def test_naive_baseline_config(self) -> None:
        """evaluation_strategy='naive_llm' — pipeline still builds (strategy used at run-time)."""
        data = _load_ablation_yaml("naive_baseline.yaml")
        config = _make_config(data)

        assert config.ablation.evaluation_strategy == "naive_llm"
        # All component toggles should be False for the naive baseline.
        assert config.ablation.use_snkg is False

        _skip_if_missing_credentials(config)

        pipeline = build_pipeline(config)

        assert isinstance(pipeline._steps, list)
        assert len(pipeline._steps) > 0

    def test_strong_baseline_config(self) -> None:
        """evaluation_strategy='strong_llm' — pipeline still builds (strategy used at run-time)."""
        data = _load_ablation_yaml("strong_baseline.yaml")
        config = _make_config(data)

        assert config.ablation.evaluation_strategy == "strong_llm"
        assert config.ablation.use_snkg is False

        _skip_if_missing_credentials(config)

        pipeline = build_pipeline(config)

        assert isinstance(pipeline._steps, list)
        assert len(pipeline._steps) > 0
