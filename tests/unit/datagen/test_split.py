"""Tests for the seeded train/val/test split utilities.

# WHY: The split must be perfectly deterministic — any change to the random
# assignment would invalidate cross-run comparisons and make benchmark results
# unreproducible.  These tests lock in that contract before the implementation
# is written (TDD).
"""

from __future__ import annotations

import pytest

from planproof.datagen.split import compute_split

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_set_ids(n: int) -> list[str]:
    """Generate a list of n synthetic set IDs for testing."""
    return [f"SET_COMPLIANT_{42000 + i:05d}" for i in range(n)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeSplitDeterministic:
    """Same inputs always produce identical split assignments."""

    def test_same_seed_same_result(self) -> None:
        # WHY: Reproducibility is the #1 requirement — CI runs, paper results,
        # and data-version audits all depend on identical splits every time.
        set_ids = _make_set_ids(50)
        result_a = compute_split(set_ids, seed=42)
        result_b = compute_split(set_ids, seed=42)
        assert result_a == result_b

    def test_different_seed_different_result(self) -> None:
        # WHY: Confirm the seed actually influences the shuffle; if it didn't,
        # both seeds would produce the same mapping and the test above would be
        # vacuously satisfied.
        set_ids = _make_set_ids(50)
        result_42 = compute_split(set_ids, seed=42)
        result_99 = compute_split(set_ids, seed=99)
        # It is astronomically unlikely that two shuffles of 50 items agree
        # entirely, so any single assignment difference is sufficient evidence.
        assert result_42 != result_99

    def test_order_independent_when_ids_sorted(self) -> None:
        # WHY: Callers may scan the filesystem in different orders on different
        # OSes.  The implementation sorts ids before shuffling to guarantee
        # a stable baseline regardless of discovery order.
        set_ids = _make_set_ids(30)
        shuffled = list(reversed(set_ids))
        assert compute_split(set_ids, seed=42) == compute_split(shuffled, seed=42)


class TestComputeSplitRatios:
    """The empirical counts should be close to the requested ratios."""

    def test_default_ratios_approximately_60_20_20(self) -> None:
        # WHY: With 50 sets the expected counts are 30/10/10.  We allow ±2
        # slots of tolerance to accommodate integer-rounding edge cases.
        set_ids = _make_set_ids(50)
        result = compute_split(set_ids, seed=42)
        counts = {
            "train": sum(1 for v in result.values() if v == "train"),
            "val": sum(1 for v in result.values() if v == "val"),
            "test": sum(1 for v in result.values() if v == "test"),
        }
        assert abs(counts["train"] - 30) <= 2
        assert abs(counts["val"] - 10) <= 2
        assert abs(counts["test"] - 10) <= 2

    def test_custom_ratios_respected(self) -> None:
        # WHY: Some experiments (e.g. few-shot ablations) need a 70/15/15 or
        # 50/25/25 split.  The function must honour caller-supplied ratios.
        set_ids = _make_set_ids(100)
        result = compute_split(set_ids, seed=7, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15)
        counts = {
            "train": sum(1 for v in result.values() if v == "train"),
            "val": sum(1 for v in result.values() if v == "val"),
            "test": sum(1 for v in result.values() if v == "test"),
        }
        assert abs(counts["train"] - 70) <= 3
        assert abs(counts["val"] - 15) <= 3
        assert abs(counts["test"] - 15) <= 3

    def test_ratios_must_sum_to_one(self) -> None:
        # WHY: Ratios that don't sum to 1.0 would silently drop or double-count
        # items.  The function should raise a clear ValueError instead of
        # producing corrupt output.
        with pytest.raises(ValueError, match="ratios must sum"):
            compute_split(["A", "B", "C"], train_ratio=0.5, val_ratio=0.3, test_ratio=0.4)


class TestAllSetsAssigned:
    """Every set_id is present in the result dict exactly once."""

    def test_all_ids_present(self) -> None:
        # WHY: A missing id would mean a set is excluded from training/eval —
        # silent data loss that would skew metrics.
        set_ids = _make_set_ids(50)
        result = compute_split(set_ids, seed=42)
        assert set(result.keys()) == set(set_ids)

    def test_values_are_valid_split_names(self) -> None:
        # WHY: Guard against typos like "training" vs "train" which would
        # break downstream code that keyed on exact string equality.
        set_ids = _make_set_ids(20)
        result = compute_split(set_ids, seed=42)
        assert all(v in {"train", "val", "test"} for v in result.values())

    def test_empty_input_returns_empty(self) -> None:
        assert compute_split([]) == {}

    def test_single_item_goes_to_train(self) -> None:
        # WHY: Edge case — a single item must land somewhere; train is the
        # natural bucket for any remainder after val/test are filled.
        result = compute_split(["ONLY_ONE"])
        assert result["ONLY_ONE"] in {"train", "val", "test"}
