"""MinEvidenceRequestGenerator — produces actionable evidence requests.

For each NOT_ASSESSABLE rule, converts the rule's missing EvidenceRequirements
into structured EvidenceRequests with human-readable guidance sourced from a
pre-loaded guidance dictionary (typically loaded from YAML).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from planproof.schemas.assessability import AssessabilityResult
from planproof.schemas.pipeline import EvidenceRequest, MissingEvidence


class MinEvidenceRequestGenerator:
    """Minimal implementation of the EvidenceRequestGenerator Protocol.

    Parameters
    ----------
    guidance:
        Mapping of attribute name → human-readable guidance text shown to
        the applicant.  Unknown attributes fall back to a generic message.
    """

    def __init__(self, guidance: dict[str, str]) -> None:
        self._guidance = guidance

    # ------------------------------------------------------------------
    # Alternate constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> "MinEvidenceRequestGenerator":
        """Load guidance from a YAML file and return a new instance.

        Parameters
        ----------
        path:
            Path to a YAML file mapping attribute names to guidance strings.
        """
        with open(path, encoding="utf-8") as fh:
            data: dict[str, str] = yaml.safe_load(fh) or {}
        return cls(guidance=data)

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def generate_requests(
        self, not_assessable: list[AssessabilityResult]
    ) -> list[EvidenceRequest]:
        """Generate EvidenceRequests for every NOT_ASSESSABLE result.

        ASSESSABLE results are silently skipped.  Each EvidenceRequirement
        inside a NOT_ASSESSABLE result is converted to a MissingEvidence
        item with attribute-specific guidance text.

        Parameters
        ----------
        not_assessable:
            List of AssessabilityResults — may contain a mix of statuses;
            only NOT_ASSESSABLE entries produce output.

        Returns
        -------
        list[EvidenceRequest]
            One EvidenceRequest per NOT_ASSESSABLE result, each containing
            one MissingEvidence item per EvidenceRequirement.
        """
        requests: list[EvidenceRequest] = []

        for result in not_assessable:
            if result.status != "NOT_ASSESSABLE":
                continue

            missing_items: list[MissingEvidence] = []
            for req in result.missing_evidence:
                guidance = self._guidance.get(
                    req.attribute,
                    f"Please provide {req.attribute} from an acceptable source document.",
                )
                missing_items.append(
                    MissingEvidence(
                        attribute=req.attribute,
                        acceptable_document_types=req.acceptable_sources,
                        guidance=guidance,
                    )
                )

            requests.append(
                EvidenceRequest(rule_id=result.rule_id, missing=missing_items)
            )

        return requests
