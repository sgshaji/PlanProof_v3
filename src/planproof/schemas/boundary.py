"""Schemas for the three-tier boundary verification pipeline.

This module defines frozen dataclasses for the boundary verification system,
which performs a three-tier check:
  1. Visual alignment: Does the drawing boundary match the photographic evidence?
  2. Scale bar analysis: Do area measurements inferred from scale bars match declarations?
  3. INSPIRE data: Does the polygon area in INSPIRE data match the declared area?

These schemas capture the results from each tier and combine them into a
unified verification report.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class BoundaryVerificationStatus(StrEnum):
    """Overall status of boundary verification across all three tiers."""

    CONSISTENT = "CONSISTENT"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class VisualAlignmentResult:
    """Result from Tier 1: Visual alignment check.

    Compares the drawing boundary against photographic evidence to detect
    misalignment, ambiguity, or clear consistency.

    Attributes
    ----------
    status : Literal["ALIGNED", "MISALIGNED", "UNCLEAR"]
        Whether the boundary is aligned with evidence, misaligned, or unclear.
    issues : list[str]
        List of specific alignment issues detected (empty if status is ALIGNED).
    confidence : float
        Confidence score for this assessment (0–1).
    """

    status: Literal["ALIGNED", "MISALIGNED", "UNCLEAR"]
    issues: list[str]
    confidence: float


@dataclass(frozen=True)
class ScaleBarResult:
    """Result from Tier 2: Scale bar analysis.

    Uses scale bars in drawings to estimate frontage, depth, and area,
    then compares with declared area to detect discrepancies.

    Attributes
    ----------
    estimated_frontage_m : float | None
        Frontage estimated from scale bar (metres), or None if not measurable.
    estimated_depth_m : float | None
        Depth estimated from scale bar (metres), or None if not measurable.
    estimated_area_m2 : float | None
        Area calculated from frontage × depth, or None if incomplete.
    declared_area_m2 : float | None
        Area declared in the planning application, or None if not found.
    discrepancy_pct : float | None
        Percentage difference between estimated and declared area.
        Positive = over-claiming, negative = under-claiming.
        None if comparison not possible.
    discrepancy_flag : bool
        True if a significant discrepancy was detected.
    confidence : float
        Confidence score for this measurement (0–1).
    """

    estimated_frontage_m: float | None
    estimated_depth_m: float | None
    estimated_area_m2: float | None
    declared_area_m2: float | None
    discrepancy_pct: float | None
    discrepancy_flag: bool
    confidence: float


@dataclass(frozen=True)
class InspireResult:
    """Result from Tier 3: INSPIRE reference data check.

    Looks up the parcel in INSPIRE data, compares the polygon area
    with the declared area to detect over-claiming.

    Attributes
    ----------
    inspire_id : str | None
        INSPIRE ID of the parcel, or None if not found.
    polygon_area_m2 : float | None
        Area of the polygon in INSPIRE data (m²), or None if not available.
    declared_area_m2 : float | None
        Area declared in the planning application, or None if not found.
    area_ratio : float | None
        Ratio of declared to polygon area (declared / polygon).
        > 1 = over-claiming, < 1 = under-claiming.
        None if comparison not possible.
    over_claiming_flag : bool
        True if declared area significantly exceeds polygon area.
    confidence : float
        Confidence score for this comparison (0–1).
    """

    inspire_id: str | None
    polygon_area_m2: float | None
    declared_area_m2: float | None
    area_ratio: float | None
    over_claiming_flag: bool
    confidence: float


@dataclass(frozen=True)
class BoundaryVerificationReport:
    """Unified boundary verification report combining all three tiers.

    Attributes
    ----------
    tier1 : VisualAlignmentResult | None
        Visual alignment result, or None if not performed.
    tier2 : ScaleBarResult | None
        Scale bar analysis result, or None if not performed.
    tier3 : InspireResult | None
        INSPIRE data check result, or None if not performed.
    combined_status : BoundaryVerificationStatus
        Overall verification status across all available tiers.
    combined_confidence : float
        Overall confidence score for the boundary verification (0–1).
    """

    tier1: VisualAlignmentResult | None
    tier2: ScaleBarResult | None
    tier3: InspireResult | None
    combined_status: BoundaryVerificationStatus
    combined_confidence: float
