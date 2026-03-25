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
        assert len(rules) == 3
        rule_ids = {r.rule_id for r in rules}
        assert rule_ids == {"R001", "R002", "R003"}

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
