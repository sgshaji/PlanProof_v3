"""Tests for configuration schema models."""
from __future__ import annotations

from planproof.schemas.config import (
    AblationConfig,
    ConfidenceThresholds,
    PipelineConfig,
)


class TestPipelineConfig:
    def test_defaults(self) -> None:
        config = PipelineConfig(
            llm_api_key="test-key",
            neo4j_uri="bolt://localhost:7687",
            neo4j_password="test",
        )
        assert config.llm_provider == "groq"
        assert config.llm_model == "llama-3.3-70b-versatile"
        assert config.neo4j_user == "neo4j"
        assert config.max_concurrent_llm_calls == 5

    def test_override_provider(self) -> None:
        config = PipelineConfig(
            llm_provider="openai",
            llm_model="gpt-4o",
            llm_api_key="sk-test",
            neo4j_uri="bolt://localhost:7687",
            neo4j_password="test",
        )
        assert config.llm_provider == "openai"
        assert config.llm_model == "gpt-4o"


class TestAblationConfig:
    def test_defaults_all_enabled(self) -> None:
        config = AblationConfig()
        assert config.use_snkg is True
        assert config.use_rule_engine is True
        assert config.use_confidence_gating is True
        assert config.use_assessability_engine is True
        assert config.use_evidence_reconciliation is True
        assert config.use_vlm is True
        assert config.evaluation_strategy == "pipeline"

    def test_disable_component(self) -> None:
        config = AblationConfig(use_vlm=False, use_snkg=False)
        assert config.use_vlm is False
        assert config.use_snkg is False
        assert config.use_rule_engine is True


class TestConfidenceThresholds:
    def test_empty_thresholds(self) -> None:
        ct = ConfidenceThresholds(thresholds={})
        assert ct.thresholds == {}

    def test_nested_thresholds(self) -> None:
        ct = ConfidenceThresholds(
            thresholds={
                "OCR_LLM": {"MEASUREMENT": 0.8, "ADDRESS": 0.7},
                "VLM_ZEROSHOT": {"MEASUREMENT": 0.6},
            }
        )
        assert ct.thresholds["OCR_LLM"]["MEASUREMENT"] == 0.8
        assert ct.thresholds["VLM_ZEROSHOT"]["MEASUREMENT"] == 0.6
