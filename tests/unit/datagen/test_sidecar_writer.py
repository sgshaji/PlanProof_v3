"""Tests for sidecar_writer — ground_truth.json assembly and writing.

# WHY: Ground truth JSON is the primary artefact that drives evaluation.
# These tests verify that every required section (values, verdicts, documents,
# degradation params) is present in the output, preventing silent omissions
# that would cause evaluation failures far downstream.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planproof.datagen.output.sidecar_writer import write_ground_truth
from planproof.datagen.rendering.models import GeneratedDocument, PlacedValue
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict
from planproof.schemas.entities import BoundingBox, DocumentType, EntityType


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


def _make_scenario() -> Scenario:
    """Build a minimal but complete Scenario for writer tests.

    # WHY: A fixed deterministic scenario prevents test flakiness — all tests
    # that read the same fixture always see the same data.
    """
    values = (
        Value(
            attribute="front_setback",
            value=7.5,
            unit="metres",
            display_text="7.5m",
        ),
        Value(
            attribute="site_coverage",
            value=35.0,
            unit="percent",
            display_text="35.0%",
        ),
    )
    verdicts = (
        Verdict(
            rule_id="R001",
            outcome="PASS",
            evaluated_value=7.5,
            threshold=8.0,
        ),
        Verdict(
            rule_id="R002",
            outcome="PASS",
            evaluated_value=35.0,
            threshold=50.0,
        ),
    )
    documents = (
        DocumentSpec(
            doc_type="FORM",
            file_format="pdf",
            values_to_place=("front_setback",),
        ),
    )
    return Scenario(
        set_id="SET_COMPLIANT_42",
        category="compliant",
        seed=42,
        profile_id="standard",
        difficulty="low",
        degradation_preset="clean",
        values=values,
        verdicts=verdicts,
        documents=documents,
        edge_case_strategy=None,
    )


def _make_placed_value(attribute: str, text: str, value: float) -> PlacedValue:
    """Create a PlacedValue with a standard bounding box."""
    return PlacedValue(
        attribute=attribute,
        value=value,
        text_rendered=text,
        page=1,
        bounding_box=BoundingBox(x=100.0, y=200.0, width=80.0, height=20.0, page=1),
        entity_type=EntityType.MEASUREMENT,
    )


def _make_generated_docs() -> list[GeneratedDocument]:
    """Build a list with one GeneratedDocument containing a PlacedValue."""
    placed = _make_placed_value("front_setback", "7.5m", 7.5)
    return [
        GeneratedDocument(
            filename="SET_COMPLIANT_42-compliant-FORM.pdf",
            doc_type=DocumentType.FORM,
            content_bytes=b"%PDF-1.4 minimal",
            file_format="pdf",
            placed_values=(placed,),
        )
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteGroundTruth:
    """Tests for write_ground_truth()."""

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        """Output file must be valid JSON with all top-level required keys.

        # WHY: Missing required keys (e.g. no 'rule_verdicts') would cause the
        # evaluation harness to crash with a KeyError rather than a clean error
        # message.  Checking required keys here surfaces the problem immediately.
        """
        scenario = _make_scenario()
        generated_docs = _make_generated_docs()
        degradation_params = {"preset": "clean", "seed": 42}

        write_ground_truth(scenario, generated_docs, degradation_params, tmp_path)

        gt_path = tmp_path / "ground_truth.json"
        assert gt_path.exists(), "ground_truth.json was not written"

        with gt_path.open(encoding="utf-8") as fh:
            data = json.load(fh)

        # All top-level keys required by spec Section 7
        required_keys = {
            "set_id",
            "category",
            "seed",
            "difficulty",
            "values",
            "rule_verdicts",
            "documents",
            "degradation",
        }
        missing = required_keys - data.keys()
        assert not missing, f"Missing required keys in ground_truth.json: {missing}"

    def test_includes_all_values(self, tmp_path: Path) -> None:
        """Every Value in the scenario must appear in ground_truth['values'].

        # WHY: A value absent from the ground truth JSON cannot be evaluated by
        # the rule engine, so missed values silently reduce coverage.
        """
        scenario = _make_scenario()
        generated_docs = _make_generated_docs()
        degradation_params = {"preset": "clean"}

        write_ground_truth(scenario, generated_docs, degradation_params, tmp_path)

        with (tmp_path / "ground_truth.json").open(encoding="utf-8") as fh:
            data = json.load(fh)

        value_attributes = {v["attribute"] for v in data["values"]}
        expected_attributes = {v.attribute for v in scenario.values}
        assert expected_attributes == value_attributes

    def test_includes_document_extractions(self, tmp_path: Path) -> None:
        """Each document entry must include a non-empty extractions list.

        # WHY: Extractions link placed values to their bounding boxes in the
        # generated document.  An empty extraction list means the evaluator
        # cannot locate the value in the document and must guess.
        """
        scenario = _make_scenario()
        generated_docs = _make_generated_docs()
        degradation_params = {"preset": "clean"}

        write_ground_truth(scenario, generated_docs, degradation_params, tmp_path)

        with (tmp_path / "ground_truth.json").open(encoding="utf-8") as fh:
            data = json.load(fh)

        assert len(data["documents"]) > 0
        for doc_entry in data["documents"]:
            assert "extractions" in doc_entry, "document entry missing 'extractions'"
            assert isinstance(doc_entry["extractions"], list)

    def test_includes_rule_verdicts(self, tmp_path: Path) -> None:
        """All verdicts from the scenario must be serialised into rule_verdicts.

        # WHY: The evaluation harness compares rule engine output against
        # rule_verdicts.  Missing a verdict means that rule is never checked.
        """
        scenario = _make_scenario()
        generated_docs = _make_generated_docs()
        degradation_params = {}

        write_ground_truth(scenario, generated_docs, degradation_params, tmp_path)

        with (tmp_path / "ground_truth.json").open(encoding="utf-8") as fh:
            data = json.load(fh)

        verdict_ids = {v["rule_id"] for v in data["rule_verdicts"]}
        expected_ids = {v.rule_id for v in scenario.verdicts}
        assert expected_ids == verdict_ids

    def test_degradation_params_embedded(self, tmp_path: Path) -> None:
        """Degradation parameters must appear verbatim in ground_truth['degradation'].

        # WHY: Storing degradation params in the sidecar lets post-hoc analysis
        # correlate extraction accuracy with specific degradation settings without
        # re-running the generator.
        """
        scenario = _make_scenario()
        generated_docs = _make_generated_docs()
        degradation_params = {"preset": "moderate_scan", "rotation_deg": 2.5}

        write_ground_truth(scenario, generated_docs, degradation_params, tmp_path)

        with (tmp_path / "ground_truth.json").open(encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["degradation"] == degradation_params
