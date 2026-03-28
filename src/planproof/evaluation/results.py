"""Experiment result data models and JSON I/O.

Stores the outcome of running a pipeline configuration against a test set, one
file per (config_name, set_id) pair.  Designed for resumable batch experiments:
check result_exists() before running to skip already-completed combinations.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel


class RuleResult(BaseModel):
    """Outcome of evaluating a single rule in an experiment run."""

    rule_id: str
    ground_truth_outcome: Literal["PASS", "FAIL"]
    predicted_outcome: Literal["PASS", "FAIL", "NOT_ASSESSABLE"]
    config_name: str
    set_id: str


class ExperimentResult(BaseModel):
    """Full result of running one pipeline configuration against one test set."""

    config_name: str
    set_id: str
    rule_results: list[RuleResult]
    metadata: dict[str, Any]
    timestamp: datetime


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def save_result(result: ExperimentResult, output_dir: Path) -> Path:
    """Write *result* to ``output_dir/{config_name}/{set_id}.json``.

    Creates intermediate directories as needed.  Returns the path written.
    """
    dest = output_dir / result.config_name / f"{result.set_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return dest


def load_result(path: Path) -> ExperimentResult:
    """Read a single ExperimentResult from *path*."""
    return ExperimentResult.model_validate_json(path.read_text(encoding="utf-8"))


def load_all_results(results_dir: Path) -> list[ExperimentResult]:
    """Recursively load every ``.json`` file under *results_dir*.

    Returns an empty list when the directory is empty or does not exist.
    """
    if not results_dir.exists():
        return []
    return [load_result(p) for p in sorted(results_dir.rglob("*.json"))]


def result_exists(config_name: str, set_id: str, output_dir: Path) -> bool:
    """Return True if the result file for *(config_name, set_id)* already exists."""
    return (output_dir / config_name / f"{set_id}.json").exists()
