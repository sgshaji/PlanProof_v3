"""Unit tests for ThresholdConfidenceGate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from planproof.reasoning.confidence import ThresholdConfidenceGate
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod


def _make_entity(
    method: ExtractionMethod,
    entity_type: EntityType,
    confidence: float,
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        value="test",
        confidence=confidence,
        source_document="doc.pdf",
        extraction_method=method,
        timestamp=datetime.now(UTC),
    )


THRESHOLDS: dict[str, dict[str, float]] = {
    "OCR_LLM": {"MEASUREMENT": 0.80, "ADDRESS": 0.85},
    "VLM_ZEROSHOT": {"MEASUREMENT": 0.70},
}


class TestIsTrustworthy:
    def test_above_threshold_is_trustworthy(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        entity = _make_entity(ExtractionMethod.OCR_LLM, EntityType.MEASUREMENT, 0.90)
        assert gate.is_trustworthy(entity) is True

    def test_below_threshold_is_not_trustworthy(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        entity = _make_entity(ExtractionMethod.OCR_LLM, EntityType.MEASUREMENT, 0.75)
        assert gate.is_trustworthy(entity) is False

    def test_exactly_at_threshold_is_trustworthy(self) -> None:
        """Threshold comparison is >=, so exact match should pass."""
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        entity = _make_entity(ExtractionMethod.OCR_LLM, EntityType.MEASUREMENT, 0.80)
        assert gate.is_trustworthy(entity) is True

    def test_missing_method_defaults_to_trustworthy(self) -> None:
        """When the extraction method is not in thresholds, default to trusted."""
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        entity = _make_entity(ExtractionMethod.MANUAL, EntityType.MEASUREMENT, 0.10)
        assert gate.is_trustworthy(entity) is True

    def test_missing_entity_type_defaults_to_trustworthy(self) -> None:
        """When entity_type is absent for a known method, default to trusted."""
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        # CERTIFICATE is not in OCR_LLM thresholds above
        entity = _make_entity(ExtractionMethod.OCR_LLM, EntityType.CERTIFICATE, 0.10)
        assert gate.is_trustworthy(entity) is True

    def test_vlm_zeroshot_above_threshold(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        entity = _make_entity(
            ExtractionMethod.VLM_ZEROSHOT, EntityType.MEASUREMENT, 0.75
        )
        assert gate.is_trustworthy(entity) is True

    def test_vlm_zeroshot_below_threshold(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        entity = _make_entity(
            ExtractionMethod.VLM_ZEROSHOT, EntityType.MEASUREMENT, 0.65
        )
        assert gate.is_trustworthy(entity) is False


class TestFilterTrusted:
    def test_keeps_high_confidence_removes_low_confidence(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        high = _make_entity(ExtractionMethod.OCR_LLM, EntityType.MEASUREMENT, 0.90)
        low = _make_entity(ExtractionMethod.OCR_LLM, EntityType.MEASUREMENT, 0.50)
        result = gate.filter_trusted([high, low])
        assert result == [high]

    def test_empty_input_returns_empty(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        assert gate.filter_trusted([]) == []

    def test_all_trusted_returns_all(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        e1 = _make_entity(ExtractionMethod.OCR_LLM, EntityType.MEASUREMENT, 0.95)
        e2 = _make_entity(ExtractionMethod.OCR_LLM, EntityType.ADDRESS, 0.92)
        result = gate.filter_trusted([e1, e2])
        assert result == [e1, e2]

    def test_none_trusted_returns_empty(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        low1 = _make_entity(ExtractionMethod.OCR_LLM, EntityType.MEASUREMENT, 0.10)
        low2 = _make_entity(ExtractionMethod.OCR_LLM, EntityType.ADDRESS, 0.20)
        assert gate.filter_trusted([low1, low2]) == []

    def test_unknown_method_always_passes_filter(self) -> None:
        gate = ThresholdConfidenceGate(thresholds=THRESHOLDS)
        manual = _make_entity(ExtractionMethod.MANUAL, EntityType.OWNERSHIP, 0.01)
        result = gate.filter_trusted([manual])
        assert result == [manual]


class TestFromYaml:
    def test_from_yaml_loads_thresholds(self, tmp_path: Path) -> None:
        yaml_content = """\
thresholds:
  OCR_LLM:
    ADDRESS: 0.85
    MEASUREMENT: 0.80
  VLM_ZEROSHOT:
    MEASUREMENT: 0.70
"""
        config_file = tmp_path / "thresholds.yaml"
        config_file.write_text(yaml_content)

        gate = ThresholdConfidenceGate.from_yaml(config_file)

        # Check a known threshold is applied correctly
        above = _make_entity(ExtractionMethod.OCR_LLM, EntityType.ADDRESS, 0.90)
        below = _make_entity(ExtractionMethod.OCR_LLM, EntityType.ADDRESS, 0.80)
        assert gate.is_trustworthy(above) is True
        assert gate.is_trustworthy(below) is False  # 0.80 < 0.85

    def test_from_yaml_vlm_threshold(self, tmp_path: Path) -> None:
        yaml_content = """\
thresholds:
  VLM_ZEROSHOT:
    MEASUREMENT: 0.70
"""
        config_file = tmp_path / "thresholds.yaml"
        config_file.write_text(yaml_content)

        gate = ThresholdConfidenceGate.from_yaml(config_file)

        at_threshold = _make_entity(
            ExtractionMethod.VLM_ZEROSHOT, EntityType.MEASUREMENT, 0.70
        )
        assert gate.is_trustworthy(at_threshold) is True
