"""Tests for combine_tier_results and BoundaryVerificationStep."""
from __future__ import annotations

import pytest

from planproof.pipeline.steps.boundary_verification import (
    BoundaryVerificationStep,
    combine_tier_results,
)
from planproof.schemas.boundary import (
    BoundaryVerificationStatus,
    InspireResult,
    ScaleBarResult,
    VisualAlignmentResult,
)


def _t1(status: str, confidence: float = 0.9) -> VisualAlignmentResult:
    return VisualAlignmentResult(status=status, issues=[], confidence=confidence)  # type: ignore[arg-type]


def _t2(
    *,
    estimated_area_m2: float | None = 500.0,
    discrepancy_flag: bool = False,
    confidence: float = 0.85,
) -> ScaleBarResult:
    return ScaleBarResult(
        estimated_frontage_m=20.0,
        estimated_depth_m=25.0,
        estimated_area_m2=estimated_area_m2,
        declared_area_m2=500.0,
        discrepancy_pct=0.0,
        discrepancy_flag=discrepancy_flag,
        confidence=confidence,
    )


def _t3(
    *,
    inspire_id: str | None = "INSPIRE-001",
    over_claiming_flag: bool = False,
    confidence: float = 0.80,
) -> InspireResult:
    return InspireResult(
        inspire_id=inspire_id,
        polygon_area_m2=500.0,
        declared_area_m2=500.0,
        area_ratio=1.0,
        over_claiming_flag=over_claiming_flag,
        confidence=confidence,
    )


class TestCombineTierResults:
    def test_all_pass(self) -> None:
        """All tiers pass → CONSISTENT."""
        report = combine_tier_results(
            tier1=_t1("ALIGNED"),
            tier2=_t2(),
            tier3=_t3(),
        )
        assert report.combined_status == BoundaryVerificationStatus.CONSISTENT
        assert report.tier1 is not None
        assert report.tier2 is not None
        assert report.tier3 is not None

    def test_tier1_misaligned(self) -> None:
        """Tier 1 MISALIGNED → DISCREPANCY_DETECTED."""
        report = combine_tier_results(
            tier1=_t1("MISALIGNED"),
            tier2=_t2(),
            tier3=_t3(),
        )
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED

    def test_tier2_discrepancy(self) -> None:
        """Tier 2 discrepancy_flag=True → DISCREPANCY_DETECTED."""
        report = combine_tier_results(
            tier1=_t1("ALIGNED"),
            tier2=_t2(discrepancy_flag=True),
            tier3=_t3(),
        )
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED

    def test_tier3_over_claiming(self) -> None:
        """Tier 3 over_claiming_flag=True → DISCREPANCY_DETECTED."""
        report = combine_tier_results(
            tier1=_t1("ALIGNED"),
            tier2=_t2(),
            tier3=_t3(over_claiming_flag=True),
        )
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED

    def test_no_tiers(self) -> None:
        """All tiers None → INSUFFICIENT_DATA with zero confidence."""
        report = combine_tier_results(None, None, None)
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA
        assert report.combined_confidence == 0.0

    def test_tier1_unclear_only(self) -> None:
        """Tier 1 UNCLEAR (only tier) → INSUFFICIENT_DATA."""
        report = combine_tier_results(tier1=_t1("UNCLEAR"))
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA

    def test_combined_confidence_is_mean(self) -> None:
        """Combined confidence is the arithmetic mean of usable tier confidences."""
        report = combine_tier_results(
            tier1=_t1("ALIGNED", confidence=0.9),
            tier3=_t3(confidence=0.8),
        )
        assert report.combined_status == BoundaryVerificationStatus.CONSISTENT
        assert report.combined_confidence == pytest.approx(0.85, abs=0.001)

    def test_tier2_no_area_excluded(self) -> None:
        """Tier 2 with estimated_area_m2=None is not counted as usable."""
        report = combine_tier_results(
            tier2=_t2(estimated_area_m2=None),
        )
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA

    def test_tier3_no_inspire_id_excluded(self) -> None:
        """Tier 3 with inspire_id=None is not counted as usable."""
        report = combine_tier_results(
            tier3=_t3(inspire_id=None),
        )
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA


class TestBoundaryVerificationStep:
    def test_execute_stores_report_in_context(self) -> None:
        """Step stores BoundaryVerificationReport in context under 'boundary_verification'."""
        step = BoundaryVerificationStep()
        ctx: dict = {}
        result = step.execute(ctx)
        assert "boundary_verification" in ctx
        assert result["success"] is True

    def test_name(self) -> None:
        assert BoundaryVerificationStep().name == "boundary_verification"

    def test_execute_returns_insufficient_data_with_no_verifiers(self) -> None:
        """Without verifiers, step produces INSUFFICIENT_DATA report."""
        step = BoundaryVerificationStep()
        ctx: dict = {}
        step.execute(ctx)
        report = ctx["boundary_verification"]
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA
