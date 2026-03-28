"""Neo4j-backed Spatial-Narrative Knowledge Graph (SNKG) repository.

Implements all four graph Protocols defined in ``planproof.interfaces.graph``:

- :class:`~planproof.interfaces.graph.EntityPopulator`   (write-side)
- :class:`~planproof.interfaces.graph.ReferenceDataLoader` (write-side)
- :class:`~planproof.interfaces.graph.EvidenceProvider`  (read-side)
- :class:`~planproof.interfaces.graph.RuleProvider`      (read-side)

# WHY: A single concrete class implements all four Protocols so that it can be
# injected into any consumer as the narrowest interface that consumer needs.
# Consumers never hold a reference to ``Neo4jSNKG`` directly -- they depend on
# the Protocol slice appropriate to their role (ISP).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.representation.reference_data import load_reference_set
from planproof.schemas.assessability import EvidenceRequirement
from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)
from planproof.schemas.rules import RuleConfig

_log = get_logger(__name__)


class Neo4jSNKG:
    """Knowledge-graph repository backed by a Neo4j database.

    Parameters
    ----------
    driver:
        An initialised ``neo4j.Driver`` (or any compatible mock).  The caller
        is responsible for creating and closing the driver; ``Neo4jSNKG``
        exposes :meth:`close` as a convenience wrapper.
    """

    def __init__(self, driver: Any) -> None:  # noqa: ANN401
        self._driver = driver

    # ------------------------------------------------------------------
    # EntityPopulator
    # ------------------------------------------------------------------

    def populate_from_entities(self, entities: list[ExtractedEntity]) -> None:
        """Merge entities and their source documents into the graph.

        For each entity:

        1. MERGE a ``SourceDocument`` node keyed on ``name``.
        2. MERGE an ``ExtractedEntity`` node keyed on
           ``(entity_type, source_document, value)`` to deduplicate.
        3. Create an ``EXTRACTED_FROM`` relationship from the entity to the
           source document.

        Parameters
        ----------
        entities:
            Extracted entities to ingest; an empty list is a no-op.
        """
        if not entities:
            _log.debug("populate_from_entities.skip", reason="empty list")
            return

        _log.info("populate_from_entities", count=len(entities))
        with self._driver.session() as session:
            for entity in entities:
                # 1. Ensure SourceDocument node exists
                session.run(
                    """
                    MERGE (d:SourceDocument {name: $name})
                    """,
                    name=entity.source_document,
                )

                # 2. Merge ExtractedEntity node (deduplicated on type+doc+value)
                session.run(
                    """
                    MERGE (e:ExtractedEntity {
                        entity_type:      $entity_type,
                        source_document:  $source_document,
                        value:            $value
                    })
                    ON CREATE SET
                        e.unit               = $unit,
                        e.confidence         = $confidence,
                        e.source_page        = $source_page,
                        e.extraction_method  = $extraction_method,
                        e.timestamp          = $timestamp
                    """,
                    entity_type=entity.entity_type.value,
                    source_document=entity.source_document,
                    value=str(entity.value),
                    unit=entity.unit,
                    confidence=entity.confidence,
                    source_page=entity.source_page,
                    extraction_method=entity.extraction_method.value,
                    timestamp=entity.timestamp.isoformat(),
                )

                # 3. Create EXTRACTED_FROM relationship
                session.run(
                    """
                    MATCH (e:ExtractedEntity {
                        entity_type:     $entity_type,
                        source_document: $source_document,
                        value:           $value
                    })
                    MATCH (d:SourceDocument {name: $source_document})
                    MERGE (e)-[:EXTRACTED_FROM]->(d)
                    """,
                    entity_type=entity.entity_type.value,
                    source_document=entity.source_document,
                    value=str(entity.value),
                )

        _log.info("populate_from_entities.done", count=len(entities))

    # ------------------------------------------------------------------
    # ReferenceDataLoader
    # ------------------------------------------------------------------

    def load_reference_data(self, parcels_dir: Path, zones_dir: Path) -> None:
        """Load council parcel and zone reference data into the graph.

        Uses :func:`planproof.representation.reference_data.load_reference_set`
        to read ``parcel.geojson`` and ``zone.json`` from *parcels_dir* (both
        files are expected in the same directory; *zones_dir* is accepted for
        interface compatibility but the same directory is used for loading).

        Graph mutations:

        - MERGE ``Parcel`` node (``parcel_id``, ``set_id``, ``geometry_wkt``)
        - MERGE ``Zone`` node (``code``, ``name``)
        - MERGE ``APPLIES_TO`` relationship (Zone → Parcel)
        - For each rule_id in ``applicable_rules``: MERGE ``Rule`` node and
          ``APPLICABLE_IN`` relationship (Rule → Zone)

        Parameters
        ----------
        parcels_dir:
            Directory containing ``parcel.geojson``.
        zones_dir:
            Directory containing ``zone.json``.  When both files live in the
            same directory, pass the same path twice.
        """
        _log.info(
            "load_reference_data",
            parcels_dir=str(parcels_dir),
            zones_dir=str(zones_dir),
        )

        # load_reference_set expects a single reference_dir with both files;
        # we prefer parcels_dir as the canonical root.
        parcel, zone = load_reference_set(parcels_dir)

        with self._driver.session() as session:
            # Parcel node
            session.run(
                """
                MERGE (p:Parcel {parcel_id: $parcel_id})
                ON CREATE SET
                    p.set_id        = $set_id,
                    p.geometry_wkt  = $geometry_wkt
                """,
                parcel_id=parcel.parcel_id,
                set_id=parcel.set_id,
                geometry_wkt=parcel.geometry_wkt,
            )

            # Zone node
            session.run(
                """
                MERGE (z:Zone {code: $code})
                ON CREATE SET z.name = $name
                """,
                code=zone.zone_code,
                name=zone.zone_name,
            )

            # Zone APPLIES_TO Parcel
            session.run(
                """
                MATCH (z:Zone  {code: $zone_code})
                MATCH (p:Parcel {parcel_id: $parcel_id})
                MERGE (z)-[:APPLIES_TO]->(p)
                """,
                zone_code=zone.zone_code,
                parcel_id=parcel.parcel_id,
            )

            # Rule nodes and APPLICABLE_IN relationships
            for rule_id in zone.applicable_rules:
                session.run(
                    """
                    MERGE (r:Rule {rule_id: $rule_id})
                    """,
                    rule_id=rule_id,
                )
                session.run(
                    """
                    MATCH (r:Rule {rule_id: $rule_id})
                    MATCH (z:Zone {code: $zone_code})
                    MERGE (r)-[:APPLICABLE_IN]->(z)
                    """,
                    rule_id=rule_id,
                    zone_code=zone.zone_code,
                )

        _log.info("load_reference_data.done", parcel_id=parcel.parcel_id)

    # ------------------------------------------------------------------
    # EvidenceProvider
    # ------------------------------------------------------------------

    def get_evidence_for_rule(self, rule_id: str) -> list[ExtractedEntity]:
        """Return all entities linked through the rule→zone→parcel chain.

        Cypher traversal: Rule → (APPLICABLE_IN) → Zone → (APPLIES_TO) →
        Parcel ← (linked via shared parcel) ← ExtractedEntity.

        In practice, all entities uploaded to the graph are considered
        candidate evidence for any rule that applies to the same zone.
        The evaluator layer applies finer-grained filtering by
        ``required_evidence`` attributes.

        Parameters
        ----------
        rule_id:
            The identifier of the rule to find evidence for.

        Returns
        -------
        list[ExtractedEntity]
            All entities found; empty list if none.
        """
        _log.info("get_evidence_for_rule", rule_id=rule_id)
        results: list[ExtractedEntity] = []

        with self._driver.session() as session:
            records = session.run(
                """
                MATCH (r:Rule {rule_id: $rule_id})-[:APPLICABLE_IN]->(z:Zone)
                      -[:APPLIES_TO]->(p:Parcel)
                MATCH (e:ExtractedEntity)
                RETURN e
                """,
                rule_id=rule_id,
            )
            for record in records:
                data = record.data().get("e", {})
                entity = _record_to_entity(data)
                if entity is not None:
                    results.append(entity)

        _log.info("get_evidence_for_rule.done", rule_id=rule_id, count=len(results))
        return results

    def get_conflicting_evidence(
        self, attribute: str
    ) -> list[tuple[ExtractedEntity, ExtractedEntity]]:
        """Find entity pairs with the same attribute but different values.

        Two entities conflict when they share the same ``entity_type``
        (used as the attribute identifier — see module docstring) but have
        different ``value`` strings and come from different ``source_document``
        nodes.

        Parameters
        ----------
        attribute:
            The ``entity_type`` value to check for conflicts
            (e.g. ``"MEASUREMENT"``).

        Returns
        -------
        list[tuple[ExtractedEntity, ExtractedEntity]]
            Pairs of conflicting entities; empty list if none.
        """
        _log.info("get_conflicting_evidence", attribute=attribute)
        results: list[tuple[ExtractedEntity, ExtractedEntity]] = []

        with self._driver.session() as session:
            records = session.run(
                """
                MATCH (a:ExtractedEntity {entity_type: $attribute})
                MATCH (b:ExtractedEntity {entity_type: $attribute})
                WHERE a.value <> b.value
                  AND a.source_document <> b.source_document
                  AND id(a) < id(b)
                RETURN a, b
                """,
                attribute=attribute,
            )
            for record in records:
                data = record.data()
                entity_a = _record_to_entity(data.get("a", {}))
                entity_b = _record_to_entity(data.get("b", {}))
                if entity_a is not None and entity_b is not None:
                    results.append((entity_a, entity_b))

        _log.info(
            "get_conflicting_evidence.done", attribute=attribute, count=len(results)
        )
        return results

    # ------------------------------------------------------------------
    # RuleProvider
    # ------------------------------------------------------------------

    def get_rules_for_zone(self, zone: str) -> list[RuleConfig]:
        """Return all rules applicable to *zone*.

        Queries for ``Rule`` nodes reachable from the ``Zone`` node via
        ``APPLICABLE_IN`` relationships, then reconstructs
        :class:`~planproof.schemas.rules.RuleConfig` objects from the stored
        properties.

        Parameters
        ----------
        zone:
            Zone code to look up (e.g. ``"R2"``).

        Returns
        -------
        list[RuleConfig]
            Rules applicable to the zone; empty list if none.
        """
        _log.info("get_rules_for_zone", zone=zone)
        results: list[RuleConfig] = []

        with self._driver.session() as session:
            records = session.run(
                """
                MATCH (r:Rule)-[:APPLICABLE_IN]->(z:Zone {code: $zone})
                RETURN r
                """,
                zone=zone,
            )
            for record in records:
                data = record.data().get("r", {})
                rule = _record_to_rule(data)
                if rule is not None:
                    results.append(rule)

        _log.info("get_rules_for_zone.done", zone=zone, count=len(results))
        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Delete all nodes and relationships from the graph.

        Intended for use in tests or when resetting the graph between
        processing runs.
        """
        _log.warning("clear", action="DETACH DELETE all nodes")
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def close(self) -> None:
        """Close the underlying Neo4j driver connection."""
        _log.info("close")
        self._driver.close()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _record_to_entity(data: dict[str, Any]) -> ExtractedEntity | None:
    """Convert a Neo4j node property dict to an :class:`ExtractedEntity`.

    Returns ``None`` if *data* is empty or malformed, so callers can safely
    skip invalid records without crashing.

    Parameters
    ----------
    data:
        A ``dict`` of Neo4j node properties for an ``ExtractedEntity`` node.
    """
    if not data:
        return None

    try:
        raw_ts = data.get("timestamp", datetime.now().isoformat())
        ts = datetime.fromisoformat(str(raw_ts)) if isinstance(raw_ts, str) else raw_ts

        return ExtractedEntity(
            entity_type=EntityType(data["entity_type"]),
            value=data.get("value", ""),
            unit=data.get("unit"),
            confidence=float(data.get("confidence", 0.0)),
            source_document=str(data.get("source_document", "")),
            source_page=(
                int(data["source_page"])
                if data.get("source_page") is not None
                else None
            ),
            source_region=None,  # BoundingBox not stored in flat Neo4j props
            extraction_method=ExtractionMethod(data["extraction_method"]),
            timestamp=ts,
        )
    except (KeyError, ValueError, TypeError) as exc:
        _log.warning("record_to_entity.failed", error=str(exc))
        return None


def _record_to_rule(data: dict[str, Any]) -> RuleConfig | None:
    """Convert a Neo4j node property dict to a :class:`RuleConfig`.

    Parameters
    ----------
    data:
        A ``dict`` of Neo4j node properties for a ``Rule`` node.
    """
    if not data:
        return None

    try:
        raw_params = data.get("parameters", "{}")
        parameters: dict[str, Any] = (
            json.loads(raw_params) if isinstance(raw_params, str) else dict(raw_params)
        )

        raw_evidence = data.get("required_evidence", "[]")
        evidence_list: list[dict[str, Any]] = (
            json.loads(raw_evidence)
            if isinstance(raw_evidence, str)
            else list(raw_evidence)
        )
        required_evidence = [EvidenceRequirement(**e) for e in evidence_list]

        return RuleConfig(
            rule_id=str(data["rule_id"]),
            description=str(data.get("description", "")),
            policy_source=str(data.get("policy_source", "")),
            evaluation_type=str(data.get("evaluation_type", "")),
            parameters=parameters,
            required_evidence=required_evidence,
        )
    except (KeyError, ValueError, TypeError) as exc:
        _log.warning("record_to_rule.failed", error=str(exc))
        return None
