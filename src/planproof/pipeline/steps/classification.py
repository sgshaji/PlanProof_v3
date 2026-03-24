"""Pipeline step: document classification."""
from __future__ import annotations

from planproof.interfaces.extraction import DocumentClassifier
from planproof.interfaces.pipeline import PipelineContext, StepResult


class ClassificationStep:
    """Classify each input document into a known type (FORM, DRAWING, etc.).

    Uses the ``DocumentClassifier`` Protocol to determine document types,
    which downstream steps use to select the appropriate extraction strategy.
    """

    def __init__(self, classifier: DocumentClassifier) -> None:
        self._classifier = classifier

    @property
    def name(self) -> str:
        return "classification"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 2")
