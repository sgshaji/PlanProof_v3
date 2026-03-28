"""Pipeline step: populate the Spatial Normative Knowledge Graph."""
from __future__ import annotations

from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.graph import EntityPopulator
from planproof.interfaces.pipeline import PipelineContext, StepResult

logger = get_logger(__name__)


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
        """Populate the knowledge graph with extracted entities.

        Steps:
        1. Extract entities from context (default to empty list)
        2. Extract metadata from context (default to empty dict)
        3. If reference_dir is in metadata and populator has load_reference_data,
           load reference data
        4. Call populate_from_entities with the entities
        5. Store populator in context["graph_ref"] for downstream steps
        6. Return success with entity_count

        Returns:
            StepResult with success, message, and entity_count artifact
        """
        entities = context.get("entities", [])
        metadata = context.get("metadata", {})

        # Load reference data if available
        if (
            "reference_dir" in metadata
            and hasattr(self._populator, "load_reference_data")
        ):
            ref_path = Path(metadata["reference_dir"])
            try:
                self._populator.load_reference_data(ref_path, ref_path)
                logger.info("reference_data_loaded", reference_dir=str(ref_path))
            except Exception as e:
                logger.warning(
                    "reference_data_load_failed",
                    reference_dir=str(ref_path),
                    error=str(e),
                )

        # Populate the graph with entities
        try:
            self._populator.populate_from_entities(entities)
            logger.info("graph_populated", entity_count=len(entities))
        except Exception as e:
            logger.error(
                "graph_population_failed",
                entity_count=len(entities),
                error=str(e),
            )
            return {
                "success": False,
                "message": f"Failed to populate graph: {e}",
                "artifacts": {"entity_count": 0},
            }

        # Store the populator for downstream steps
        context["graph_ref"] = self._populator

        return {
            "success": True,
            "message": f"Populated graph with {len(entities)} entities",
            "artifacts": {"entity_count": len(entities)},
        }
