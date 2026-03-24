"""Protocols for knowledge-graph operations (ISP-split).

# WHY: The original monolithic SNKGRepository violated the Interface
# Segregation Principle -- callers that only needed to *read* evidence were
# forced to depend on write-side methods (populate, load reference data) and
# vice-versa.  Splitting into four narrow Protocols means:
#
#   1. EntityPopulator   -- write-side: ingest extracted entities
#   2. ReferenceDataLoader -- write-side: load council parcel/zone data
#   3. EvidenceProvider  -- read-side: query evidence for rule evaluation
#   4. RuleProvider      -- read-side: query applicable rules for a zone
#
# A single concrete class (e.g. Neo4jSNKG) may implement all four, but each
# consumer only couples to the slice it actually uses.  This keeps tests
# minimal and makes swapping storage backends safe.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from planproof.schemas.entities import ExtractedEntity
from planproof.schemas.rules import RuleConfig


class EntityPopulator(Protocol):
    """Write-side: push extracted entities into the knowledge graph.

    # WHY: Extraction steps only need this -- they should not see query methods.
    """

    def populate_from_entities(self, entities: list[ExtractedEntity]) -> None: ...


class ReferenceDataLoader(Protocol):
    """Write-side: load council-supplied reference data (parcels, zones).

    # WHY: Reference-data loading is a separate concern from entity ingestion
    # and happens once per council dataset, not per document.
    """

    def load_reference_data(self, parcels_dir: Path, zones_dir: Path) -> None: ...


class EvidenceProvider(Protocol):
    """Read-side: retrieve evidence needed by rule evaluators.

    # WHY: Rule evaluators and the assessability evaluator only need to *read*
    # evidence -- giving them write access would be a Liskov / ISP violation.
    """

    def get_evidence_for_rule(self, rule_id: str) -> list[ExtractedEntity]: ...

    def get_conflicting_evidence(
        self, attribute: str
    ) -> list[tuple[ExtractedEntity, ExtractedEntity]]: ...


class RuleProvider(Protocol):
    """Read-side: look up which rules apply to a given zone.

    # WHY: Separated from EvidenceProvider because rule-lookup is a metadata
    # concern (what *should* be checked) vs. evidence-lookup (what *was found*).
    """

    def get_rules_for_zone(self, zone: str) -> list[RuleConfig]: ...
