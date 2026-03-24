"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from pathlib import Path

from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.pipeline.pipeline import Pipeline
from planproof.schemas.config import (
    AblationConfig,
    ConfidenceThresholds,
    PipelineConfig,
)


def _make_config() -> PipelineConfig:
    """Create a minimal PipelineConfig for testing."""
    return PipelineConfig(
        llm_provider="ollama",
        llm_model="llama3.1",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test",
        confidence=ConfidenceThresholds(thresholds={}),
        ablation=AblationConfig(),
    )


class _NoOpStep:
    """A step that does nothing — for testing the pipeline skeleton."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def execute(self, context: PipelineContext) -> StepResult:
        return {"success": True, "message": "ok"}


class _FailingStep:
    """A step that raises an exception — for testing error handling."""

    @property
    def name(self) -> str:
        return "failing_step"

    def execute(self, context: PipelineContext) -> StepResult:
        msg = "Intentional test failure"
        raise RuntimeError(msg)


class TestPipeline:
    def test_empty_pipeline_returns_report(self) -> None:
        """Pipeline with zero steps should return a valid empty report."""
        pipeline = Pipeline(config=_make_config())
        report = pipeline.run(input_dir=Path("nonexistent"))
        assert report.summary.total_rules == 0
        assert report.summary.passed == 0
        assert report.summary.failed == 0
        assert report.summary.not_assessable == 0

    def test_step_registration(self) -> None:
        pipeline = Pipeline(config=_make_config())
        pipeline.register(_NoOpStep("step_a"))
        pipeline.register(_NoOpStep("step_b"))
        assert len(pipeline._steps) == 2

    def test_steps_execute_in_order(self) -> None:
        """Steps should execute in registration order."""
        order: list[str] = []

        class _TrackingStep:
            def __init__(self, name: str) -> None:
                self._name = name

            @property
            def name(self) -> str:
                return self._name

            def execute(self, context: PipelineContext) -> StepResult:
                order.append(self._name)
                return {"success": True}

        pipeline = Pipeline(config=_make_config())
        pipeline.register(_TrackingStep("first"))
        pipeline.register(_TrackingStep("second"))
        pipeline.register(_TrackingStep("third"))
        pipeline.run(input_dir=Path("."))

        assert order == ["first", "second", "third"]

    def test_failing_step_does_not_crash_pipeline(self) -> None:
        """A step that raises should be caught; pipeline continues."""
        pipeline = Pipeline(config=_make_config())
        pipeline.register(_FailingStep())
        pipeline.register(_NoOpStep("after_failure"))

        # Should not raise
        report = pipeline.run(input_dir=Path("."))
        assert report is not None
