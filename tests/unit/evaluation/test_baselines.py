"""Tests for evaluation baseline runners."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from planproof.evaluation.baselines.strong import StrongBaselineRunner
from planproof.schemas.assessability import EvidenceRequirement
from planproof.schemas.rules import RuleConfig, RuleOutcome


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(
    rule_id: str = "R001",
    description: str = "Minimum front setback",
    threshold: float = 6.0,
    attribute: str = "front_setback",
) -> RuleConfig:
    return RuleConfig(
        rule_id=rule_id,
        description=description,
        policy_source="LEP 2012 s4.3",
        evaluation_type="numeric_threshold",
        parameters={"threshold": threshold},
        required_evidence=[
            EvidenceRequirement(
                attribute=attribute,
                acceptable_sources=["DRAWING"],
                min_confidence=0.8,
            )
        ],
    )


def _llm_response(
    verdict: str = "PASS",
    evidence_cited: list[str] | None = None,
    evaluated_value: Any = 7.5,
    explanation: str = "Value meets threshold.",
) -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "evidence_cited": evidence_cited or ["Front setback is 7.5m"],
            "evaluated_value": evaluated_value,
            "explanation": explanation,
        }
    )


# ---------------------------------------------------------------------------
# StrongBaselineRunner
# ---------------------------------------------------------------------------


class TestStrongBaselineRunner:
    def test_valid_per_rule_responses_produce_correct_verdicts(self) -> None:
        """Mock LLM returns valid per-rule responses → correct verdicts."""
        rules = [_rule("R001"), _rule("R002", description="Max height", threshold=9.0)]
        llm = MagicMock()
        llm.complete.side_effect = [
            _llm_response("PASS", evaluated_value=7.5),
            _llm_response("FAIL", evaluated_value=10.0, explanation="Exceeds max."),
        ]

        runner = StrongBaselineRunner(llm_client=llm, rules=rules)
        verdicts = runner.run(extracted_text="Front setback: 7.5m. Height: 10m.")

        assert len(verdicts) == 2
        assert verdicts[0].rule_id == "R001"
        assert verdicts[0].outcome == RuleOutcome.PASS
        assert verdicts[1].rule_id == "R002"
        assert verdicts[1].outcome == RuleOutcome.FAIL

    def test_makes_n_llm_calls_for_n_rules(self) -> None:
        """One LLM call per rule, not one call for all rules."""
        rules = [_rule("R001"), _rule("R002"), _rule("R003")]
        llm = MagicMock()
        llm.complete.return_value = _llm_response()

        runner = StrongBaselineRunner(llm_client=llm, rules=rules)
        runner.run(extracted_text="some application text")

        assert llm.complete.call_count == 3

    def test_evidence_cited_included_in_explanation(self) -> None:
        """evidence_cited quotes from LLM response are folded into explanation."""
        rules = [_rule("R001")]
        llm = MagicMock()
        llm.complete.return_value = _llm_response(
            evidence_cited=["setback is 7.5 metres from front boundary"],
            explanation="Meets minimum.",
        )

        runner = StrongBaselineRunner(llm_client=llm, rules=rules)
        verdicts = runner.run(extracted_text="setback is 7.5 metres from front boundary")

        assert len(verdicts) == 1
        assert "setback is 7.5 metres from front boundary" in verdicts[0].explanation

    def test_parsing_failure_produces_fail_verdict(self) -> None:
        """If LLM returns unparseable JSON, verdict is FAIL with error explanation."""
        rules = [_rule("R001")]
        llm = MagicMock()
        llm.complete.return_value = "This is not valid JSON at all."

        runner = StrongBaselineRunner(llm_client=llm, rules=rules)
        verdicts = runner.run(extracted_text="some text")

        assert len(verdicts) == 1
        assert verdicts[0].rule_id == "R001"
        assert verdicts[0].outcome == RuleOutcome.FAIL
        assert "parse" in verdicts[0].explanation.lower() or "error" in verdicts[0].explanation.lower()

    def test_empty_rules_returns_empty_verdicts(self) -> None:
        """No rules → no LLM calls, empty verdict list."""
        llm = MagicMock()
        runner = StrongBaselineRunner(llm_client=llm, rules=[])
        verdicts = runner.run(extracted_text="some text")

        assert verdicts == []
        llm.complete.assert_not_called()

    def test_prompt_contains_rule_context(self) -> None:
        """LLM prompt includes rule_id, description, threshold, and required evidence attributes."""
        rules = [_rule("R001", description="Minimum front setback", threshold=6.0, attribute="front_setback")]
        llm = MagicMock()
        llm.complete.return_value = _llm_response()

        runner = StrongBaselineRunner(llm_client=llm, rules=rules)
        runner.run(extracted_text="Front setback: 7.5m.")

        prompt = llm.complete.call_args[0][0]
        assert "R001" in prompt
        assert "Minimum front setback" in prompt
        assert "6.0" in prompt or "6" in prompt
        assert "front_setback" in prompt

    def test_evaluated_value_preserved_in_verdict(self) -> None:
        """evaluated_value from LLM response is stored on the verdict."""
        rules = [_rule("R001")]
        llm = MagicMock()
        llm.complete.return_value = _llm_response(evaluated_value=7.5)

        runner = StrongBaselineRunner(llm_client=llm, rules=rules)
        verdicts = runner.run(extracted_text="Front setback: 7.5m.")

        assert verdicts[0].evaluated_value == 7.5

    def test_all_verdicts_are_pass_or_fail_never_not_assessable(self) -> None:
        """Strong baseline never emits NOT_ASSESSABLE — always forces PASS or FAIL."""
        rules = [_rule("R001"), _rule("R002")]
        llm = MagicMock()
        llm.complete.side_effect = [
            _llm_response("PASS"),
            "bad json",
        ]

        runner = StrongBaselineRunner(llm_client=llm, rules=rules)
        verdicts = runner.run(extracted_text="some text")

        for v in verdicts:
            assert v.outcome in (RuleOutcome.PASS, RuleOutcome.FAIL)
