"""Integration test: verify Neo4j Aura connectivity.

Requires a running Neo4j instance with credentials in .env.
Skipped automatically if the connection fails (e.g. in CI without Neo4j).
"""
from __future__ import annotations

import os

import pytest
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("PLANPROOF_NEO4J_URI", "")
NEO4J_USER = os.getenv("PLANPROOF_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("PLANPROOF_NEO4J_PASSWORD", "")

needs_neo4j = pytest.mark.skipif(
    not NEO4J_URI or not NEO4J_PASSWORD,
    reason="PLANPROOF_NEO4J_URI/PASSWORD not set",
)


@needs_neo4j
class TestNeo4jConnectivity:
    """Verify we can reach the Neo4j Aura instance."""

    def test_can_connect_and_query(self) -> None:
        """Open a session, run a trivial query, confirm a result."""
        driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        try:
            driver.verify_connectivity()
            with driver.session() as session:
                result = session.run("RETURN 1 AS n")
                record = result.single()
                assert record is not None
                assert record["n"] == 1
        finally:
            driver.close()

    def test_can_write_and_read_node(self) -> None:
        """Create a temporary node, read it back, then clean up."""
        driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        try:
            with driver.session() as session:
                # Write
                session.run(
                    "CREATE (t:_Test {name: $name})",
                    name="planproof_connectivity_test",
                )
                # Read
                result = session.run(
                    "MATCH (t:_Test {name: $name}) RETURN t.name AS name",
                    name="planproof_connectivity_test",
                )
                record = result.single()
                assert record is not None
                assert record["name"] == "planproof_connectivity_test"
                # Cleanup
                session.run("MATCH (t:_Test) DELETE t")
        finally:
            driver.close()
