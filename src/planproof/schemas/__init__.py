"""PlanProof schema definitions — Pydantic v2 data models.

These models serve as the integration contracts (M4 milestones) between
pipeline layers. Every function that crosses a layer boundary accepts and
returns these types, ensuring type safety and serialisation consistency.

Re-exports the most commonly used types for convenience::

    from planproof.schemas import ExtractedEntity, RuleVerdict, ComplianceReport
"""

from __future__ import annotations

from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
    ConflictDetail,
    EvidenceRequirement,
)
from planproof.schemas.config import (
    AblationConfig,
    ConfidenceThresholds,
    PipelineConfig,
)
from planproof.schemas.entities import (
    BoundingBox,
    ClassifiedDocument,
    DocumentType,
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
    RawTextResult,
)
from planproof.schemas.pipeline import (
    ComplianceReport,
    EvidenceRequest,
    MissingEvidence,
    ReportSummary,
    StepResult,
    StepStatus,
)
from planproof.schemas.reconciliation import (
    ReconciledEvidence,
    ReconciliationStatus,
)
from planproof.schemas.rules import (
    RuleConfig,
    RuleOutcome,
    RuleVerdict,
)

__all__ = [
    # entities
    "EntityType",
    "ExtractionMethod",
    "DocumentType",
    "BoundingBox",
    "RawTextResult",
    "ClassifiedDocument",
    "ExtractedEntity",
    # reconciliation
    "ReconciliationStatus",
    "ReconciledEvidence",
    # assessability
    "BlockingReason",
    "EvidenceRequirement",
    "ConflictDetail",
    "AssessabilityResult",
    # rules
    "RuleOutcome",
    "RuleVerdict",
    "RuleConfig",
    # pipeline
    "StepStatus",
    "StepResult",
    "ComplianceReport",
    "ReportSummary",
    "EvidenceRequest",
    "MissingEvidence",
    # config
    "ConfidenceThresholds",
    "AblationConfig",
    "PipelineConfig",
]
