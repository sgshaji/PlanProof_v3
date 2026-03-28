"""Tests for GraphPopulationStep."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from planproof.interfaces.pipeline import PipelineContext
from planproof.pipeline.steps.graph_population import GraphPopulationStep
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod


@pytest.fixture()
def mock_populator() -> MagicMock:
    """Create a mock EntityPopulator."""
    return MagicMock()


@pytest.fixture()
def sample_entities() -> list[ExtractedEntity]:
    """Create sample extracted entities for testing."""
    return [
        ExtractedEntity(
            entity_type=EntityType.ZONE,
            value="R2 Zone",
            confidence=0.95,
            source_document="test_doc.pdf",
            source_page=1,
            extraction_method=ExtractionMethod.VLM_STRUCTURED,
            timestamp=datetime.now(),
        ),
        ExtractedEntity(
            entity_type=EntityType.ADDRESS,
            value="123 Main Street",
            confidence=0.88,
            source_document="test_doc.pdf",
            source_page=1,
            extraction_method=ExtractionMethod.OCR_LLM,
            timestamp=datetime.now(),
        ),
    ]


@pytest.fixture()
def reference_dir(tmp_path: Path) -> Path:
    """Create a mock reference directory."""
    ref_dir = tmp_path / "reference_data"
    ref_dir.mkdir()
    (ref_dir / "parcel.geojson").write_text("{}")
    (ref_dir / "zone.json").write_text("{}")
    return ref_dir


class TestGraphPopulationStep:
    """Test suite for GraphPopulationStep."""

    def test_populates_graph_with_entities(
        self, mock_populator: MagicMock, sample_entities: list[ExtractedEntity]
    ) -> None:
        """Test that populate_from_entities is called with entities."""
        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {"entities": sample_entities}

        result = step.execute(context)

        mock_populator.populate_from_entities.assert_called_once_with(sample_entities)
        assert result["success"] is True

    def test_sets_graph_ref_in_context(
        self, mock_populator: MagicMock, sample_entities: list[ExtractedEntity]
    ) -> None:
        """Test that context["graph_ref"] is set to the populator."""
        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {"entities": sample_entities}

        result = step.execute(context)

        assert context["graph_ref"] is mock_populator
        assert result["success"] is True

    def test_succeeds_with_empty_entities(self, mock_populator: MagicMock) -> None:
        """Test that the step succeeds with an empty entities list."""
        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {"entities": []}

        result = step.execute(context)

        mock_populator.populate_from_entities.assert_called_once_with([])
        assert result["success"] is True
        assert context["graph_ref"] is mock_populator

    def test_handles_missing_entities_key(self, mock_populator: MagicMock) -> None:
        """Test that missing 'entities' key defaults to empty list."""
        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {}

        result = step.execute(context)

        mock_populator.populate_from_entities.assert_called_once_with([])
        assert result["success"] is True

    def test_loads_reference_data_when_available(
        self,
        mock_populator: MagicMock,
        sample_entities: list[ExtractedEntity],
        reference_dir: Path,
    ) -> None:
        """Test that reference data is loaded when metadata has reference_dir."""
        # Set up the populator to have load_reference_data method
        mock_populator.load_reference_data = MagicMock()

        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {
            "entities": sample_entities,
            "metadata": {"reference_dir": str(reference_dir)},
        }

        result = step.execute(context)

        # Verify load_reference_data was called with the reference_dir path
        mock_populator.load_reference_data.assert_called_once_with(
            reference_dir, reference_dir
        )
        # Verify populate_from_entities was still called
        mock_populator.populate_from_entities.assert_called_once_with(sample_entities)
        assert result["success"] is True

    def test_skips_reference_data_when_no_method(
        self, mock_populator: MagicMock, sample_entities: list[ExtractedEntity]
    ) -> None:
        """Test that reference data loading is skipped if populator lacks the method."""
        # Ensure load_reference_data doesn't exist (it won't in a mock by default)
        delattr(mock_populator, "load_reference_data")

        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {
            "entities": sample_entities,
            "metadata": {"reference_dir": "/some/path"},
        }

        result = step.execute(context)

        # Should still populate entities
        mock_populator.populate_from_entities.assert_called_once_with(sample_entities)
        assert result["success"] is True

    def test_skips_reference_data_when_no_metadata(
        self, mock_populator: MagicMock, sample_entities: list[ExtractedEntity]
    ) -> None:
        """Test that reference data loading is skipped if metadata is missing."""
        mock_populator.load_reference_data = MagicMock()

        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {"entities": sample_entities}

        result = step.execute(context)

        # load_reference_data should not be called
        mock_populator.load_reference_data.assert_not_called()
        # But populate_from_entities should be called
        mock_populator.populate_from_entities.assert_called_once_with(sample_entities)
        assert result["success"] is True

    def test_skips_reference_data_when_no_reference_dir_key(
        self, mock_populator: MagicMock, sample_entities: list[ExtractedEntity]
    ) -> None:
        """Test that reference data loading is skipped if metadata lacks
        reference_dir key."""
        mock_populator.load_reference_data = MagicMock()

        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {
            "entities": sample_entities,
            "metadata": {"other_key": "value"},
        }

        result = step.execute(context)

        # load_reference_data should not be called
        mock_populator.load_reference_data.assert_not_called()
        # But populate_from_entities should be called
        mock_populator.populate_from_entities.assert_called_once_with(sample_entities)
        assert result["success"] is True

    def test_returns_correct_step_result_format(
        self, mock_populator: MagicMock, sample_entities: list[ExtractedEntity]
    ) -> None:
        """Test that the result has correct structure and entity_count."""
        step = GraphPopulationStep(mock_populator)
        context: PipelineContext = {"entities": sample_entities}

        result = step.execute(context)

        assert "success" in result
        assert "message" in result
        assert "artifacts" in result
        assert result["artifacts"]["entity_count"] == len(sample_entities)

    def test_step_name_property(self, mock_populator: MagicMock) -> None:
        """Test that the step name is correctly set."""
        step = GraphPopulationStep(mock_populator)
        assert step.name == "graph_population"
