"""Pipeline step: three-tier boundary verification."""
from __future__ import annotations

from planproof.infrastructure.logging import get_logger
from planproof.schemas.boundary import (
    BoundaryVerificationReport,
    BoundaryVerificationStatus,
    InspireResult,
    ScaleBarResult,
    VisualAlignmentResult,
)

logger = get_logger(__name__)


def combine_tier_results(
    tier1: VisualAlignmentResult | None = None,
    tier2: ScaleBarResult | None = None,
    tier3: InspireResult | None = None,
) -> BoundaryVerificationReport:
    """Combine tier results into a single report.

    - ANY tier detects discrepancy → DISCREPANCY_DETECTED
    - All available tiers pass → CONSISTENT
    - No tier produced usable result → INSUFFICIENT_DATA
    """
    has_discrepancy = False
    has_usable_result = False
    confidences: list[float] = []

    if tier1 is not None and tier1.status != "UNCLEAR":
        has_usable_result = True
        confidences.append(tier1.confidence)
        if tier1.status == "MISALIGNED":
            has_discrepancy = True

    if tier2 is not None and tier2.estimated_area_m2 is not None:
        has_usable_result = True
        confidences.append(tier2.confidence)
        if tier2.discrepancy_flag:
            has_discrepancy = True

    if tier3 is not None and tier3.inspire_id is not None:
        has_usable_result = True
        confidences.append(tier3.confidence)
        if tier3.over_claiming_flag:
            has_discrepancy = True

    if not has_usable_result:
        status = BoundaryVerificationStatus.INSUFFICIENT_DATA
        combined_conf = 0.0
    elif has_discrepancy:
        status = BoundaryVerificationStatus.DISCREPANCY_DETECTED
        combined_conf = sum(confidences) / len(confidences) if confidences else 0.0
    else:
        status = BoundaryVerificationStatus.CONSISTENT
        combined_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return BoundaryVerificationReport(
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        combined_status=status,
        combined_confidence=round(combined_conf, 3),
    )


class BoundaryVerificationStep:
    """Run three-tier boundary verification and store result in context."""

    def __init__(
        self,
        visual_verifier: object | None = None,
        scalebar_verifier: object | None = None,
        inspire_verifier: object | None = None,
    ) -> None:
        self._visual = visual_verifier
        self._scalebar = scalebar_verifier
        self._inspire = inspire_verifier

    @property
    def name(self) -> str:
        return "boundary_verification"

    def execute(self, context: dict) -> dict:
        # Placeholder: extract inputs from context and call verifiers
        # For now, store empty report
        report = combine_tier_results(None, None, None)
        context["boundary_verification"] = report

        logger.info(
            "boundary_verification_complete",
            status=report.combined_status.value,
            confidence=report.combined_confidence,
        )

        return {
            "success": True,
            "message": f"Boundary verification: {report.combined_status.value}",
            "artifacts": {},
        }
