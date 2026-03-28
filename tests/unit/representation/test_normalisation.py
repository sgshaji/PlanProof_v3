"""Tests for normalisation module — unit conversion registry and Normaliser.

Tests are written TDD-style: they define the contract before implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(
    entity_type: EntityType = EntityType.MEASUREMENT,
    value: object = 10.0,
    unit: str | None = "feet",
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        unit=unit,
        confidence=0.9,
        source_document="test.pdf",
        source_page=1,
        source_region=None,
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# UnitConversionRegistry tests
# ---------------------------------------------------------------------------


class TestUnitConversionRegistry:
    """Tests for UnitConversionRegistry."""

    def test_feet_to_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "feet", "metres")
        assert abs(result - 0.3048) < 1e-6

    def test_ft_alias_to_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "ft", "metres")
        assert abs(result - 0.3048) < 1e-6

    def test_foot_alias_to_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "foot", "metres")
        assert abs(result - 0.3048) < 1e-6

    def test_inches_to_mm(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "inches", "mm")
        assert abs(result - 25.4) < 1e-6

    def test_in_alias_to_mm(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "in", "mm")
        assert abs(result - 25.4) < 1e-6

    def test_inch_alias_to_mm(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "inch", "mm")
        assert abs(result - 25.4) < 1e-6

    def test_square_feet_to_square_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "square_feet", "square_metres")
        assert abs(result - 0.092903) < 1e-4

    def test_sq_ft_alias_to_square_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "sq_ft", "square_metres")
        assert abs(result - 0.092903) < 1e-4

    def test_sqft_alias_to_square_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1.0, "sqft", "square_metres")
        assert abs(result - 0.092903) < 1e-4

    def test_mm_to_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(1000.0, "mm", "metres")
        assert abs(result - 1.0) < 1e-9

    def test_cm_to_metres(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(100.0, "cm", "metres")
        assert abs(result - 1.0) < 1e-9

    def test_same_unit_passthrough(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(42.0, "metres", "metres")
        assert result == 42.0

    def test_unknown_unit_returns_original(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        result = reg.convert(5.0, "furlongs", "metres")
        assert result == 5.0

    def test_custom_conversion_registration(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        reg.register("miles", "metres", lambda v: v * 1609.344)
        result = reg.convert(1.0, "miles", "metres")
        assert abs(result - 1609.344) < 1e-3

    def test_custom_registration_overrides_unknown(self) -> None:
        from planproof.representation.normalisation import UnitConversionRegistry

        reg = UnitConversionRegistry()
        # Before registration, unknown unit → passthrough
        assert reg.convert(3.0, "leagues", "metres") == 3.0
        reg.register("leagues", "metres", lambda v: v * 4828.032)
        assert abs(reg.convert(1.0, "leagues", "metres") - 4828.032) < 1e-3


# ---------------------------------------------------------------------------
# Normaliser tests
# ---------------------------------------------------------------------------


class TestNormaliser:
    """Tests for the Normaliser class."""

    def test_feet_entity_converts_to_metres(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 10.0, "feet")
        result = normaliser.normalise(entity)

        assert result.unit == "metres"
        assert abs(result.value - 3.05) < 0.001  # 10 * 0.3048 = 3.048 → 3.05

    def test_metres_entity_unchanged(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 7.5, "metres")
        result = normaliser.normalise(entity)

        assert result.unit == "metres"
        assert result.value == 7.5

    def test_none_unit_unchanged(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 42.0, None)
        result = normaliser.normalise(entity)

        assert result.unit is None
        assert result.value == 42.0

    def test_returns_new_entity_not_mutated(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 1.0, "feet")
        result = normaliser.normalise(entity)

        # Original must be unchanged
        assert entity.unit == "feet"
        assert entity.value == 1.0
        # Result is a different object
        assert result is not entity

    def test_batch_normalisation(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entities = [
            _make_entity(EntityType.MEASUREMENT, 10.0, "feet"),
            _make_entity(EntityType.MEASUREMENT, 5.0, "metres"),
            _make_entity(EntityType.MEASUREMENT, 100.0, "sqft"),
        ]
        results = normaliser.normalise_all(entities)

        assert len(results) == 3
        assert results[0].unit == "metres"
        assert results[1].unit == "metres"
        assert results[2].unit == "square_metres"

    def test_address_title_case(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.ADDRESS, "123 HIGH STREET", None)
        result = normaliser.normalise(entity)

        assert result.value == "123 High Street"

    def test_address_abbreviation_expansion_st(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.ADDRESS, "10 Oak St", None)
        result = normaliser.normalise(entity)

        assert result.value == "10 Oak Street"

    def test_address_abbreviation_expansion_rd(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.ADDRESS, "5 Park Rd", None)
        result = normaliser.normalise(entity)

        assert result.value == "5 Park Road"

    def test_address_abbreviation_expansion_ave(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.ADDRESS, "7 Elm Ave", None)
        result = normaliser.normalise(entity)

        assert result.value == "7 Elm Avenue"

    def test_non_string_address_passthrough(self) -> None:
        """If address value is not a string, return unchanged."""
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.ADDRESS, 12345, None)
        result = normaliser.normalise(entity)

        assert result.value == 12345

    def test_non_measurement_non_address_passthrough(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.ZONE, "R2", None)
        result = normaliser.normalise(entity)

        assert result.value == "R2"
        assert result.unit is None

    def test_numeric_precision_metres(self) -> None:
        """metres values must be rounded to 2 decimal places."""
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 1.23456789, "metres")
        result = normaliser.normalise(entity)

        assert result.value == 1.23

    def test_numeric_precision_mm(self) -> None:
        """mm values must be rounded to 1 decimal place."""
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 12.789, "mm")
        result = normaliser.normalise(entity)

        assert result.value == 12.8

    def test_numeric_precision_square_metres(self) -> None:
        """square_metres values must be rounded to 2 decimal places."""
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 15.6789, "square_metres")
        result = normaliser.normalise(entity)

        assert result.value == 15.68

    def test_numeric_precision_percent(self) -> None:
        """percent values must be rounded to 1 decimal place."""
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 33.333, "percent")
        result = normaliser.normalise(entity)

        assert result.value == 33.3

    def test_custom_registry_used_by_normaliser(self) -> None:
        from planproof.representation.normalisation import (
            Normaliser,
            UnitConversionRegistry,
        )

        reg = UnitConversionRegistry()
        reg.register("furlongs", "metres", lambda v: v * 201.168)
        normaliser = Normaliser(registry=reg)

        entity = _make_entity(EntityType.MEASUREMENT, 1.0, "furlongs")
        result = normaliser.normalise(entity)

        assert result.unit == "metres"
        assert abs(result.value - 201.17) < 0.01

    def test_inches_entity_converts_to_mm(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 2.0, "inches")
        result = normaliser.normalise(entity)

        assert result.unit == "mm"
        assert abs(result.value - 50.8) < 0.01

    def test_sqft_entity_converts_to_square_metres(self) -> None:
        from planproof.representation.normalisation import Normaliser

        normaliser = Normaliser()
        entity = _make_entity(EntityType.MEASUREMENT, 100.0, "sqft")
        result = normaliser.normalise(entity)

        assert result.unit == "square_metres"
        assert abs(result.value - 9.29) < 0.01
