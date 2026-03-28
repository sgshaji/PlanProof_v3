"""Unit tests for MinEvidenceRequestGenerator.

TDD: tests written first; implementation follows.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
    EvidenceRequirement,
)
from planproof.schemas.pipeline import EvidenceRequest, MissingEvidence
from planproof.output.evidence_request import MinEvidenceRequestGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_not_assessable(
    rule_id: str,
    missing: list[EvidenceRequirement],
) -> AssessabilityResult:
    return AssessabilityResult(
        rule_id=rule_id,
        status="NOT_ASSESSABLE",
        blocking_reason=BlockingReason.MISSING_EVIDENCE,
        missing_evidence=missing,
        conflicts=[],
    )


def _make_assessable(rule_id: str) -> AssessabilityResult:
    return AssessabilityResult(
        rule_id=rule_id,
        status="ASSESSABLE",
        blocking_reason=BlockingReason.NONE,
        missing_evidence=[],
        conflicts=[],
    )


def _make_requirement(attribute: str, sources: list[str]) -> EvidenceRequirement:
    return EvidenceRequirement(
        attribute=attribute,
        acceptable_sources=sources,
        min_confidence=0.8,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMinEvidenceRequestGeneratorGeneratesRequests:
    """generate_requests returns one EvidenceRequest per NOT_ASSESSABLE rule."""

    def test_generates_one_request_per_not_assessable_rule(self):
        req = _make_requirement("building_height", ["elevation_drawing"])
        result = _make_not_assessable("R001", [req])
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result])

        assert len(requests) == 1
        assert requests[0].rule_id == "R001"

    def test_missing_evidence_maps_to_missing_list(self):
        req = _make_requirement("building_height", ["elevation_drawing", "form"])
        result = _make_not_assessable("R002", [req])
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result])

        assert len(requests[0].missing) == 1
        me = requests[0].missing[0]
        assert me.attribute == "building_height"
        assert me.acceptable_document_types == ["elevation_drawing", "form"]

    def test_multiple_missing_requirements_produce_multiple_missing_items(self):
        reqs = [
            _make_requirement("building_height", ["elevation_drawing"]),
            _make_requirement("rear_garden_depth", ["site_plan"]),
        ]
        result = _make_not_assessable("R003", reqs)
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result])

        assert len(requests[0].missing) == 2
        attributes = {m.attribute for m in requests[0].missing}
        assert attributes == {"building_height", "rear_garden_depth"}


class TestMinEvidenceRequestGeneratorGuidance:
    """Guidance text is applied from the guidance dict."""

    def test_uses_guidance_text_when_attribute_known(self):
        guidance = {
            "building_height": "Provide a dimensioned elevation drawing showing the overall building height in metres."
        }
        req = _make_requirement("building_height", ["elevation_drawing"])
        result = _make_not_assessable("R001", [req])
        generator = MinEvidenceRequestGenerator(guidance=guidance)

        requests = generator.generate_requests([result])

        assert requests[0].missing[0].guidance == guidance["building_height"]

    def test_falls_back_for_unknown_attribute(self):
        req = _make_requirement("unknown_attr", ["some_doc"])
        result = _make_not_assessable("R001", [req])
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result])

        expected = "Please provide unknown_attr from an acceptable source document."
        assert requests[0].missing[0].guidance == expected

    def test_fallback_includes_attribute_name(self):
        req = _make_requirement("site_coverage", ["floor_plan"])
        result = _make_not_assessable("R001", [req])
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result])

        assert "site_coverage" in requests[0].missing[0].guidance


class TestMinEvidenceRequestGeneratorFiltering:
    """ASSESSABLE results must be excluded from output."""

    def test_empty_input_returns_empty_list(self):
        generator = MinEvidenceRequestGenerator(guidance={})
        requests = generator.generate_requests([])
        assert requests == []

    def test_assessable_results_are_filtered_out(self):
        assessable = _make_assessable("R_PASS")
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([assessable])

        assert requests == []

    def test_mixed_list_only_includes_not_assessable(self):
        req = _make_requirement("building_height", ["elevation_drawing"])
        not_assessable = _make_not_assessable("R_FAIL", [req])
        assessable = _make_assessable("R_PASS")
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([not_assessable, assessable])

        assert len(requests) == 1
        assert requests[0].rule_id == "R_FAIL"

    def test_multiple_not_assessable_rules_all_included(self):
        req1 = _make_requirement("building_height", ["elevation_drawing"])
        req2 = _make_requirement("zone_category", ["zoning_certificate"])
        result1 = _make_not_assessable("R001", [req1])
        result2 = _make_not_assessable("R002", [req2])
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result1, result2])

        assert len(requests) == 2
        rule_ids = {r.rule_id for r in requests}
        assert rule_ids == {"R001", "R002"}


class TestMinEvidenceRequestGeneratorFromYaml:
    """from_yaml classmethod loads guidance from a YAML file."""

    def test_from_yaml_loads_guidance(self, tmp_path):
        yaml_path = tmp_path / "guidance.yaml"
        guidance_data = {
            "building_height": "Provide a dimensioned elevation drawing.",
            "rear_garden_depth": "Provide a dimensioned site plan.",
        }
        yaml_path.write_text(yaml.dump(guidance_data))

        generator = MinEvidenceRequestGenerator.from_yaml(yaml_path)

        req = _make_requirement("building_height", ["elevation_drawing"])
        result = _make_not_assessable("R001", [req])
        requests = generator.generate_requests([result])

        assert requests[0].missing[0].guidance == "Provide a dimensioned elevation drawing."

    def test_from_yaml_all_keys_available(self, tmp_path):
        yaml_path = tmp_path / "guidance.yaml"
        guidance_data = {
            "building_height": "Guidance A",
            "rear_garden_depth": "Guidance B",
            "site_coverage": "Guidance C",
            "zone_category": "Guidance D",
        }
        yaml_path.write_text(yaml.dump(guidance_data))

        generator = MinEvidenceRequestGenerator.from_yaml(yaml_path)

        for attr, expected_text in guidance_data.items():
            req = _make_requirement(attr, ["some_doc"])
            result = _make_not_assessable("R001", [req])
            requests = generator.generate_requests([result])
            assert requests[0].missing[0].guidance == expected_text

    def test_from_yaml_unknown_attribute_still_falls_back(self, tmp_path):
        yaml_path = tmp_path / "guidance.yaml"
        yaml_path.write_text(yaml.dump({"building_height": "Some guidance."}))

        generator = MinEvidenceRequestGenerator.from_yaml(yaml_path)

        req = _make_requirement("unknown_attr", ["doc"])
        result = _make_not_assessable("R001", [req])
        requests = generator.generate_requests([result])

        assert "unknown_attr" in requests[0].missing[0].guidance


class TestMinEvidenceRequestGeneratorReturnType:
    """Return values conform to EvidenceRequest / MissingEvidence schemas."""

    def test_returns_list_of_evidence_request_instances(self):
        req = _make_requirement("building_height", ["elevation_drawing"])
        result = _make_not_assessable("R001", [req])
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result])

        assert isinstance(requests, list)
        assert all(isinstance(r, EvidenceRequest) for r in requests)

    def test_missing_items_are_missing_evidence_instances(self):
        req = _make_requirement("building_height", ["elevation_drawing"])
        result = _make_not_assessable("R001", [req])
        generator = MinEvidenceRequestGenerator(guidance={})

        requests = generator.generate_requests([result])

        assert all(isinstance(m, MissingEvidence) for m in requests[0].missing)
