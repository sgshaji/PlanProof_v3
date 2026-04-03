"""Tests for datagen YAML config loading and validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from planproof.datagen.scenario.config_loader import (
    ConfigValidationError,
    load_degradation_presets,
    load_profiles,
    load_rule_configs,
)

CONFIGS_DIR = Path("configs/datagen")


class TestRuleConfigLoading:
    def test_load_all_rule_configs(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        # Now 8 rules: R001, R002, R003 + C001, C002, C003, C004, C006
        assert len(rules) == 8
        rule_ids = {r.rule_id for r in rules}
        assert {"R001", "R002", "R003"}.issubset(rule_ids)

    def test_rule_has_compliant_range(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        r001 = next(r for r in rules if r.rule_id == "R001")
        assert r001.compliant_range.min < r001.compliant_range.max

    def test_rule_has_violation_types(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        r001 = next(r for r in rules if r.rule_id == "R001")
        assert len(r001.violation_types) >= 1
        assert all(v.name for v in r001.violation_types)

    def test_invalid_yaml_raises_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("rule_id: R999\n")
        with pytest.raises(ConfigValidationError):
            load_rule_configs(tmp_path)


class TestProfileLoading:
    def test_load_all_profiles(self) -> None:
        profiles = load_profiles(CONFIGS_DIR / "profiles")
        assert len(profiles) == 3
        ids = {p.profile_id for p in profiles}
        assert "standard_3file" in ids

    def test_profile_has_document_composition(self) -> None:
        profiles = load_profiles(CONFIGS_DIR / "profiles")
        std = next(p for p in profiles if p.profile_id == "standard_3file")
        assert len(std.document_composition) >= 2


class TestAllRuleConfigsLoad:
    def test_seven_configs_load(self) -> None:
        configs = load_rule_configs(Path("configs/datagen/rules"))
        rule_ids = {c.rule_id for c in configs}
        assert rule_ids == {"R001", "R002", "R003", "C001", "C002", "C003", "C004", "C006"}


class TestMultiAttributeConfig:
    def test_default_value_type_is_numeric(self) -> None:
        from planproof.datagen.scenario.config_loader import DatagenRuleConfig

        rules = load_rule_configs(CONFIGS_DIR / "rules")
        r001 = next(r for r in rules if r.rule_id == "R001")
        assert r001.value_type == "numeric"

    def test_default_extra_attributes_empty(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        r001 = next(r for r in rules if r.rule_id == "R001")
        assert r001.extra_attributes == []

    def test_default_valid_values_empty(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        r001 = next(r for r in rules if r.rule_id == "R001")
        assert r001.valid_values == []

    def test_categorical_config_via_model_validate(self) -> None:
        from planproof.datagen.scenario.config_loader import DatagenRuleConfig

        raw = {
            "rule_id": "TEST_CAT",
            "attribute": "cert_type",
            "unit": "categorical",
            "value_type": "categorical",
            "compliant_range": {"min": 0.0, "max": 0.0},
            "violation_types": [{"name": "invalid", "range": {"min": 0.0, "max": 0.0}}],
            "evidence_locations": [{"doc_type": "FORM", "field": "cert_type"}],
            "valid_values": ["A", "B"],
            "invalid_values": ["X"],
        }
        cfg = DatagenRuleConfig.model_validate(raw)
        assert cfg.value_type == "categorical"
        assert cfg.valid_values == ["A", "B"]
        assert cfg.invalid_values == ["X"]

    def test_extra_attributes_field_loaded(self) -> None:
        from planproof.datagen.scenario.config_loader import DatagenRuleConfig

        raw = {
            "rule_id": "TEST_MULTI",
            "attribute": "site_coverage",
            "unit": "percent",
            "value_type": "numeric",
            "compliant_range": {"min": 10.0, "max": 50.0},
            "violation_types": [{"name": "exceeds_max", "range": {"min": 50.1, "max": 80.0}}],
            "evidence_locations": [{"doc_type": "FORM", "field": "site_coverage"}],
            "extra_attributes": [
                {"attribute": "building_footprint_area", "unit": "m²", "type": "derived"}
            ],
        }
        cfg = DatagenRuleConfig.model_validate(raw)
        assert len(cfg.extra_attributes) == 1
        assert cfg.extra_attributes[0]["attribute"] == "building_footprint_area"


class TestDegradationPresetLoading:
    def test_load_all_presets(self) -> None:
        presets = load_degradation_presets(CONFIGS_DIR / "degradation")
        assert len(presets) == 3
        ids = {p.preset_id for p in presets}
        assert "clean" in ids
        assert "moderate_scan" in ids
        assert "heavy_scan" in ids

    def test_preset_has_transforms(self) -> None:
        presets = load_degradation_presets(CONFIGS_DIR / "degradation")
        moderate = next(p for p in presets if p.preset_id == "moderate_scan")
        assert len(moderate.transforms) >= 1
