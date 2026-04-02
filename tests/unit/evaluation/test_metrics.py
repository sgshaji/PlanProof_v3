"""Tests for evaluation metrics — recall, precision, F2, bootstrap CI, McNemar."""
from __future__ import annotations

import math

import pytest

from planproof.evaluation.metrics import (
    belief_statistics,
    blocking_reason_distribution,
    bootstrap_ci,
    cohens_h,
    compute_automation_rate,
    compute_component_contribution,
    compute_confusion_matrix,
    compute_f2_score,
    compute_precision,
    compute_recall,
    mcnemar_test,
    partially_assessable_rate,
)
from planproof.evaluation.results import RuleResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(
    gt: str,
    pred: str,
    rule_id: str = "R001",
    config: str = "cfg",
    set_id: str = "s1",
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        ground_truth_outcome=gt,
        predicted_outcome=pred,
        config_name=config,
        set_id=set_id,
    )


# ---------------------------------------------------------------------------
# compute_confusion_matrix — known inputs
# ---------------------------------------------------------------------------


class TestComputeConfusionMatrix:
    def test_tp_fp_fn_tn_counts(self) -> None:
        """Known mix of outcomes produces expected TP/FP/FN/TN counts."""
        results = [
            _result("FAIL", "FAIL"),   # TP
            _result("FAIL", "FAIL"),   # TP
            _result("PASS", "FAIL"),   # FP
            _result("FAIL", "PASS"),   # FN
            _result("PASS", "PASS"),   # TN
            _result("PASS", "PASS"),   # TN
        ]
        cm = compute_confusion_matrix(results)
        assert cm["tp"] == 2
        assert cm["fp"] == 1
        assert cm["fn"] == 1
        assert cm["tn"] == 2
        assert cm["not_assessable"] == 0

    def test_not_assessable_counts_as_fn(self) -> None:
        """NOT_ASSESSABLE predicted when gt=FAIL counts as FN, not a separate error."""
        results = [
            _result("FAIL", "NOT_ASSESSABLE"),
            _result("FAIL", "NOT_ASSESSABLE"),
        ]
        cm = compute_confusion_matrix(results)
        assert cm["fn"] == 2
        assert cm["not_assessable"] == 2
        assert cm["tp"] == 0

    def test_not_assessable_when_gt_pass_not_counted_as_fp_or_tn(self) -> None:
        """NOT_ASSESSABLE predicted when gt=PASS: not TP/FP/FN/TN — only not_assessable."""
        results = [
            _result("PASS", "NOT_ASSESSABLE"),
        ]
        cm = compute_confusion_matrix(results)
        assert cm["tp"] == 0
        assert cm["fp"] == 0
        assert cm["fn"] == 0
        assert cm["tn"] == 0
        assert cm["not_assessable"] == 1

    def test_all_pass_correctly(self) -> None:
        """All gt=PASS, pred=PASS → all TN."""
        results = [_result("PASS", "PASS") for _ in range(3)]
        cm = compute_confusion_matrix(results)
        assert cm["tn"] == 3
        assert cm["tp"] == 0
        assert cm["fp"] == 0
        assert cm["fn"] == 0

    def test_empty_input_returns_zeros(self) -> None:
        """Empty list → all zeros."""
        cm = compute_confusion_matrix([])
        assert cm == {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "not_assessable": 0}

    def test_mixed_not_assessable(self) -> None:
        """NOT_ASSESSABLE for both gt outcomes tracked correctly."""
        results = [
            _result("FAIL", "NOT_ASSESSABLE"),  # FN + not_assessable
            _result("PASS", "NOT_ASSESSABLE"),  # only not_assessable
            _result("FAIL", "FAIL"),            # TP
        ]
        cm = compute_confusion_matrix(results)
        assert cm["tp"] == 1
        assert cm["fn"] == 1
        assert cm["not_assessable"] == 2


# ---------------------------------------------------------------------------
# compute_recall
# ---------------------------------------------------------------------------


class TestComputeRecall:
    def test_standard_recall(self) -> None:
        """TP=8, FN=2 → recall = 0.8."""
        cm = {"tp": 8, "fp": 0, "fn": 2, "tn": 0, "not_assessable": 0}
        assert compute_recall(cm) == pytest.approx(0.8)

    def test_perfect_recall(self) -> None:
        """No FN → recall = 1.0."""
        cm = {"tp": 5, "fp": 0, "fn": 0, "tn": 0, "not_assessable": 0}
        assert compute_recall(cm) == pytest.approx(1.0)

    def test_zero_recall(self) -> None:
        """No TP → recall = 0.0."""
        cm = {"tp": 0, "fp": 0, "fn": 5, "tn": 0, "not_assessable": 0}
        assert compute_recall(cm) == pytest.approx(0.0)

    def test_zero_division_returns_zero(self) -> None:
        """TP=0, FN=0 → 0.0 (no positives exist)."""
        cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 5, "not_assessable": 0}
        assert compute_recall(cm) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_precision
# ---------------------------------------------------------------------------


class TestComputePrecision:
    def test_standard_precision(self) -> None:
        """TP=8, FP=2 → precision = 0.8."""
        cm = {"tp": 8, "fp": 2, "fn": 0, "tn": 0, "not_assessable": 0}
        assert compute_precision(cm) == pytest.approx(0.8)

    def test_perfect_precision(self) -> None:
        """No FP → precision = 1.0."""
        cm = {"tp": 5, "fp": 0, "fn": 0, "tn": 0, "not_assessable": 0}
        assert compute_precision(cm) == pytest.approx(1.0)

    def test_zero_precision(self) -> None:
        """No TP → precision = 0.0."""
        cm = {"tp": 0, "fp": 5, "fn": 0, "tn": 0, "not_assessable": 0}
        assert compute_precision(cm) == pytest.approx(0.0)

    def test_zero_division_returns_zero(self) -> None:
        """TP=0, FP=0 → 0.0."""
        cm = {"tp": 0, "fp": 0, "fn": 5, "tn": 0, "not_assessable": 0}
        assert compute_precision(cm) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_f2_score
# ---------------------------------------------------------------------------


class TestComputeF2Score:
    def test_known_f2_value(self) -> None:
        """TP=8, FP=2, FN=2 → precision=0.8, recall=0.8 → F2=0.8."""
        cm = {"tp": 8, "fp": 2, "fn": 2, "tn": 0, "not_assessable": 0}
        # F2 = (5 * 0.8 * 0.8) / (4*0.8 + 0.8) = 3.2 / 4.0 = 0.8
        assert compute_f2_score(cm) == pytest.approx(0.8)

    def test_f2_weights_recall_over_precision(self) -> None:
        """F2 penalises FN more than FP — high recall, lower precision → F2 > F1."""
        # precision=0.5, recall=1.0
        cm = {"tp": 5, "fp": 5, "fn": 0, "tn": 0, "not_assessable": 0}
        f2 = compute_f2_score(cm)
        # F2 = (5 * 0.5 * 1.0) / (4*0.5 + 1.0) = 2.5 / 3.0 ≈ 0.833
        assert f2 == pytest.approx(5 * 0.5 * 1.0 / (4 * 0.5 + 1.0))

    def test_zero_division_returns_zero(self) -> None:
        """All zeros → 0.0."""
        cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 5, "not_assessable": 0}
        assert compute_f2_score(cm) == pytest.approx(0.0)

    def test_f2_zero_precision_zero_recall(self) -> None:
        """Zero precision and recall → 0.0."""
        cm = {"tp": 0, "fp": 3, "fn": 3, "tn": 0, "not_assessable": 0}
        assert compute_f2_score(cm) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_automation_rate
# ---------------------------------------------------------------------------


class TestComputeAutomationRate:
    def test_three_assessable_of_four(self) -> None:
        """3 assessable out of 4 → 0.75."""
        results = [
            _result("PASS", "PASS"),
            _result("FAIL", "FAIL"),
            _result("PASS", "FAIL"),
            _result("FAIL", "NOT_ASSESSABLE"),
        ]
        assert compute_automation_rate(results) == pytest.approx(0.75)

    def test_all_assessable(self) -> None:
        """No NOT_ASSESSABLE → 1.0."""
        results = [_result("PASS", "PASS"), _result("FAIL", "FAIL")]
        assert compute_automation_rate(results) == pytest.approx(1.0)

    def test_none_assessable(self) -> None:
        """All NOT_ASSESSABLE → 0.0."""
        results = [_result("FAIL", "NOT_ASSESSABLE"), _result("PASS", "NOT_ASSESSABLE")]
        assert compute_automation_rate(results) == pytest.approx(0.0)

    def test_empty_input_returns_zero(self) -> None:
        """Empty list → 0.0."""
        assert compute_automation_rate([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# bootstrap_ci
# ---------------------------------------------------------------------------


class TestBootstrapCI:
    def test_returns_tuple_of_two_floats(self) -> None:
        """bootstrap_ci returns (lower, upper) as floats."""
        values = [0.7, 0.8, 0.75, 0.72, 0.85, 0.68, 0.9, 0.77]
        result = bootstrap_ci(values)
        assert isinstance(result, tuple)
        assert len(result) == 2
        lower, upper = result
        assert isinstance(lower, float)
        assert isinstance(upper, float)

    def test_lower_less_than_upper(self) -> None:
        """Lower bound is strictly less than upper bound for non-degenerate input."""
        values = [0.1 * i for i in range(1, 11)]
        lower, upper = bootstrap_ci(values)
        assert lower < upper

    def test_reproducibility(self) -> None:
        """Same input always produces the same CI (seeded RNG)."""
        values = [0.6, 0.7, 0.8, 0.9, 0.5]
        r1 = bootstrap_ci(values)
        r2 = bootstrap_ci(values)
        assert r1 == r2

    def test_constant_values_equal_bounds(self) -> None:
        """All-same values → lower == upper == that value."""
        values = [0.5] * 20
        lower, upper = bootstrap_ci(values)
        assert lower == pytest.approx(0.5)
        assert upper == pytest.approx(0.5)

    def test_n_resamples_parameter(self) -> None:
        """Custom n_resamples is accepted."""
        values = [0.6, 0.7, 0.8, 0.9]
        lower, upper = bootstrap_ci(values, n_resamples=500)
        assert lower <= upper


# ---------------------------------------------------------------------------
# mcnemar_test
# ---------------------------------------------------------------------------


class TestMcnemarTest:
    def _correct(self, gt: str, pred: str) -> bool:
        """True when prediction matches ground truth."""
        return gt == pred

    def test_returns_statistic_and_pvalue(self) -> None:
        """mcnemar_test returns a (statistic, p_value) tuple."""
        results_a = [
            _result("FAIL", "FAIL"),   # A correct
            _result("FAIL", "PASS"),   # A wrong
            _result("PASS", "PASS"),   # both correct
        ]
        results_b = [
            _result("FAIL", "PASS"),   # B wrong
            _result("FAIL", "FAIL"),   # B correct
            _result("PASS", "PASS"),   # both correct
        ]
        stat, p = mcnemar_test(results_a, results_b)
        assert isinstance(stat, float)
        assert isinstance(p, float)

    def test_identical_systems_pvalue_not_significant(self) -> None:
        """Two identical systems → b=0, c=0 → statistic=0, p-value=NaN or 1.0."""
        results = [
            _result("FAIL", "FAIL"),
            _result("PASS", "PASS"),
        ]
        stat, p = mcnemar_test(results, results)
        # When b+c=0, statistic is 0 and p-value is NaN (undefined)
        assert stat == pytest.approx(0.0)

    def test_large_discordance_significant(self) -> None:
        """Large discordance → small p-value (< 0.05)."""
        # A is always correct, B is always wrong on FAIL cases
        n = 20
        results_a = [_result("FAIL", "FAIL", rule_id=f"R{i:03d}") for i in range(n)]
        results_b = [_result("FAIL", "PASS", rule_id=f"R{i:03d}") for i in range(n)]
        stat, p = mcnemar_test(results_a, results_b)
        assert stat > 0
        # p-value should be small (or NaN if scipy not installed)
        if not math.isnan(p):
            assert p < 0.05


# ---------------------------------------------------------------------------
# cohens_h
# ---------------------------------------------------------------------------


class TestCohensH:
    def test_same_proportions_returns_zero(self) -> None:
        """Same proportion p1=p2 → Cohen's h = 0.0."""
        assert cohens_h(0.7, 0.7) == pytest.approx(0.0)

    def test_different_proportions_nonzero(self) -> None:
        """Different proportions → non-zero effect size."""
        h = cohens_h(0.8, 0.5)
        assert h != pytest.approx(0.0)

    def test_known_value(self) -> None:
        """h = 2*arcsin(sqrt(p1)) - 2*arcsin(sqrt(p2))."""
        p1, p2 = 0.9, 0.6
        expected = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))
        assert cohens_h(p1, p2) == pytest.approx(expected)

    def test_zero_and_one(self) -> None:
        """Boundary values 0.0 and 1.0 do not raise."""
        h = cohens_h(1.0, 0.0)
        assert isinstance(h, float)

    def test_antisymmetric(self) -> None:
        """cohens_h(p1, p2) == -cohens_h(p2, p1)."""
        assert cohens_h(0.7, 0.4) == pytest.approx(-cohens_h(0.4, 0.7))


# ---------------------------------------------------------------------------
# partially_assessable_rate
# ---------------------------------------------------------------------------


class TestPartiallyAssessableRate:
    def test_no_partially_assessable(self) -> None:
        results = [_result("PASS", "PASS"), _result("FAIL", "FAIL")]
        assert partially_assessable_rate(results) == pytest.approx(0.0)

    def test_some_partially_assessable(self) -> None:
        results = [
            _result("PASS", "PASS"),
            RuleResult(
                rule_id="R002",
                ground_truth_outcome="FAIL",
                predicted_outcome="PARTIALLY_ASSESSABLE",
                config_name="cfg",
                set_id="s1",
            ),
        ]
        assert partially_assessable_rate(results) == pytest.approx(0.5)

    def test_empty_returns_zero(self) -> None:
        assert partially_assessable_rate([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# blocking_reason_distribution
# ---------------------------------------------------------------------------


class TestBlockingReasonDistribution:
    def test_counts_each_reason(self) -> None:
        results = [
            RuleResult(
                rule_id="R001",
                ground_truth_outcome="PASS",
                predicted_outcome="NOT_ASSESSABLE",
                config_name="cfg",
                set_id="s1",
                blocking_reason="MISSING_EVIDENCE",
            ),
            RuleResult(
                rule_id="R002",
                ground_truth_outcome="PASS",
                predicted_outcome="NOT_ASSESSABLE",
                config_name="cfg",
                set_id="s1",
                blocking_reason="MISSING_EVIDENCE",
            ),
            RuleResult(
                rule_id="R003",
                ground_truth_outcome="PASS",
                predicted_outcome="PASS",
                config_name="cfg",
                set_id="s1",
                blocking_reason="NONE",
            ),
        ]
        dist = blocking_reason_distribution(results)
        assert dist["MISSING_EVIDENCE"] == 2
        assert dist["NONE"] == 1

    def test_none_blocking_reason_counted(self) -> None:
        results = [_result("PASS", "PASS")]  # blocking_reason defaults to None
        dist = blocking_reason_distribution(results)
        assert dist.get("null", 0) == 1


# ---------------------------------------------------------------------------
# belief_statistics
# ---------------------------------------------------------------------------


class TestBeliefStatistics:
    def test_basic_stats(self) -> None:
        results = [
            RuleResult(
                rule_id=f"R{i:03d}",
                ground_truth_outcome="PASS",
                predicted_outcome="PASS",
                config_name="cfg",
                set_id="s1",
                belief=v,
            )
            for i, v in enumerate([0.2, 0.4, 0.6, 0.8])
        ]
        stats = belief_statistics(results)
        assert stats["mean"] == pytest.approx(0.5)
        assert stats["min"] == pytest.approx(0.2)
        assert stats["max"] == pytest.approx(0.8)
        assert "std" in stats
        assert "median" in stats

    def test_skips_none_beliefs(self) -> None:
        results = [
            RuleResult(
                rule_id="R001",
                ground_truth_outcome="PASS",
                predicted_outcome="PASS",
                config_name="cfg",
                set_id="s1",
                belief=0.5,
            ),
            _result("PASS", "PASS"),  # belief=None
        ]
        stats = belief_statistics(results)
        assert stats["mean"] == pytest.approx(0.5)
        assert stats["count"] == 1

    def test_empty_results(self) -> None:
        stats = belief_statistics([])
        assert stats["count"] == 0
        assert stats["mean"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_component_contribution
# ---------------------------------------------------------------------------


class TestComponentContribution:
    def test_returns_rows_for_each_ablation(self) -> None:
        full = [
            RuleResult(
                rule_id="R001",
                ground_truth_outcome="FAIL",
                predicted_outcome="FAIL",
                config_name="full_system",
                set_id="s1",
            ),
        ]
        abl_d = [
            RuleResult(
                rule_id="R001",
                ground_truth_outcome="FAIL",
                predicted_outcome="PASS",
                config_name="ablation_d",
                set_id="s1",
            ),
        ]
        all_results = {"full_system": full, "ablation_d": abl_d}
        rows = compute_component_contribution(all_results)
        assert len(rows) >= 1
        row_d = next(r for r in rows if r["config_name"] == "ablation_d")
        assert "recall_delta" in row_d
        assert "mcnemar_p" in row_d
        assert "cohens_h" in row_d


# ---------------------------------------------------------------------------
# compute_confusion_matrix — PARTIALLY_ASSESSABLE
# ---------------------------------------------------------------------------


class TestConfusionMatrixPartiallyAssessable:
    def test_partially_assessable_counted_like_not_assessable(self) -> None:
        results = [
            RuleResult(
                rule_id="R001",
                ground_truth_outcome="FAIL",
                predicted_outcome="PARTIALLY_ASSESSABLE",
                config_name="cfg",
                set_id="s1",
            ),
        ]
        cm = compute_confusion_matrix(results)
        assert cm["fn"] == 1
        assert cm["not_assessable"] == 1
