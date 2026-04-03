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
        # Only check numeric values (categorical/string values use str_value,
        # not a numeric display_text, so they are excluded from this assertion).
        for v in values:
            if v.str_value is None:
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


class TestGenerateValuesExtended:
    """Tests for multi-attribute, categorical, string_pair, and numeric_pair generation."""

    def _get_rule(self, rule_id: str) -> object:
        rules = load_rule_configs(RULES_DIR)
        return next(r for r in rules if r.rule_id == rule_id)

    def test_categorical_compliant_value(self) -> None:
        rule = self._get_rule("C001")
        values = generate_values([rule], "compliant", seed=42)
        cert = next(v for v in values if v.attribute == "certificate_type")
        assert cert.str_value in rule.valid_values  # type: ignore[attr-defined]

    def test_string_pair_compliant_values(self) -> None:
        rule = self._get_rule("C002")
        values = generate_values([rule], "compliant", seed=42)
        attrs = {v.attribute for v in values}
        assert "form_address" in attrs
        assert "drawing_address" in attrs

    def test_numeric_pair_compliant_values(self) -> None:
        rule = self._get_rule("C003")
        values = generate_values([rule], "compliant", seed=42)
        attrs = {v.attribute for v in values}
        assert "stated_site_area" in attrs
        assert "reference_parcel_area" in attrs

    def test_extra_attributes_generated(self) -> None:
        rule = self._get_rule("R003")
        values = generate_values([rule], "compliant", seed=42)
        attrs = {v.attribute for v in values}
        assert "building_footprint_area" in attrs
        assert "total_site_area" in attrs
        assert "zone_category" in attrs

    def test_noncompliant_categorical_invalid(self) -> None:
        rule = self._get_rule("C001")
        # Try a few seeds to find one that produces a violation
        found_invalid = False
        for seed in range(20):
            values = generate_values([rule], "noncompliant", seed=seed)
            cert = next(v for v in values if v.attribute == "certificate_type")
            if cert.str_value in rule.invalid_values:  # type: ignore[attr-defined]
                found_invalid = True
                break
        assert found_invalid, "No seed produced an invalid certificate type for C001"

    def test_seven_rules_generate_values(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        assert len(rules) == 8
        values = generate_values(rules, "compliant", seed=42)
        # Should have at least 8 values (one primary per rule), but likely more
        assert len(values) >= 8

    def test_compute_verdicts_all_pass_compliant(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        verdicts = compute_verdicts(values, rules)
        # All 8 rules should have verdicts
        assert len(verdicts) == 8
        assert all(v.outcome == "PASS" for v in verdicts)

    def test_compute_verdicts_noncompliant_has_fail(self) -> None:
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
