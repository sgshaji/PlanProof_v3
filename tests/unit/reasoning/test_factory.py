"""Tests for RuleFactory — rule loading and evaluator creation."""
from __future__ import annotations

from pathlib import Path

from planproof.reasoning.evaluators.factory import RuleFactory
from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator


class TestRuleFactoryInjectsRuleId:
    """RuleFactory.load_rules must inject rule_id into evaluator parameters."""

    def test_loaded_evaluator_has_rule_id_in_params(self, tmp_path: Path) -> None:
        rule_yaml = tmp_path / "r001_test.yaml"
        rule_yaml.write_text(
            "rule_id: R001\n"
            "description: test\n"
            "policy_source: test_policy\n"
            "evaluation_type: numeric_threshold\n"
            "parameters:\n"
            "  attribute: building_height\n"
            "  operator: '<='\n"
            "  threshold: 8.0\n"
            "  unit: metres\n"
            "required_evidence:\n"
            "  - attribute: building_height\n"
            "    acceptable_sources: [DRAWING]\n"
            "    min_confidence: 0.7\n"
        )
        RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
        factory = RuleFactory()
        pairs = factory.load_rules(tmp_path)
        config, evaluator = pairs[0]
        assert evaluator._params["rule_id"] == "R001"  # type: ignore[attr-defined]

    def test_rule_id_injected_for_ratio_evaluator(self, tmp_path: Path) -> None:
        rule_yaml = tmp_path / "r003_test.yaml"
        rule_yaml.write_text(
            "rule_id: R003\n"
            "description: test ratio\n"
            "policy_source: test_policy\n"
            "evaluation_type: ratio_threshold\n"
            "parameters:\n"
            "  numerator_attribute: footprint_area\n"
            "  denominator_attribute: site_area\n"
            "  operator: '<='\n"
            "  threshold: 0.5\n"
            "required_evidence:\n"
            "  - attribute: footprint_area\n"
            "    acceptable_sources: [DRAWING]\n"
            "    min_confidence: 0.7\n"
        )
        RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
        factory = RuleFactory()
        pairs = factory.load_rules(tmp_path)
        config, evaluator = pairs[0]
        assert evaluator._params["rule_id"] == "R003"  # type: ignore[attr-defined]

    def test_rule_id_does_not_overwrite_existing_param(self, tmp_path: Path) -> None:
        """If YAML parameters already contain rule_id, the top-level value wins."""
        rule_yaml = tmp_path / "r001_test.yaml"
        rule_yaml.write_text(
            "rule_id: R001\n"
            "description: test\n"
            "policy_source: test_policy\n"
            "evaluation_type: numeric_threshold\n"
            "parameters:\n"
            "  attribute: building_height\n"
            "  operator: '<='\n"
            "  threshold: 8.0\n"
            "  rule_id: WRONG\n"
            "required_evidence:\n"
            "  - attribute: building_height\n"
            "    acceptable_sources: [DRAWING]\n"
            "    min_confidence: 0.7\n"
        )
        RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
        factory = RuleFactory()
        pairs = factory.load_rules(tmp_path)
        _config, evaluator = pairs[0]
        # Top-level rule_id should take precedence
        assert evaluator._params["rule_id"] == "R001"  # type: ignore[attr-defined]
