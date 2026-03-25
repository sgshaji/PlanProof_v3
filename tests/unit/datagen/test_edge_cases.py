"""Tests for edge-case strategy pure functions."""
from __future__ import annotations

from pathlib import Path

import pytest

from planproof.datagen.scenario.config_loader import (
    load_profiles,
    load_rule_configs,
)
from planproof.datagen.scenario.edge_cases import apply_edge_case
from planproof.datagen.scenario.generator import build_scenario

RULES_DIR = Path("configs/datagen/rules")
PROFILES_DIR = Path("configs/datagen/profiles")


def _make_scenario():
    """Build a standard compliant scenario for testing."""
    rules = load_rule_configs(RULES_DIR)
    profiles = load_profiles(PROFILES_DIR)
    std = next(
        p for p in profiles if p.profile_id == "standard_3file"
    )
    return build_scenario(std, rules, "compliant", seed=42)


class TestMissingEvidence:
    def test_removes_value_placement(self) -> None:
        original = _make_scenario()
        result = apply_edge_case(original, "missing_evidence", seed=1)
        # At least one document should have fewer values_to_place
        orig_total = sum(
            len(d.values_to_place) for d in original.documents
        )
        result_total = sum(
            len(d.values_to_place) for d in result.documents
        )
        assert result_total < orig_total


class TestConflictingValues:
    def test_adds_different_value(self) -> None:
        original = _make_scenario()
        result = apply_edge_case(
            original, "conflicting_values", seed=1
        )
        assert len(result.values) > len(original.values)


class TestLowConfidenceScan:
    def test_changes_preset(self) -> None:
        original = _make_scenario()
        result = apply_edge_case(
            original, "low_confidence_scan", seed=1
        )
        assert result.degradation_preset == "heavy_scan"


class TestPartialDocuments:
    def test_removes_document(self) -> None:
        original = _make_scenario()
        result = apply_edge_case(
            original, "partial_documents", seed=1
        )
        assert len(result.documents) < len(original.documents)


class TestAmbiguousUnits:
    def test_removes_unit_from_display(self) -> None:
        original = _make_scenario()
        result = apply_edge_case(
            original, "ambiguous_units", seed=1
        )
        # At least one value should have a numeric-only display_text
        changed = [
            v
            for v_orig, v_new in zip(
                original.values, result.values
            )
            if (v := v_new).display_text != v_orig.display_text
        ]
        assert len(changed) >= 1
        for v in changed:
            float(v.display_text)  # should not raise


class TestDispatcher:
    def test_unknown_strategy_raises(self) -> None:
        scenario = _make_scenario()
        with pytest.raises(ValueError, match="Unknown"):
            apply_edge_case(scenario, "nonexistent", seed=1)
