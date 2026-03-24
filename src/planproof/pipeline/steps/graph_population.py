"""Pipeline step: populate the Spatial Normative Knowledge Graph."""
from __future__ import annotations

from planproof.interfaces.graph import EntityPopulator
from planproof.interfaces.pipeline import PipelineContext, StepResult


class GraphPopulationStep:
    """Push extracted entities into the Neo4j-backed knowledge graph.

    Uses the ``EntityPopulator`` Protocol so that the step is decoupled
    from the concrete graph implementation.
    """

    def __init__(self, populator: EntityPopulator) -> None:
        self._populator = populator

    @property
    def name(self) -> str:
        return "graph_population"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 3")
