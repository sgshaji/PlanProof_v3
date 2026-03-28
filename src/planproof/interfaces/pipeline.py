"""Protocols for the orchestration pipeline.

Defines the step abstraction and the shared context object that carries
state between steps.
"""
from __future__ import annotations

from typing import Any, Protocol, TypedDict

from planproof.schemas.assessability import AssessabilityResult
from planproof.schemas.entities import ClassifiedDocument, ExtractedEntity
from planproof.schemas.rules import RuleVerdict


class PipelineContext(TypedDict, total=False):
    """Mutable state bag threaded through every pipeline step.

    # DESIGN: Using TypedDict (total=False) rather than a dataclass because
    # early steps only populate a subset of keys.  Each step adds to the
    # context; later steps read what earlier steps wrote.
    """

    classified_documents: list[ClassifiedDocument]
    entities: list[ExtractedEntity]
    graph_ref: Any  # opaque handle to the populated knowledge graph
    verdicts: list[RuleVerdict]
    assessability_results: list[AssessabilityResult]
    metadata: dict[str, Any]


class StepResult(TypedDict, total=False):
    """Value returned by each pipeline step."""

    success: bool
    message: str
    artifacts: dict[str, Any]


class PipelineStep(Protocol):
    """Contract: a single composable unit of work in the pipeline."""

    @property
    def name(self) -> str:
        """Human-readable step name used for logging and tracing."""
        ...

    def execute(self, context: PipelineContext) -> StepResult: ...
