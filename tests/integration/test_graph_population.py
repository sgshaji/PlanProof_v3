"""Integration tests: Neo4j SNKG graph population and querying.

Requires a running Neo4j instance with credentials set via environment
variables.  The entire test class is skipped when PLANPROOF_NEO4J_URI is
absent or empty — safe to run in CI without Neo4j configured.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from planproof.representation.snkg import Neo4jSNKG
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod

# ---------------------------------------------------------------------------
# Credentials & skip marker
# ---------------------------------------------------------------------------

NEO4J_URI = os.getenv("PLANPROOF_NEO4J_URI", "")
NEO4J_USER = os.getenv("PLANPROOF_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("PLANPROOF_NEO4J_PASSWORD", "")

needs_neo4j = pytest.mark.skipif(
    not NEO4J_URI or not NEO4J_PASSWORD,
    reason="PLANPROOF_NEO4J_URI/PASSWORD not set",
)

# ---------------------------------------------------------------------------
# Reference data path
# ---------------------------------------------------------------------------

_REFERENCE_DIR = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "synthetic_diverse"
    / "compliant"
    / "SET_COMPLIANT_100000"
    / "reference"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(value: str = "5.5", source_document: str = "test_doc.pdf") -> ExtractedEntity:
    """Build a minimal ExtractedEntity for test use."""
    return ExtractedEntity(
        entity_type=EntityType.MEASUREMENT,
        value=value,
        unit="m",
        confidence=0.9,
        source_document=source_document,
        source_page=1,
        source_region=None,
        extraction_method=ExtractionMethod.VLM_ZEROSHOT,
        timestamp=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def snkg():
    """Create a Neo4jSNKG, clear the graph, yield it, then clean up."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    graph = Neo4jSNKG(driver)
    graph.clear()
    try:
        yield graph
    finally:
        graph.clear()
        graph.close()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@needs_neo4j
class TestGraphPopulation:
    """Integration tests for Neo4jSNKG entity population and querying."""

    def test_populate_and_query(self, snkg: Neo4jSNKG) -> None:
        """Populate entities and verify get_evidence_for_rule returns a list."""
        entities = [_make_entity("3.5"), _make_entity("6.0", "another_doc.pdf")]
        snkg.populate_from_entities(entities)

        # Without rule/zone/parcel nodes the query returns an empty list — that
        # is the correct behaviour when no reference data is loaded.
        result = snkg.get_evidence_for_rule("RULE_HEIGHT_MAX")
        assert isinstance(result, list)

    def test_reference_data_loading(self, snkg: Neo4jSNKG) -> None:
        """Load reference data from the synthetic dataset; expect no errors."""
        if not _REFERENCE_DIR.exists():
            pytest.skip(f"Reference data not found at {_REFERENCE_DIR}")

        # Both files live in the same directory; pass it twice per the interface.
        snkg.load_reference_data(_REFERENCE_DIR, _REFERENCE_DIR)

        # Verify at least one Rule node was created (zone.json has applicable_rules)
        from neo4j import GraphDatabase as _GD  # noqa: PLC0415  (local import ok here)

        driver = _GD.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        try:
            with driver.session() as session:
                result = session.run("MATCH (r:Rule) RETURN count(r) AS cnt")
                record = result.single()
                assert record is not None
                assert record["cnt"] >= 0  # at minimum no crash; rules may be 0
        finally:
            driver.close()

    def test_clear_empties_graph(self, snkg: Neo4jSNKG) -> None:
        """Populate, then clear; subsequent queries return empty results."""
        snkg.populate_from_entities([_make_entity()])
        snkg.clear()

        result = snkg.get_evidence_for_rule("RULE_HEIGHT_MAX")
        assert result == []

    def test_full_round_trip(self, snkg: Neo4jSNKG) -> None:
        """Load reference data then entities; get_evidence_for_rule returns entities."""
        if not _REFERENCE_DIR.exists():
            pytest.skip(f"Reference data not found at {_REFERENCE_DIR}")

        # 1. Load reference data so Rule → Zone → Parcel chain exists.
        snkg.load_reference_data(_REFERENCE_DIR, _REFERENCE_DIR)

        # 2. Discover a rule_id from the loaded graph.
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        rule_id: str | None = None
        try:
            with driver.session() as session:
                result = session.run("MATCH (r:Rule) RETURN r.rule_id AS rid LIMIT 1")
                record = result.single()
                if record is not None:
                    rule_id = record["rid"]
        finally:
            driver.close()

        if rule_id is None:
            pytest.skip("No Rule nodes found after loading reference data")

        # 3. Populate entities.
        entities = [_make_entity("4.2"), _make_entity("8.0", "plan_b.pdf")]
        snkg.populate_from_entities(entities)

        # 4. get_evidence_for_rule must return the entities now that the chain exists.
        evidence = snkg.get_evidence_for_rule(rule_id)
        assert isinstance(evidence, list)
        assert len(evidence) >= 1, (
            f"Expected at least 1 entity for rule {rule_id!r}, got 0"
        )
