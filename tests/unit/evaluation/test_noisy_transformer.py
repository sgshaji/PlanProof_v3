"""Unit tests for NoisyEntityTransformer.

Tests cover the identity transform (no degradation), each degradation mode
individually, and determinism with a fixed seed.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from planproof.evaluation.noisy_transformer import DegradationConfig, NoisyEntityTransformer
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_entity(
    attribute: str = "building_height",
    value: float = 10.0,
    confidence: float = 1.0,
    entity_type: EntityType = EntityType.MEASUREMENT,
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        attribute=attribute,
        value=value,
        unit="m",
        confidence=confidence,
        source_document="DRAWING_test.pdf",
        source_page=1,
        source_region=None,
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=datetime.now(timezone.utc),
    )


def _make_entity_list(n: int = 5) -> list[ExtractedEntity]:
    attrs = ["building_height", "rear_garden_depth", "building_footprint_area",
             "total_site_area", "stated_site_area"]
    return [_make_entity(attribute=attrs[i % len(attrs)], value=float(i + 1)) for i in range(n)]


# ---------------------------------------------------------------------------
# test_no_degradation: identity transform
# ---------------------------------------------------------------------------


def test_no_degradation():
    """Zero-config transformer returns entities with identical field values."""
    cfg = DegradationConfig()
    transformer = NoisyEntityTransformer(cfg, seed=42)
    originals = _make_entity_list(5)
    result = transformer.transform(originals)

    assert len(result) == len(originals), "Entity count must be unchanged"
    for orig, noisy in zip(originals, result):
        assert noisy.value == orig.value, "Values must be unchanged with no noise"
        assert noisy.confidence == orig.confidence, "Confidence must be unchanged"
        assert noisy.attribute == orig.attribute, "Attributes must be unchanged"


# ---------------------------------------------------------------------------
# test_value_noise_changes_values
# ---------------------------------------------------------------------------


def test_value_noise_changes_values():
    """Value noise produces different numeric values but the count stays the same."""
    cfg = DegradationConfig(value_noise_pct=0.20)
    transformer = NoisyEntityTransformer(cfg, seed=42)
    originals = _make_entity_list(10)
    result = transformer.transform(originals)

    assert len(result) == len(originals), "Entity count must be unchanged after value noise"

    # At least some values should have changed (with 20% noise, very unlikely all are equal)
    changed = sum(1 for orig, noisy in zip(originals, result) if noisy.value != orig.value)
    assert changed > 0, "Expected at least one value to change with 20% noise"

    # All values must remain positive
    for entity in result:
        try:
            assert float(entity.value) > 0, f"Value must remain positive, got {entity.value}"
        except (TypeError, ValueError):
            pass  # Non-numeric values are left unchanged


# ---------------------------------------------------------------------------
# test_entity_dropout_removes_entities
# ---------------------------------------------------------------------------


def test_entity_dropout_removes_entities():
    """Entity dropout reduces the entity count."""
    cfg = DegradationConfig(entity_dropout_pct=0.50)
    transformer = NoisyEntityTransformer(cfg, seed=42)
    originals = _make_entity_list(10)
    result = transformer.transform(originals)

    assert len(result) < len(originals), "Dropout must remove entities"
    assert len(result) == 5, "50% dropout of 10 entities should yield 5"


def test_entity_dropout_zero_keeps_all():
    """Zero dropout leaves entity count unchanged."""
    cfg = DegradationConfig(entity_dropout_pct=0.0)
    transformer = NoisyEntityTransformer(cfg, seed=42)
    originals = _make_entity_list(8)
    result = transformer.transform(originals)
    assert len(result) == 8


# ---------------------------------------------------------------------------
# test_confidence_noise_changes_confidence
# ---------------------------------------------------------------------------


def test_confidence_noise_changes_confidence():
    """Confidence noise modifies confidence scores and keeps them in [0.01, 1.0]."""
    cfg = DegradationConfig(confidence_noise_std=0.30)
    transformer = NoisyEntityTransformer(cfg, seed=42)
    originals = _make_entity_list(20)
    result = transformer.transform(originals)

    assert len(result) == len(originals)

    # All confidence values must be in the valid range
    for entity in result:
        assert 0.01 <= entity.confidence <= 1.0, (
            f"Confidence {entity.confidence} outside [0.01, 1.0]"
        )

    # At least some confidence values should have changed
    changed = sum(1 for orig, noisy in zip(originals, result) if noisy.confidence != orig.confidence)
    assert changed > 0, "Expected at least one confidence score to change with noise_std=0.30"


# ---------------------------------------------------------------------------
# test_deterministic_with_seed
# ---------------------------------------------------------------------------


def test_deterministic_with_seed():
    """Two transformers with the same seed produce identical results."""
    cfg = DegradationConfig(
        value_noise_pct=0.10,
        entity_dropout_pct=0.20,
        confidence_noise_std=0.10,
    )
    originals = _make_entity_list(10)

    transformer_a = NoisyEntityTransformer(cfg, seed=99)
    transformer_b = NoisyEntityTransformer(cfg, seed=99)

    result_a = transformer_a.transform(originals)
    result_b = transformer_b.transform(originals)

    assert len(result_a) == len(result_b), "Deterministic seed must produce same length"
    for a, b in zip(result_a, result_b):
        assert a.value == b.value, "Values must match with same seed"
        assert a.confidence == b.confidence, "Confidence must match with same seed"
        assert a.attribute == b.attribute, "Attributes must match with same seed"


def test_different_seeds_give_different_results():
    """Different seeds produce different noisy outputs."""
    cfg = DegradationConfig(value_noise_pct=0.20)
    originals = _make_entity_list(10)

    result_42 = NoisyEntityTransformer(cfg, seed=42).transform(originals)
    result_99 = NoisyEntityTransformer(cfg, seed=99).transform(originals)

    # It's extremely unlikely that all 10 values are identical with different seeds
    different = sum(1 for a, b in zip(result_42, result_99) if a.value != b.value)
    assert different > 0, "Different seeds must produce different results"


# ---------------------------------------------------------------------------
# test_originals_not_mutated
# ---------------------------------------------------------------------------


def test_originals_not_mutated():
    """The transformer never modifies the original entity list or its elements."""
    cfg = DegradationConfig(
        value_noise_pct=0.30,
        entity_dropout_pct=0.30,
        confidence_noise_std=0.30,
        attribute_swap_pct=0.30,
    )
    originals = _make_entity_list(10)
    # Capture original values before transform
    original_values = [e.value for e in originals]
    original_confs = [e.confidence for e in originals]
    original_attrs = [e.attribute for e in originals]

    NoisyEntityTransformer(cfg, seed=42).transform(originals)

    # Originals must be unchanged
    for i, entity in enumerate(originals):
        assert entity.value == original_values[i], "Original value must not be mutated"
        assert entity.confidence == original_confs[i], "Original confidence must not be mutated"
        assert entity.attribute == original_attrs[i], "Original attribute must not be mutated"


# ---------------------------------------------------------------------------
# test_empty_list
# ---------------------------------------------------------------------------


def test_empty_list():
    """Transforming an empty list returns an empty list without error."""
    cfg = DegradationConfig(value_noise_pct=0.10, entity_dropout_pct=0.50)
    result = NoisyEntityTransformer(cfg, seed=42).transform([])
    assert result == []


# ---------------------------------------------------------------------------
# test_attribute_swap
# ---------------------------------------------------------------------------


def test_attribute_swap_changes_attributes():
    """Attribute swap permutes attribute names between entities."""
    cfg = DegradationConfig(attribute_swap_pct=1.0)  # Swap as many as possible
    transformer = NoisyEntityTransformer(cfg, seed=42)
    originals = _make_entity_list(6)
    result = transformer.transform(originals)

    assert len(result) == len(originals), "Swap must not change entity count"

    original_attrs = [e.attribute for e in originals]
    result_attrs = [e.attribute for e in result]

    # The multiset of attributes must be the same (swap only permutes, doesn't add/remove)
    assert sorted(original_attrs) == sorted(result_attrs), (
        "Attribute swap must preserve the multiset of attribute names"
    )

    # At least some attributes must have moved
    changed = sum(1 for o, r in zip(original_attrs, result_attrs) if o != r)
    assert changed > 0, "Expected at least one attribute to be swapped"
