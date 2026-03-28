"""Naive baseline runner for ablation study.

Bypasses the full pipeline — sends all rule descriptions in a single LLM call
and parses the response as a batch of PASS/FAIL verdicts. Used as the lower-
bound comparison point when measuring the value added by the structured
extraction and reasoning pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from planproof.schemas.rules import RuleConfig, RuleOutcome, RuleVerdict

logger = logging.getLogger(__name__)


class NaiveBaselineRunner:
    """Single-shot LLM baseline — no structured extraction, no graph, no
    assessability gating.

    All rules are evaluated in one prompt; the model is expected to return a
    JSON object with a ``verdicts`` list.  Outcomes are forced to PASS or FAIL;
    NOT_ASSESSABLE is never emitted by this runner.
    """

    def __init__(self, llm_client: Any, rules: list[RuleConfig]) -> None:
        self._llm = llm_client
        self._rules = rules

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, extracted_text: str) -> list[RuleVerdict]:
        """Evaluate all rules against *extracted_text* in a single LLM call.

        Returns an empty list when no rules are configured.  On parse failure,
        returns a FAIL verdict for every rule with an error explanation.
        """
        if not self._rules:
            return []

        prompt = self._build_prompt(extracted_text)
        raw = self._llm.complete(prompt)

        try:
            return self._parse_response(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("NaiveBaselineRunner: failed to parse LLM response: %s", exc)
            return self._fail_all(f"LLM response could not be parsed: {exc}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, extracted_text: str) -> str:
        rule_lines: list[str] = []
        for rule in self._rules:
            threshold = rule.parameters.get("threshold", "N/A")
            rule_lines.append(
                f"- rule_id: {rule.rule_id}\n"
                f"  description: {rule.description}\n"
                f"  threshold: {threshold}"
            )
        rules_block = "\n".join(rule_lines)

        return (
            "Given this planning application text, evaluate each of these rules. "
            "For each rule, respond PASS or FAIL with a brief explanation.\n\n"
            f"Planning application text:\n{extracted_text}\n\n"
            f"Rules to evaluate:\n{rules_block}\n\n"
            "Respond with JSON only, in this exact format:\n"
            '{"verdicts": ['
            '{"rule_id": "R001", "outcome": "PASS", "explanation": "..."}, '
            "...]}"
        )

    def _parse_response(self, raw: str) -> list[RuleVerdict]:
        data = json.loads(raw)
        verdict_items: list[dict[str, Any]] = data["verdicts"]

        # Index parsed verdicts by rule_id for lookup
        parsed: dict[str, dict[str, Any]] = {
            item["rule_id"]: item for item in verdict_items
        }

        verdicts: list[RuleVerdict] = []
        for rule in self._rules:
            item = parsed.get(rule.rule_id)
            if item is None:
                # Rule was not included in the response — treat as FAIL
                verdicts.append(
                    RuleVerdict(
                        rule_id=rule.rule_id,
                        outcome=RuleOutcome.FAIL,
                        evidence_used=[],
                        explanation=f"Rule {rule.rule_id} was absent from LLM response.",
                        evaluated_value=None,
                        threshold=rule.parameters.get("threshold"),
                    )
                )
                continue

            raw_outcome = str(item.get("outcome", "")).upper()
            outcome = (
                RuleOutcome.PASS if raw_outcome == "PASS" else RuleOutcome.FAIL
            )
            verdicts.append(
                RuleVerdict(
                    rule_id=rule.rule_id,
                    outcome=outcome,
                    evidence_used=[],
                    explanation=item.get("explanation", ""),
                    evaluated_value=None,
                    threshold=rule.parameters.get("threshold"),
                )
            )

        return verdicts

    def _fail_all(self, error_explanation: str) -> list[RuleVerdict]:
        return [
            RuleVerdict(
                rule_id=rule.rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=[],
                explanation=error_explanation,
                evaluated_value=None,
                threshold=rule.parameters.get("threshold"),
            )
            for rule in self._rules
        ]
