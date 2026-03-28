"""Unit tests for Neo4jSNKG — all four protocol implementations.

Neo4j driver interactions are fully mocked; no database connection is required.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from planproof.representation.snkg import Neo4jSNKG
from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)
from planproof.schemas.rules import RuleConfig

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, 12, 0, 0)


def _make_entity(
    entity_type: EntityType = EntityType.MEASUREMENT,
    value: object = "8.5m",
    unit: str | None = "m",
    confidence: float = 0.9,
    source_document: str = "DA-001.pdf",
    source_page: int | None = 1,
    extraction_method: ExtractionMethod = ExtractionMethod.OCR_LLM,
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        unit=unit,
        confidence=confidence,
        source_document=source_document,
        source_page=source_page,
        extraction_method=extraction_method,
        timestamp=_NOW,
    )


def _make_driver() -> MagicMock:
    """Return a MagicMock neo4j driver with a context-manager session."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver


def _make_snkg(driver: MagicMock | None = None) -> Neo4jSNKG:
    if driver is None:
        driver = _make_driver()
    return Neo4jSNKG(driver=driver)


# ---------------------------------------------------------------------------
# Reference data fixtures (mirrors test_reference_data.py helpers)
# ---------------------------------------------------------------------------

_SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [151.0, -33.87],
                        [151.0001304, -33.87],
                        [151.0001304, -33.8696069],
                        [151.0, -33.8696069],
                        [151.0, -33.87],
                    ]
                ],
            },
            "properties": {
                "parcel_id": "PARCEL_001",
                "set_id": "SET_001",
            },
        }
    ],
}

_SAMPLE_ZONE = {
    "zone_code": "R2",
    "zone_name": "Low Density Residential",
    "applicable_rules": ["R001", "R002"],
}


@pytest.fixture()
def reference_dir(tmp_path: Path) -> Path:
    (tmp_path / "parcel.geojson").write_text(json.dumps(_SAMPLE_GEOJSON))
    (tmp_path / "zone.json").write_text(json.dumps(_SAMPLE_ZONE))
    return tmp_path


# ---------------------------------------------------------------------------
# EntityPopulator
# ---------------------------------------------------------------------------


class TestPopulateFromEntities:
    def test_creates_session_and_runs_cypher(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        entity = _make_entity()

        snkg.populate_from_entities([entity])

        session = driver.session.return_value.__enter__.return_value
        assert session.run.called

    def test_runs_merge_for_source_document(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        entity = _make_entity(source_document="DA-001.pdf")

        snkg.populate_from_entities([entity])

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "SourceDocument" in calls_text

    def test_runs_merge_for_entity_node(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        entity = _make_entity()

        snkg.populate_from_entities([entity])

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "ExtractedEntity" in calls_text

    def test_runs_extracted_from_relationship(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        entity = _make_entity()

        snkg.populate_from_entities([entity])

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "EXTRACTED_FROM" in calls_text

    def test_empty_list_does_not_error(self) -> None:
        snkg = _make_snkg()
        # Must not raise even with an empty list
        snkg.populate_from_entities([])

    def test_multiple_entities_each_trigger_merge(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        entities = [_make_entity(), _make_entity(value="9m", source_document="B.pdf")]

        snkg.populate_from_entities(entities)

        session = driver.session.return_value.__enter__.return_value
        # At minimum we expect one run call per entity
        assert session.run.call_count >= len(entities)


# ---------------------------------------------------------------------------
# ReferenceDataLoader
# ---------------------------------------------------------------------------


class TestLoadReferenceData:
    def test_creates_parcel_node(self, reference_dir: Path) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)

        snkg.load_reference_data(reference_dir, reference_dir)

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "Parcel" in calls_text

    def test_creates_zone_node(self, reference_dir: Path) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)

        snkg.load_reference_data(reference_dir, reference_dir)

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "Zone" in calls_text

    def test_creates_applies_to_relationship(self, reference_dir: Path) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)

        snkg.load_reference_data(reference_dir, reference_dir)

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "APPLIES_TO" in calls_text

    def test_creates_rule_nodes(self, reference_dir: Path) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)

        snkg.load_reference_data(reference_dir, reference_dir)

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "Rule" in calls_text

    def test_creates_applicable_in_relationship(self, reference_dir: Path) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)

        snkg.load_reference_data(reference_dir, reference_dir)

        session = driver.session.return_value.__enter__.return_value
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "APPLICABLE_IN" in calls_text


# ---------------------------------------------------------------------------
# EvidenceProvider
# ---------------------------------------------------------------------------


class TestGetEvidenceForRule:
    def test_calls_session_run(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = []

        snkg.get_evidence_for_rule("R001")

        assert session.run.called

    def test_returns_empty_list_when_no_records(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = []

        result = snkg.get_evidence_for_rule("R001")

        assert result == []

    def test_returns_extracted_entities_from_records(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value

        # Simulate a neo4j record dict returned from session.run
        record_data = {
            "entity_type": "MEASUREMENT",
            "value": "8.5m",
            "unit": "m",
            "confidence": 0.9,
            "source_document": "DA-001.pdf",
            "source_page": 1,
            "source_region": None,
            "extraction_method": "OCR_LLM",
            "timestamp": _NOW.isoformat(),
        }
        mock_record = MagicMock()
        mock_record.__getitem__ = MagicMock(side_effect=record_data.__getitem__)
        mock_record.data.return_value = {"e": record_data}
        session.run.return_value = [mock_record]

        result = snkg.get_evidence_for_rule("R001")

        assert len(result) == 1
        assert isinstance(result[0], ExtractedEntity)
        assert result[0].entity_type == EntityType.MEASUREMENT


class TestGetConflictingEvidence:
    def test_returns_empty_for_no_conflicts(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = []

        result = snkg.get_conflicting_evidence("MEASUREMENT")

        assert result == []

    def test_calls_session_run(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = []

        snkg.get_conflicting_evidence("ADDRESS")

        assert session.run.called

    def test_returns_pairs_when_conflicts_exist(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value

        entity_data_a = {
            "entity_type": "MEASUREMENT",
            "value": "8.5m",
            "unit": "m",
            "confidence": 0.9,
            "source_document": "DA-001.pdf",
            "source_page": 1,
            "source_region": None,
            "extraction_method": "OCR_LLM",
            "timestamp": _NOW.isoformat(),
        }
        entity_data_b = {
            "entity_type": "MEASUREMENT",
            "value": "9.0m",
            "unit": "m",
            "confidence": 0.85,
            "source_document": "DA-002.pdf",
            "source_page": 2,
            "source_region": None,
            "extraction_method": "OCR_LLM",
            "timestamp": _NOW.isoformat(),
        }
        mock_record = MagicMock()
        mock_record.data.return_value = {"a": entity_data_a, "b": entity_data_b}
        session.run.return_value = [mock_record]

        result = snkg.get_conflicting_evidence("MEASUREMENT")

        assert len(result) == 1
        pair = result[0]
        assert isinstance(pair[0], ExtractedEntity)
        assert isinstance(pair[1], ExtractedEntity)


# ---------------------------------------------------------------------------
# RuleProvider
# ---------------------------------------------------------------------------


class TestGetRulesForZone:
    def test_calls_session_run(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = []

        snkg.get_rules_for_zone("R2")

        assert session.run.called

    def test_returns_empty_for_no_rules(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = []

        result = snkg.get_rules_for_zone("R2")

        assert result == []

    def test_returns_rule_configs_from_records(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)
        session = driver.session.return_value.__enter__.return_value

        rule_data = {
            "rule_id": "R001",
            "description": "Max building height",
            "policy_source": "LEP 2.1",
            "evaluation_type": "threshold",
            "parameters": '{"max_value": 9.5, "unit": "m"}',
            "required_evidence": "[]",
        }
        mock_record = MagicMock()
        mock_record.data.return_value = {"r": rule_data}
        session.run.return_value = [mock_record]

        result = snkg.get_rules_for_zone("R2")

        assert len(result) == 1
        assert isinstance(result[0], RuleConfig)
        assert result[0].rule_id == "R001"


# ---------------------------------------------------------------------------
# Utility methods
# ---------------------------------------------------------------------------


class TestClear:
    def test_runs_detach_delete(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)

        snkg.clear()

        session = driver.session.return_value.__enter__.return_value
        assert session.run.called
        calls_text = " ".join(str(c) for c in session.run.call_args_list)
        assert "DETACH DELETE" in calls_text


class TestClose:
    def test_calls_driver_close(self) -> None:
        driver = _make_driver()
        snkg = _make_snkg(driver)

        snkg.close()

        driver.close.assert_called_once()
