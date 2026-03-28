"""Tests for evaluation baseline runners."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from planproof.evaluation.baselines.naive import NaiveBaselineRunner
from planproof.schemas.assessability import EvidenceRequirement
from planproof.schemas.rules import RuleConfig, RuleOutcome


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(
    rule_id: str = "R001",
    description: str = "Building height must not exceed 8.5 m",
    threshold: float = 8.5,
) -> RuleConfig:
    return RuleConfig(
        rule_id=rule_id,
        description=description,
        policy_source="LPS-2023 cl.4.2",
        evaluation_type="numeric_threshold",
        parameters={"threshold": threshold, "operator": "<="},
        required_evidence=[],
    )


def _valid_response(*verdicts: dict) -> str:
    return json.dumps({"verdicts": list(verdicts)})


def _mock_llm(response: str) -> MagicMock:
    client = MagicMock()
    client.complete.return_value = response
    return client


# ---------------------------------------------------------------------------
# NaiveBaselineRunner — happy path: valid JSON response
# ---------------------------------------------------------------------------


class TestNaiveBaselineRunnerValidResponse:
    def test_returns_correct_number_of_verdicts(self) -> None:
        """Mock LLM returns valid JSON → correct verdicts parsed."""
        rules = [_rule("R001"), _rule("R002", threshold=3.0)]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "PASS", "explanation": "Height is 7 m."},
            {"rule_id": "R002", "outcome": "FAIL", "explanation": "Exceeds limit."},
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("some planning text")
        assert len(verdicts) == 2

    def test_pass_verdict_parsed_correctly(self) -> None:
        """PASS outcome and explanation are populated from JSON response."""
        rules = [_rule("R001")]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "PASS", "explanation": "Compliant."}
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        assert verdicts[0].outcome == RuleOutcome.PASS
        assert verdicts[0].rule_id == "R001"
        assert verdicts[0].explanation == "Compliant."

    def test_fail_verdict_parsed_correctly(self) -> None:
        """FAIL outcome is correctly parsed."""
        rules = [_rule("R001")]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "FAIL", "explanation": "Non-compliant."}
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        assert verdicts[0].outcome == RuleOutcome.FAIL

    def test_verdict_order_matches_rules_order(self) -> None:
        """Verdicts are returned in rule definition order, not LLM response order."""
        rules = [_rule("R001"), _rule("R002", threshold=3.0)]
        # Response in reverse order
        response = _valid_response(
            {"rule_id": "R002", "outcome": "FAIL", "explanation": "Bad."},
            {"rule_id": "R001", "outcome": "PASS", "explanation": "Good."},
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        assert verdicts[0].rule_id == "R001"
        assert verdicts[1].rule_id == "R002"

    def test_threshold_populated_from_rule_parameters(self) -> None:
        """threshold on the verdict is sourced from rule parameters, not LLM."""
        rules = [_rule("R001", threshold=8.5)]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "PASS", "explanation": "OK."}
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        assert verdicts[0].threshold == 8.5

    def test_evidence_used_is_always_empty_list(self) -> None:
        """Naive runner has no structured extraction — evidence_used is always []."""
        rules = [_rule("R001")]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "PASS", "explanation": "OK."}
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        assert verdicts[0].evidence_used == []


# ---------------------------------------------------------------------------
# NaiveBaselineRunner — all verdicts are PASS or FAIL (no NOT_ASSESSABLE)
# ---------------------------------------------------------------------------


class TestNaiveBaselineNoNotAssessable:
    def test_all_outcomes_pass_or_fail_on_valid_response(self) -> None:
        """All verdicts are PASS or FAIL — NOT_ASSESSABLE is never emitted."""
        rules = [_rule("R001"), _rule("R002", threshold=3.0)]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "PASS", "explanation": "Fine."},
            {"rule_id": "R002", "outcome": "FAIL", "explanation": "Bad."},
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        for v in verdicts:
            assert v.outcome in (RuleOutcome.PASS, RuleOutcome.FAIL)

    def test_all_outcomes_fail_on_parse_error(self) -> None:
        """Parse error → all outcomes are FAIL, never NOT_ASSESSABLE."""
        rules = [_rule("R001"), _rule("R002", threshold=3.0)]
        runner = NaiveBaselineRunner(_mock_llm("not json at all"), rules)
        verdicts = runner.run("text")
        for v in verdicts:
            assert v.outcome == RuleOutcome.FAIL

    def test_unknown_outcome_string_maps_to_fail(self) -> None:
        """Unrecognised outcome strings (including NOT_ASSESSABLE) map to FAIL."""
        rules = [_rule("R001")]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "NOT_ASSESSABLE", "explanation": "N/A."}
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        assert verdicts[0].outcome == RuleOutcome.FAIL


# ---------------------------------------------------------------------------
# NaiveBaselineRunner — malformed LLM response → all FAIL with error explanation
# ---------------------------------------------------------------------------


class TestNaiveBaselineMalformedResponse:
    def test_invalid_json_returns_fail_for_all_rules(self) -> None:
        """Malformed LLM response → all FAIL with error explanation."""
        rules = [_rule("R001"), _rule("R002", threshold=3.0)]
        runner = NaiveBaselineRunner(_mock_llm("{bad json"), rules)
        verdicts = runner.run("text")
        assert len(verdicts) == 2
        assert all(v.outcome == RuleOutcome.FAIL for v in verdicts)

    def test_error_explanation_is_populated_on_parse_failure(self) -> None:
        """Explanation is non-empty on parse failure."""
        rules = [_rule("R001")]
        runner = NaiveBaselineRunner(_mock_llm("not json"), rules)
        verdicts = runner.run("text")
        assert verdicts[0].explanation != ""

    def test_missing_verdicts_key_returns_fail_for_all(self) -> None:
        """Wrong top-level key in JSON → all FAIL."""
        rules = [_rule("R001")]
        response = json.dumps({"results": []})
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        assert verdicts[0].outcome == RuleOutcome.FAIL

    def test_rule_absent_from_response_is_fail(self) -> None:
        """Rule missing from LLM response is given a FAIL verdict."""
        rules = [_rule("R001"), _rule("R002", threshold=3.0)]
        response = _valid_response(
            {"rule_id": "R001", "outcome": "PASS", "explanation": "OK."}
        )
        runner = NaiveBaselineRunner(_mock_llm(response), rules)
        verdicts = runner.run("text")
        r002 = next(v for v in verdicts if v.rule_id == "R002")
        assert r002.outcome == RuleOutcome.FAIL


# ---------------------------------------------------------------------------
# NaiveBaselineRunner — empty rules list → empty verdicts
# ---------------------------------------------------------------------------


class TestNaiveBaselineEmptyRules:
    def test_empty_rules_returns_empty_list(self) -> None:
        """Empty rules list → empty verdicts list."""
        runner = NaiveBaselineRunner(_mock_llm("irrelevant"), [])
        verdicts = runner.run("any text")
        assert verdicts == []

    def test_llm_not_called_when_no_rules(self) -> None:
        """LLM is not called when there are no rules to evaluate."""
        llm = _mock_llm("irrelevant")
        runner = NaiveBaselineRunner(llm, [])
        runner.run("any text")
        llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# NaiveBaselineRunner — prompt includes rule descriptions
# ---------------------------------------------------------------------------


class TestNaiveBaselinePromptContent:
    def _capture_prompt(self, rules: list[RuleConfig], text: str = "sample text") -> str:
        llm = MagicMock()
        llm.complete.return_value = _valid_response(
            *[{"rule_id": r.rule_id, "outcome": "PASS", "explanation": "ok"} for r in rules]
        )
        runner = NaiveBaselineRunner(llm, rules)
        runner.run(text)
        return llm.complete.call_args[0][0]

    def test_prompt_includes_rule_description(self) -> None:
        """Prompt includes each rule's description."""
        rule = _rule("R001", description="Height must not exceed 8.5 m")
        prompt = self._capture_prompt([rule])
        assert "Height must not exceed 8.5 m" in prompt

    def test_prompt_includes_rule_id(self) -> None:
        """Prompt includes the rule_id for each rule."""
        rule = _rule("R001")
        prompt = self._capture_prompt([rule])
        assert "R001" in prompt

    def test_prompt_includes_threshold(self) -> None:
        """Prompt includes the threshold value from rule parameters."""
        rule = _rule("R001", threshold=8.5)
        prompt = self._capture_prompt([rule])
        assert "8.5" in prompt

    def test_prompt_includes_extracted_text(self) -> None:
        """Prompt includes the planning application text."""
        rule = _rule("R001")
        prompt = self._capture_prompt([rule], text="THE UNIQUE PLANNING TEXT MARKER")
        assert "THE UNIQUE PLANNING TEXT MARKER" in prompt

    def test_prompt_includes_all_rules_when_multiple(self) -> None:
        """All rule descriptions appear in a single prompt (not N separate prompts)."""
        rules = [
            _rule("R001", description="Height limit"),
            _rule("R002", description="Setback requirement"),
        ]
        prompt = self._capture_prompt(rules)
        assert "Height limit" in prompt
        assert "Setback requirement" in prompt

    def test_single_llm_call_for_multiple_rules(self) -> None:
        """Naive baseline uses exactly one LLM call regardless of rule count."""
        rules = [_rule("R001"), _rule("R002"), _rule("R003")]
        llm = MagicMock()
        llm.complete.return_value = _valid_response(
            {"rule_id": "R001", "outcome": "PASS", "explanation": "ok"},
            {"rule_id": "R002", "outcome": "PASS", "explanation": "ok"},
            {"rule_id": "R003", "outcome": "PASS", "explanation": "ok"},
        )
        runner = NaiveBaselineRunner(llm, rules)
        runner.run("text")
        assert llm.complete.call_count == 1
