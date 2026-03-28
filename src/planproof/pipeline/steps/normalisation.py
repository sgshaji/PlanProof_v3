"""Pipeline step: entity normalisation and unit conversion."""
from __future__ import annotations

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.representation.normalisation import Normaliser

_log = get_logger(__name__)


class NormalisationStep:
    """Normalise extracted entities to canonical units and formats.

    Converts measurements to SI units, standardises address formats,
    and resolves abbreviations so that downstream comparison logic
    operates on uniform representations.
    """

    def __init__(self, normaliser: Normaliser | None = None) -> None:
        """Initialise the normalisation step.

        Parameters
        ----------
        normaliser:
            Optional Normaliser instance. If not provided, a default
            Normaliser with the built-in registry is created.
        """
        self._normaliser = normaliser if normaliser is not None else Normaliser()

    @property
    def name(self) -> str:
        return "normalisation"

    def execute(self, context: PipelineContext) -> StepResult:
        """Normalise all entities in the context to canonical representations.

        Parameters
        ----------
        context:
            The pipeline context containing entities to normalise.

        Returns
        -------
        StepResult:
            A result dict with success flag and normalisation count in artifacts.
        """
        entities = context.get("entities", [])

        if not entities:
            _log.debug("normalisation_no_entities")
            return {"success": True, "artifacts": {"count": 0}}

        normalised_entities = self._normaliser.normalise_all(entities)
        context["entities"] = normalised_entities

        _log.debug("normalisation_complete", count=len(normalised_entities))
        return {"success": True, "artifacts": {"count": len(normalised_entities)}}
