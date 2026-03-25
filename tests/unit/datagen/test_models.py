"""Tests for datagen scenario models — immutability and construction."""
from __future__ import annotations

import pytest

from planproof.datagen.scenario.models import (
    DocumentSpec,
    Scenario,
    Value,
    Verdict,
)


class TestValue:
    def test_creation(self) -> None:
        v = Value(
            attribute="building_height", value=7.5, unit="metres", display_text="7.5m"
        )
        assert v.attribute == "building_height"
        assert v.value == 7.5
        assert v.display_text == "7.5m"

    def test_frozen(self) -> None:
        v = Value(attribute="x", value=1.0, unit="m", display_text="1m")
        with pytest.raises(AttributeError):
            v.value = 2.0  # type: ignore[misc]


class TestVerdict:
    def test_creation(self) -> None:
        v = Verdict(rule_id="R001", outcome="PASS", evaluated_value=7.5, threshold=8.0)
        assert v.outcome == "PASS"


class TestDocumentSpec:
    def test_creation(self) -> None:
        ds = DocumentSpec(
            doc_type="FORM",
            file_format="pdf",
            values_to_place=("building_height", "site_address"),
        )
        assert ds.doc_type == "FORM"
        assert len(ds.values_to_place) == 2


class TestScenario:
    def test_creation(self) -> None:
        s = Scenario(
            set_id="SET_C001",
            category="compliant",
            seed=42,
            profile_id="standard_3file",
            difficulty="medium",
            degradation_preset="moderate_scan",
            values=(Value(attribute="h", value=7.5, unit="m", display_text="7.5m"),),
            verdicts=(
                Verdict(
                    rule_id="R001", outcome="PASS", evaluated_value=7.5, threshold=8.0
                ),
            ),
            documents=(
                DocumentSpec(
                    doc_type="FORM", file_format="pdf", values_to_place=("h",)
                ),
            ),
            edge_case_strategy=None,
        )
        assert s.set_id == "SET_C001"
        assert s.edge_case_strategy is None

    def test_frozen(self) -> None:
        s = Scenario(
            set_id="X", category="compliant", seed=1, profile_id="p",
            difficulty="low", degradation_preset="clean",
            values=(), verdicts=(), documents=(), edge_case_strategy=None,
        )
        with pytest.raises(AttributeError):
            s.seed = 99  # type: ignore[misc]
