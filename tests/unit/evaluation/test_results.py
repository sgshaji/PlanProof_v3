"""Tests for evaluation result data models and JSON I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from planproof.evaluation.results import (
    ExperimentResult,
    RuleResult,
    load_all_results,
    load_result,
    result_exists,
    save_result,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _rule_result(
    rule_id: str = "R001",
    ground_truth: str = "PASS",
    predicted: str = "PASS",
    config_name: str = "cfg-a",
    set_id: str = "set-01",
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        ground_truth_outcome=ground_truth,
        predicted_outcome=predicted,
        config_name=config_name,
        set_id=set_id,
    )


_SENTINEL: list[RuleResult] = []  # distinct sentinel to detect "not passed"


def _experiment_result(
    config_name: str = "cfg-a",
    set_id: str = "set-01",
    rule_results: list[RuleResult] | None = None,
    metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> ExperimentResult:
    resolved_rules = (
        [_rule_result(config_name=config_name, set_id=set_id)]
        if rule_results is None
        else rule_results
    )
    return ExperimentResult(
        config_name=config_name,
        set_id=set_id,
        rule_results=resolved_rules,
        metadata=metadata or {"duration_s": 1.23, "entity_count": 5},
        timestamp=timestamp or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# RuleResult — field validation
# ---------------------------------------------------------------------------


class TestRuleResultValidation:
    def test_valid_pass_pass(self) -> None:
        r = _rule_result(ground_truth="PASS", predicted="PASS")
        assert r.ground_truth_outcome == "PASS"
        assert r.predicted_outcome == "PASS"

    def test_valid_fail_not_assessable(self) -> None:
        r = _rule_result(ground_truth="FAIL", predicted="NOT_ASSESSABLE")
        assert r.ground_truth_outcome == "FAIL"
        assert r.predicted_outcome == "NOT_ASSESSABLE"

    def test_invalid_ground_truth_raises(self) -> None:
        with pytest.raises(Exception):
            RuleResult(
                rule_id="R001",
                ground_truth_outcome="UNKNOWN",
                predicted_outcome="PASS",
                config_name="cfg-a",
                set_id="set-01",
            )

    def test_invalid_predicted_raises(self) -> None:
        with pytest.raises(Exception):
            RuleResult(
                rule_id="R001",
                ground_truth_outcome="PASS",
                predicted_outcome="MAYBE",
                config_name="cfg-a",
                set_id="set-01",
            )

    def test_all_predicted_variants_accepted(self) -> None:
        for outcome in ("PASS", "FAIL", "NOT_ASSESSABLE"):
            r = _rule_result(predicted=outcome)
            assert r.predicted_outcome == outcome

    def test_rule_id_stored(self) -> None:
        r = _rule_result(rule_id="R042")
        assert r.rule_id == "R042"

    def test_config_name_and_set_id_stored(self) -> None:
        r = _rule_result(config_name="my-cfg", set_id="set-99")
        assert r.config_name == "my-cfg"
        assert r.set_id == "set-99"


# ---------------------------------------------------------------------------
# Round-trip save / load
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        original = _experiment_result()
        save_result(original, tmp_path)
        loaded = load_result(tmp_path / "cfg-a" / "set-01.json")

        assert loaded.config_name == original.config_name
        assert loaded.set_id == original.set_id
        assert loaded.metadata == original.metadata
        assert loaded.timestamp == original.timestamp
        assert len(loaded.rule_results) == len(original.rule_results)

    def test_round_trip_rule_results_fields(self, tmp_path: Path) -> None:
        rr = _rule_result(rule_id="R007", ground_truth="FAIL", predicted="NOT_ASSESSABLE")
        original = _experiment_result(rule_results=[rr])
        save_result(original, tmp_path)
        loaded = load_result(tmp_path / "cfg-a" / "set-01.json")

        assert loaded.rule_results[0].rule_id == "R007"
        assert loaded.rule_results[0].ground_truth_outcome == "FAIL"
        assert loaded.rule_results[0].predicted_outcome == "NOT_ASSESSABLE"

    def test_round_trip_empty_rule_results(self, tmp_path: Path) -> None:
        original = _experiment_result(rule_results=[])
        save_result(original, tmp_path)
        loaded = load_result(tmp_path / "cfg-a" / "set-01.json")
        assert loaded.rule_results == []

    def test_round_trip_metadata_arbitrary_types(self, tmp_path: Path) -> None:
        meta = {"duration_s": 2.5, "entity_count": 10, "notes": "test run", "flag": True}
        original = _experiment_result(metadata=meta)
        save_result(original, tmp_path)
        loaded = load_result(tmp_path / "cfg-a" / "set-01.json")
        assert loaded.metadata == meta

    def test_save_returns_correct_path(self, tmp_path: Path) -> None:
        result = _experiment_result(config_name="cfg-x", set_id="set-02")
        path = save_result(result, tmp_path)
        assert path == tmp_path / "cfg-x" / "set-02.json"
        assert path.exists()

    def test_save_creates_intermediate_dirs(self, tmp_path: Path) -> None:
        result = _experiment_result(config_name="nested/cfg", set_id="s1")
        path = save_result(result, tmp_path)
        assert path.exists()


# ---------------------------------------------------------------------------
# result_exists
# ---------------------------------------------------------------------------


class TestResultExists:
    def test_false_before_save(self, tmp_path: Path) -> None:
        assert result_exists("cfg-a", "set-01", tmp_path) is False

    def test_true_after_save(self, tmp_path: Path) -> None:
        result = _experiment_result(config_name="cfg-a", set_id="set-01")
        save_result(result, tmp_path)
        assert result_exists("cfg-a", "set-01", tmp_path) is True

    def test_false_for_different_set_id(self, tmp_path: Path) -> None:
        result = _experiment_result(config_name="cfg-a", set_id="set-01")
        save_result(result, tmp_path)
        assert result_exists("cfg-a", "set-02", tmp_path) is False

    def test_false_for_different_config_name(self, tmp_path: Path) -> None:
        result = _experiment_result(config_name="cfg-a", set_id="set-01")
        save_result(result, tmp_path)
        assert result_exists("cfg-b", "set-01", tmp_path) is False


# ---------------------------------------------------------------------------
# load_all_results
# ---------------------------------------------------------------------------


class TestLoadAllResults:
    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert load_all_results(tmp_path) == []

    def test_nonexistent_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert load_all_results(tmp_path / "does-not-exist") == []

    def test_loads_single_result(self, tmp_path: Path) -> None:
        save_result(_experiment_result(), tmp_path)
        results = load_all_results(tmp_path)
        assert len(results) == 1
        assert results[0].config_name == "cfg-a"

    def test_loads_across_multiple_config_subdirs(self, tmp_path: Path) -> None:
        save_result(_experiment_result(config_name="cfg-a", set_id="s1"), tmp_path)
        save_result(_experiment_result(config_name="cfg-b", set_id="s1"), tmp_path)
        save_result(_experiment_result(config_name="cfg-c", set_id="s1"), tmp_path)
        results = load_all_results(tmp_path)
        assert len(results) == 3
        config_names = {r.config_name for r in results}
        assert config_names == {"cfg-a", "cfg-b", "cfg-c"}

    def test_loads_multiple_sets_within_same_config(self, tmp_path: Path) -> None:
        save_result(_experiment_result(config_name="cfg-a", set_id="s1"), tmp_path)
        save_result(_experiment_result(config_name="cfg-a", set_id="s2"), tmp_path)
        results = load_all_results(tmp_path)
        assert len(results) == 2
        set_ids = {r.set_id for r in results}
        assert set_ids == {"s1", "s2"}

    def test_all_results_are_experiment_result_instances(self, tmp_path: Path) -> None:
        save_result(_experiment_result(config_name="cfg-a", set_id="s1"), tmp_path)
        save_result(_experiment_result(config_name="cfg-b", set_id="s2"), tmp_path)
        results = load_all_results(tmp_path)
        assert all(isinstance(r, ExperimentResult) for r in results)


# ---------------------------------------------------------------------------
# RuleResult — SABLE fields
# ---------------------------------------------------------------------------


class TestRuleResultSableFields:
    def test_partially_assessable_accepted(self) -> None:
        r = _rule_result(predicted="PARTIALLY_ASSESSABLE")
        assert r.predicted_outcome == "PARTIALLY_ASSESSABLE"

    def test_sable_fields_default_none(self) -> None:
        r = _rule_result()
        assert r.belief is None
        assert r.plausibility is None
        assert r.conflict_mass is None
        assert r.blocking_reason is None

    def test_sable_fields_stored(self) -> None:
        r = RuleResult(
            rule_id="R001",
            ground_truth_outcome="PASS",
            predicted_outcome="PARTIALLY_ASSESSABLE",
            config_name="cfg-a",
            set_id="set-01",
            belief=0.85,
            plausibility=0.95,
            conflict_mass=0.02,
            blocking_reason="NONE",
        )
        assert r.belief == 0.85
        assert r.plausibility == 0.95
        assert r.conflict_mass == 0.02
        assert r.blocking_reason == "NONE"

    def test_sable_fields_round_trip(self, tmp_path: Path) -> None:
        rr = RuleResult(
            rule_id="R010",
            ground_truth_outcome="FAIL",
            predicted_outcome="PARTIALLY_ASSESSABLE",
            config_name="cfg-sable",
            set_id="set-rt",
            belief=0.7,
            plausibility=0.9,
            conflict_mass=0.05,
            blocking_reason="LOW_EVIDENCE",
        )
        original = _experiment_result(config_name="cfg-sable", set_id="set-rt", rule_results=[rr])
        save_result(original, tmp_path)
        loaded = load_result(tmp_path / "cfg-sable" / "set-rt.json")

        lr = loaded.rule_results[0]
        assert lr.predicted_outcome == "PARTIALLY_ASSESSABLE"
        assert lr.belief == 0.7
        assert lr.plausibility == 0.9
        assert lr.conflict_mass == 0.05
        assert lr.blocking_reason == "LOW_EVIDENCE"
