"""Tests for rule schema models — round-trip serialisation and validation."""
from __future__ import annotations

from planproof.schemas.assessability import EvidenceRequirement
from planproof.schemas.rules import RuleConfig, RuleOutcome, RuleVerdict


class TestRuleConfig:
    def test_valid_creation(self) -> None:
        config = RuleConfig(
            rule_id="R001",
            description="Minimum setback from front boundary",
            policy_source="LEP 2012 s4.3",
            evaluation_type="numeric_threshold",
            parameters={"min_value": 6.0, "unit": "metres"},
            required_evidence=[
                EvidenceRequirement(
                    attribute="front_setback",
                    acceptable_sources=["DRAWING"],
                    min_confidence=0.8,
                    spatial_grounding=None,
                )
            ],
        )
        assert config.rule_id == "R001"
        assert config.parameters["min_value"] == 6.0
        assert len(config.required_evidence) == 1

    def test_json_round_trip(self) -> None:
        config = RuleConfig(
            rule_id="R002",
            description="Max building height",
            policy_source="LEP 2012 s4.3",
            evaluation_type="numeric_threshold",
            parameters={"max_value": 9.0},
            required_evidence=[],
        )
        restored = RuleConfig.model_validate_json(config.model_dump_json())
        assert restored == config


class TestRuleVerdict:
    def test_pass_verdict(self, sample_entity) -> None:  # type: ignore[no-untyped-def]
        verdict = RuleVerdict(
            rule_id="R001",
            outcome=RuleOutcome.PASS,
            evidence_used=[sample_entity],
            explanation="Front setback 7.5m >= 6.0m minimum",
            evaluated_value=7.5,
            threshold=6.0,
        )
        assert verdict.outcome == RuleOutcome.PASS
        assert len(verdict.evidence_used) == 1

    def test_fail_verdict(self) -> None:
        verdict = RuleVerdict(
            rule_id="R001",
            outcome=RuleOutcome.FAIL,
            evidence_used=[],
            explanation="Front setback 4.0m < 6.0m minimum",
            evaluated_value=4.0,
            threshold=6.0,
        )
        assert verdict.outcome == RuleOutcome.FAIL

    def test_json_round_trip(self) -> None:
        verdict = RuleVerdict(
            rule_id="R001",
            outcome=RuleOutcome.PASS,
            evidence_used=[],
            explanation="OK",
            evaluated_value=7.5,
            threshold=6.0,
        )
        restored = RuleVerdict.model_validate_json(
            verdict.model_dump_json()
        )
        assert restored == verdict
