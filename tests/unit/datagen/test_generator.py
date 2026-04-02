"""Tests for scenario generation pure functions."""
from __future__ import annotations

from pathlib import Path

import pytest

from planproof.datagen.scenario.config_loader import (
    load_profiles,
    load_rule_configs,
)
from planproof.datagen.scenario.generator import (
    build_scenario,
    compute_verdicts,
    generate_values,
)
from planproof.datagen.scenario.models import Scenario

RULES_DIR = Path("configs/datagen/rules")
PROFILES_DIR = Path("configs/datagen/profiles")


class TestGenerateValues:
    def test_compliant_values_within_range(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        assert len(values) >= 3

    def test_noncompliant_has_values(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "noncompliant", seed=42)
        assert len(values) >= 3

    def test_seed_determinism(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        v1 = generate_values(rules, "compliant", seed=123)
        v2 = generate_values(rules, "compliant", seed=123)
        assert v1 == v2

    def test_different_seeds_differ(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        v1 = generate_values(rules, "compliant", seed=1)
        v2 = generate_values(rules, "compliant", seed=2)
        assert v1 != v2

    def test_display_text_contains_value(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        for v in values:
            assert str(round(v.value, 1)) in v.display_text


class TestComputeVerdicts:
    def test_compliant_all_pass(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        verdicts = compute_verdicts(values, rules)
        assert all(v.outcome == "PASS" for v in verdicts)

    def test_noncompliant_at_least_one_fail(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "noncompliant", seed=42)
        verdicts = compute_verdicts(values, rules)
        assert any(v.outcome == "FAIL" for v in verdicts)


class TestValueStringSupport:
    def test_value_default_str_value_is_none(self) -> None:
        from planproof.datagen.scenario.models import Value

        v = Value(attribute="cert_type", value=0.0, unit="categorical", display_text="A")
        assert v.str_value is None

    def test_value_with_str_value(self) -> None:
        from planproof.datagen.scenario.models import Value

        v = Value(
            attribute="cert_type",
            value=0.0,
            unit="categorical",
            display_text="A",
            str_value="A",
        )
        assert v.str_value == "A"

    def test_value_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        from planproof.datagen.scenario.models import Value

        v = Value(attribute="x", value=1.0, unit="m", display_text="1.0m", str_value="A")
        with pytest.raises(FrozenInstanceError):
            v.str_value = "B"  # type: ignore[misc]


class TestBuildScenario:
    def test_returns_complete_scenario(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        profiles = load_profiles(PROFILES_DIR)
        std = next(
            p for p in profiles if p.profile_id == "standard_3file"
        )
        scenario = build_scenario(std, rules, "compliant", seed=42)
        assert isinstance(scenario, Scenario)
        assert scenario.category == "compliant"
        assert len(scenario.values) >= 3
        assert len(scenario.documents) >= 2
        assert scenario.seed == 42
