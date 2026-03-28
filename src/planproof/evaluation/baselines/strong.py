"""Strong baseline: per-rule chain-of-thought LLM evaluation.

This baseline makes one LLM call per rule with a structured CoT prompt.
It is stronger than a naive single-call baseline because it focuses the
model's attention on one rule at a time, but it still has no pipeline
architecture (no structured extraction, no reconciliation, no confidence
gating).

The key characteristic of all baselines: every verdict is PASS or FAIL.
NOT_ASSESSABLE is never emitted — the strong baseline shows the ceiling of
what a lone LLM can achieve when given one rule at a time.
"""
from __future__ import annotations

import json
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.schemas.rules import RuleConfig, RuleOutcome, RuleVerdict

logger = get_logger(__name__)

_COT_TEMPLATE = """\
You are evaluating planning rule {rule_id}: {description}.
Threshold: {threshold}.
Required evidence: {required_evidence}.

Application text:
{extracted_text}

Think step by step:
1. Identify relevant evidence in the text
2. Extract the specific value for {attribute}
3. Compare against the threshold
4. Provide your verdict

Respond with JSON:
{{"verdict": "PASS" or "FAIL", "evidence_cited": ["quoted text..."], "evaluated_value": ..., "explanation": "..."}}\
"""


class StrongBaselineRunner:
    """Evaluate planning rules with per-rule chain-of-thought LLM calls.

    One LLM call is made per rule so the model can focus on a single policy
    requirement at a time.  Parsing failures default to FAIL so that the
    baseline never silently drops a rule.
    """

    def __init__(self, llm_client: Any, rules: list[RuleConfig]) -> None:
        self._llm = llm_client
        self._rules = rules

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, extracted_text: str) -> list[RuleVerdict]:
        """Evaluate all rules and return one RuleVerdict per rule.

        Each rule is evaluated independently via a separate LLM call.
        All returned verdicts are either PASS or FAIL — NOT_ASSESSABLE is
        never emitted.
        """
        verdicts: list[RuleVerdict] = []
        for rule in self._rules:
            verdict = self._evaluate_rule(rule, extracted_text)
            verdicts.append(verdict)
        return verdicts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_rule(self, rule: RuleConfig, extracted_text: str) -> RuleVerdict:
        prompt = self._build_prompt(rule, extracted_text)
        raw = self._llm.complete(prompt)
        return self._parse_response(raw, rule)

    def _build_prompt(self, rule: RuleConfig, extracted_text: str) -> str:
        threshold = rule.parameters.get("threshold", rule.parameters)
        attributes = ", ".join(req.attribute for req in rule.required_evidence)
        # Use the first required attribute for the targeted extraction step;
        # fall back to the rule_id if no evidence requirements are declared.
        primary_attribute = (
            rule.required_evidence[0].attribute if rule.required_evidence else rule.rule_id
        )
        required_evidence_desc = "; ".join(
            f"{req.attribute} (sources: {', '.join(req.acceptable_sources)})"
            for req in rule.required_evidence
        ) or "none specified"

        return _COT_TEMPLATE.format(
            rule_id=rule.rule_id,
            description=rule.description,
            threshold=threshold,
            required_evidence=required_evidence_desc,
            extracted_text=extracted_text,
            attribute=primary_attribute,
        )

    def _parse_response(self, raw: str, rule: RuleConfig) -> RuleVerdict:
        try:
            data = json.loads(raw)
            verdict_str: str = data["verdict"]
            outcome = RuleOutcome.PASS if verdict_str == "PASS" else RuleOutcome.FAIL
            evidence_cited: list[str] = data.get("evidence_cited", [])
            evaluated_value: Any = data.get("evaluated_value")
            base_explanation: str = data.get("explanation", "")

            # Fold evidence citations into the explanation so callers have
            # a single string containing everything the LLM said.
            if evidence_cited:
                citations = "; ".join(f'"{q}"' for q in evidence_cited)
                explanation = f"{base_explanation} Evidence cited: {citations}"
            else:
                explanation = base_explanation

            threshold = rule.parameters.get("threshold")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "strong_baseline_parse_error",
                rule_id=rule.rule_id,
                error=str(exc),
            )
            return RuleVerdict(
                rule_id=rule.rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=[],
                explanation=f"Failed to parse LLM response: {exc}",
                evaluated_value=None,
                threshold=rule.parameters.get("threshold"),
            )

        return RuleVerdict(
            rule_id=rule.rule_id,
            outcome=outcome,
            evidence_used=[],
            explanation=explanation,
            evaluated_value=evaluated_value,
            threshold=threshold,
        )
