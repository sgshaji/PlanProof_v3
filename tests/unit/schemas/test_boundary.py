"""Tests for boundary verification schemas — three-tier verification pipeline."""

from __future__ import annotations

import pytest

from planproof.schemas.boundary import (
    BoundaryVerificationReport,
    BoundaryVerificationStatus,
    InspireResult,
    ScaleBarResult,
    VisualAlignmentResult,
)


class TestVisualAlignmentResult:
    """Tests for VisualAlignmentResult dataclass."""

    def test_valid_aligned_creation(self) -> None:
        result = VisualAlignmentResult(
            status="ALIGNED",
            issues=[],
            confidence=0.95,
        )
        assert result.status == "ALIGNED"
        assert result.issues == []
        assert result.confidence == 0.95

    def test_misaligned_with_issues(self) -> None:
        issues = [
            "Boundary does not match plot outline",
            "Fence position inconsistent with form",
        ]
        result = VisualAlignmentResult(
            status="MISALIGNED",
            issues=issues,
            confidence=0.72,
        )
        assert result.status == "MISALIGNED"
        assert result.issues == issues
        assert len(result.issues) == 2

    def test_unclear_status(self) -> None:
        result = VisualAlignmentResult(
            status="UNCLEAR",
            issues=["Image quality insufficient"],
            confidence=0.40,
        )
        assert result.status == "UNCLEAR"
        assert result.confidence == 0.40

    def test_frozen_immutability(self) -> None:
        result = VisualAlignmentResult(
            status="ALIGNED",
            issues=[],
            confidence=0.95,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.status = "MISALIGNED"


class TestScaleBarResult:
    """Tests for ScaleBarResult dataclass."""

    def test_valid_creation_with_discrepancy(self) -> None:
        result = ScaleBarResult(
            estimated_frontage_m=15.5,
            estimated_depth_m=25.0,
            estimated_area_m2=387.5,
            declared_area_m2=400.0,
            discrepancy_pct=3.2,
            discrepancy_flag=True,
            confidence=0.88,
        )
        assert result.estimated_area_m2 == 387.5
        assert result.declared_area_m2 == 400.0
        assert result.discrepancy_flag is True

    def test_no_discrepancy(self) -> None:
        result = ScaleBarResult(
            estimated_frontage_m=10.0,
            estimated_depth_m=20.0,
            estimated_area_m2=200.0,
            declared_area_m2=200.0,
            discrepancy_pct=0.0,
            discrepancy_flag=False,
            confidence=0.92,
        )
        assert result.discrepancy_flag is False
        assert result.discrepancy_pct == 0.0

    def test_partial_data_available(self) -> None:
        """Scale bar measurement may have some None fields."""
        result = ScaleBarResult(
            estimated_frontage_m=12.0,
            estimated_depth_m=None,
            estimated_area_m2=None,
            declared_area_m2=180.0,
            discrepancy_pct=None,
            discrepancy_flag=False,
            confidence=0.65,
        )
        assert result.estimated_frontage_m == 12.0
        assert result.estimated_depth_m is None
        assert result.estimated_area_m2 is None

    def test_frozen_immutability(self) -> None:
        result = ScaleBarResult(
            estimated_frontage_m=10.0,
            estimated_depth_m=20.0,
            estimated_area_m2=200.0,
            declared_area_m2=200.0,
            discrepancy_pct=0.0,
            discrepancy_flag=False,
            confidence=0.92,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.discrepancy_flag = True


class TestInspireResult:
    """Tests for InspireResult dataclass."""

    def test_valid_creation_not_over_claiming(self) -> None:
        result = InspireResult(
            inspire_id="GB123456789",
            polygon_area_m2=500.0,
            declared_area_m2=510.0,
            area_ratio=1.02,
            over_claiming_flag=False,
            confidence=0.91,
        )
        assert result.inspire_id == "GB123456789"
        assert result.polygon_area_m2 == 500.0
        assert result.over_claiming_flag is False

    def test_over_claiming_detected(self) -> None:
        result = InspireResult(
            inspire_id="GB987654321",
            polygon_area_m2=300.0,
            declared_area_m2=450.0,
            area_ratio=1.5,
            over_claiming_flag=True,
            confidence=0.85,
        )
        assert result.over_claiming_flag is True
        assert result.area_ratio == 1.5

    def test_missing_inspire_id(self) -> None:
        """Parcel may not have an INSPIRE ID."""
        result = InspireResult(
            inspire_id=None,
            polygon_area_m2=200.0,
            declared_area_m2=200.0,
            area_ratio=1.0,
            over_claiming_flag=False,
            confidence=0.75,
        )
        assert result.inspire_id is None

    def test_frozen_immutability(self) -> None:
        result = InspireResult(
            inspire_id="GB123456789",
            polygon_area_m2=500.0,
            declared_area_m2=510.0,
            area_ratio=1.02,
            over_claiming_flag=False,
            confidence=0.91,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.over_claiming_flag = True


class TestBoundaryVerificationReport:
    """Tests for BoundaryVerificationReport dataclass."""

    def test_consistent_report_all_tiers(self) -> None:
        """All three tiers available and consistent."""
        tier1 = VisualAlignmentResult(
            status="ALIGNED",
            issues=[],
            confidence=0.95,
        )
        tier2 = ScaleBarResult(
            estimated_frontage_m=10.0,
            estimated_depth_m=20.0,
            estimated_area_m2=200.0,
            declared_area_m2=200.0,
            discrepancy_pct=0.0,
            discrepancy_flag=False,
            confidence=0.92,
        )
        tier3 = InspireResult(
            inspire_id="GB123456789",
            polygon_area_m2=200.0,
            declared_area_m2=200.0,
            area_ratio=1.0,
            over_claiming_flag=False,
            confidence=0.91,
        )
        report = BoundaryVerificationReport(
            tier1=tier1,
            tier2=tier2,
            tier3=tier3,
            combined_status=BoundaryVerificationStatus.CONSISTENT,
            combined_confidence=0.93,
        )
        assert report.combined_status == BoundaryVerificationStatus.CONSISTENT
        assert report.tier1 is not None
        assert report.tier2 is not None
        assert report.tier3 is not None

    def test_discrepancy_detected(self) -> None:
        """Discrepancy found between tiers."""
        tier1 = VisualAlignmentResult(
            status="ALIGNED",
            issues=[],
            confidence=0.95,
        )
        tier2 = ScaleBarResult(
            estimated_frontage_m=10.0,
            estimated_depth_m=20.0,
            estimated_area_m2=190.0,
            declared_area_m2=250.0,
            discrepancy_pct=24.0,
            discrepancy_flag=True,
            confidence=0.88,
        )
        tier3 = None
        report = BoundaryVerificationReport(
            tier1=tier1,
            tier2=tier2,
            tier3=tier3,
            combined_status=BoundaryVerificationStatus.DISCREPANCY_DETECTED,
            combined_confidence=0.65,
        )
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED
        assert report.tier3 is None

    def test_insufficient_data(self) -> None:
        """Insufficient data to reach a verdict."""
        tier1 = VisualAlignmentResult(
            status="UNCLEAR",
            issues=["Image quality insufficient"],
            confidence=0.40,
        )
        report = BoundaryVerificationReport(
            tier1=tier1,
            tier2=None,
            tier3=None,
            combined_status=BoundaryVerificationStatus.INSUFFICIENT_DATA,
            combined_confidence=0.40,
        )
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA
        assert report.tier2 is None
        assert report.tier3 is None

    def test_frozen_immutability(self) -> None:
        report = BoundaryVerificationReport(
            tier1=None,
            tier2=None,
            tier3=None,
            combined_status=BoundaryVerificationStatus.INSUFFICIENT_DATA,
            combined_confidence=0.0,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            report.combined_status = BoundaryVerificationStatus.CONSISTENT
