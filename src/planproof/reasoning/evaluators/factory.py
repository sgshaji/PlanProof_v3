"""Rule factory with evaluator registry.

Reads YAML rule definitions and produces configured ``RuleEvaluator``
instances.  New rule types require only a new evaluator class and one
line of registration -- existing evaluators are never modified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from planproof.interfaces.reasoning import RuleEvaluator
from planproof.schemas.assessability import EvidenceRequirement
from planproof.schemas.rules import RuleConfig


class RuleFactory:
    """Reads YAML rule definitions and produces configured RuleEvaluator instances.

    # DESIGN: OCP -- adding a new rule type requires only a new evaluator class
    # and one line of registration. Existing evaluators are never modified.
    """

    _registry: dict[str, type] = {}

    @classmethod
    def register_evaluator(cls, evaluation_type: str, evaluator_cls: type) -> None:
        """Register an evaluator class for a given evaluation type.

        Parameters
        ----------
        evaluation_type:
            The string that appears in rule YAML under ``evaluation_type``.
        evaluator_cls:
            The evaluator class to instantiate for rules of this type.
        """
        cls._registry[evaluation_type] = evaluator_cls

    def load_rules(self, rules_dir: Path) -> list[tuple[RuleConfig, RuleEvaluator]]:
        """Load all ``*.yaml`` rule files from *rules_dir*.

        Returns a list of (config, evaluator) pairs ready for the rule
        evaluation step.
        """
        results: list[tuple[RuleConfig, RuleEvaluator]] = []

        for yaml_path in sorted(rules_dir.glob("*.yaml")):
            with open(yaml_path) as f:
                raw: dict[str, Any] = yaml.safe_load(f)

            # Parse required_evidence into EvidenceRequirement instances
            evidence_reqs = [
                EvidenceRequirement(**req)
                for req in raw.get("required_evidence", [])
            ]

            params = raw.get("parameters", {})
            params["rule_id"] = raw["rule_id"]  # Inject so evaluators can report it

            config = RuleConfig(
                rule_id=raw["rule_id"],
                description=raw["description"],
                policy_source=raw["policy_source"],
                evaluation_type=raw["evaluation_type"],
                parameters=params,
                required_evidence=evidence_reqs,
            )

            evaluator = self.create_evaluator(config)
            results.append((config, evaluator))

        return results

    def create_evaluator(self, rule_config: RuleConfig) -> RuleEvaluator:
        """Instantiate the evaluator for *rule_config*'s evaluation type.

        Raises
        ------
        KeyError:
            If no evaluator is registered for the given ``evaluation_type``.
        """
        eval_type = rule_config.evaluation_type
        if eval_type not in self._registry:
            registered = ", ".join(sorted(self._registry)) or "(none)"
            raise KeyError(
                f"No evaluator registered for type {eval_type!r}. "
                f"Registered types: {registered}"
            )
        evaluator_cls = self._registry[eval_type]
        result: RuleEvaluator = evaluator_cls(rule_config.parameters)
        return result
