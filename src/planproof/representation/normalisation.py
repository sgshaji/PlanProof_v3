"""Unit conversion registry and entity normaliser for PlanProof.

Provides two public classes:

- ``UnitConversionRegistry`` — extensible registry of unit→unit conversion
  functions with built-in imperial/metric conversions and common aliases.
- ``Normaliser`` — converts ``ExtractedEntity`` objects to canonical units and
  applies format normalisation (address casing, numeric precision).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import EntityType, ExtractedEntity

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

_ConvertFn = Callable[[float], float]
_RegistryKey = tuple[str, str]  # (from_unit, to_unit)

# ---------------------------------------------------------------------------
# Canonical units produced by normalisation
# ---------------------------------------------------------------------------

# Maps *source* unit → canonical_unit.
# Used by Normaliser to know which target unit to convert to.
# Note: "mm" is itself a canonical unit (used for inch-family sub-metre
# precision) and is therefore NOT listed here as needing conversion.
_CANONICAL_UNIT: dict[str, str] = {
    # length → metres
    "feet": "metres",
    "ft": "metres",
    "foot": "metres",
    "cm": "metres",
    # length → mm (inches family keeps sub-metre precision as mm)
    "inches": "mm",
    "in": "mm",
    "inch": "mm",
    # area → square_metres
    "square_feet": "square_metres",
    "sq_ft": "square_metres",
    "sqft": "square_metres",
}

# Precision (decimal places) for each canonical unit
_PRECISION: dict[str, int] = {
    "metres": 2,
    "mm": 1,
    "square_metres": 2,
    "percent": 1,
}

# Units that are already canonical — they should NEVER be further converted
# by the Normaliser even if the registry has a path for them (e.g. mm→metres
# is available for direct registry queries but must not be applied when "mm"
# is the target of an inch-family conversion).
_CANONICAL_UNITS: frozenset[str] = frozenset(_PRECISION.keys())

# Address abbreviation expansions applied *after* title-casing.
# Order matters: longer patterns first to avoid partial matches.
_ADDRESS_ABBREVS: list[tuple[str, str]] = [
    (r"\bSt\b", "Street"),
    (r"\bRd\b", "Road"),
    (r"\bAve\b", "Avenue"),
    (r"\bDr\b", "Drive"),
    (r"\bLn\b", "Lane"),
    (r"\bCt\b", "Court"),
    (r"\bPl\b", "Place"),
    (r"\bBlvd\b", "Boulevard"),
    (r"\bCres\b", "Crescent"),
    (r"\bTce\b", "Terrace"),
    (r"\bHwy\b", "Highway"),
]


# ---------------------------------------------------------------------------
# UnitConversionRegistry
# ---------------------------------------------------------------------------


class UnitConversionRegistry:
    """Registry of unit-conversion functions.

    Built-in conversions cover the most common imperial/metric units found in
    Australian and UK planning documents.  Custom conversions can be added at
    runtime via :meth:`register`.
    """

    def __init__(self) -> None:
        self._registry: dict[_RegistryKey, _ConvertFn] = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, from_unit: str, to_unit: str, fn: _ConvertFn) -> None:
        """Add or replace a conversion function.

        Parameters
        ----------
        from_unit:
            Source unit string (case-sensitive).
        to_unit:
            Target unit string (case-sensitive).
        fn:
            Callable that accepts a ``float`` and returns a ``float``.
        """
        self._registry[(from_unit, to_unit)] = fn
        _log.debug(
            "unit_conversion_registered",
            from_unit=from_unit,
            to_unit=to_unit,
        )

    def canonical_for(self, from_unit: str) -> str | None:
        """Return the registered target unit for *from_unit*, if any.

        Checks the registry for any ``(from_unit, *)`` entry and returns the
        corresponding target unit.  Returns ``None`` if *from_unit* has no
        registered conversion.

        When multiple targets are registered for the same source (unusual),
        the first match found is returned.
        """
        for (src, tgt) in self._registry:
            if src == from_unit:
                return tgt
        return None

    def convert(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convert *value* from *from_unit* to *to_unit*.

        Returns the original *value* unchanged if:
        - ``from_unit == to_unit`` (same-unit passthrough), or
        - No conversion is registered for the given pair.

        Parameters
        ----------
        value:
            Numeric value to convert.
        from_unit:
            Source unit.
        to_unit:
            Target unit.
        """
        if from_unit == to_unit:
            return value
        fn = self._registry.get((from_unit, to_unit))
        if fn is None:
            _log.debug(
                "unit_conversion_not_found",
                from_unit=from_unit,
                to_unit=to_unit,
                value=value,
            )
            return value
        return fn(value)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register all built-in conversions and their aliases."""
        # feet → metres (including aliases)
        for alias in ("feet", "ft", "foot"):
            self.register(alias, "metres", lambda v: v * 0.3048)

        # inches → mm (including aliases)
        for alias in ("inches", "in", "inch"):
            self.register(alias, "mm", lambda v: v * 25.4)

        # square_feet → square_metres (including aliases)
        for alias in ("square_feet", "sq_ft", "sqft"):
            self.register(alias, "square_metres", lambda v: v * 0.09290304)

        # mm → metres
        self.register("mm", "metres", lambda v: v / 1000.0)

        # cm → metres
        self.register("cm", "metres", lambda v: v / 100.0)


# ---------------------------------------------------------------------------
# Normaliser
# ---------------------------------------------------------------------------


class Normaliser:
    """Normalises ``ExtractedEntity`` objects to canonical representations.

    Measurement entities are converted to their canonical unit and rounded to
    the configured precision.  Address entities are title-cased and common
    abbreviations are expanded.  All other entity types are passed through
    unchanged.

    Parameters
    ----------
    registry:
        Optional custom :class:`UnitConversionRegistry`.  A default registry
        with all built-in conversions is used when not supplied.
    """

    def __init__(self, registry: UnitConversionRegistry | None = None) -> None:
        self._registry = registry if registry is not None else UnitConversionRegistry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalise(self, entity: ExtractedEntity) -> ExtractedEntity:
        """Return a normalised copy of *entity*.

        The original entity is never mutated.

        Parameters
        ----------
        entity:
            The entity to normalise.
        """
        if entity.entity_type == EntityType.MEASUREMENT:
            return self._normalise_measurement(entity)
        if entity.entity_type == EntityType.ADDRESS:
            return self._normalise_address(entity)
        return entity

    def normalise_all(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Return a normalised copy of every entity in *entities*.

        Parameters
        ----------
        entities:
            Batch of entities to normalise.
        """
        return [self.normalise(e) for e in entities]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalise_measurement(self, entity: ExtractedEntity) -> ExtractedEntity:
        """Convert measurement to canonical unit and apply precision rounding."""
        unit = entity.unit
        value = entity.value

        if unit is None or not isinstance(value, (int, float)):
            return entity

        # Determine the target canonical unit: built-in table first, then
        # fall back to whatever target the custom registry has for this unit.
        # Never convert units that are already canonical (e.g. mm stays as mm).
        canonical: str | None = _CANONICAL_UNIT.get(unit)
        if canonical is None and unit not in _CANONICAL_UNITS:
            canonical = self._registry.canonical_for(unit)

        if canonical is not None and canonical != unit:
            converted_value: float = self._registry.convert(
                float(value), unit, canonical
            )
            precision = _PRECISION.get(canonical)
            rounded: float = (
                round(converted_value, precision)
                if precision is not None
                else converted_value
            )
            _log.debug(
                "measurement_normalised",
                from_unit=unit,
                to_unit=canonical,
                original=value,
                normalised=rounded,
            )
            return entity.model_copy(update={"value": rounded, "unit": canonical})

        # No conversion needed — just apply precision if the unit is canonical
        precision = _PRECISION.get(unit) if unit else None
        if precision is not None and isinstance(value, (int, float)):
            rounded_in_place: float = round(float(value), precision)
            if rounded_in_place != float(value):
                return entity.model_copy(update={"value": rounded_in_place})

        return entity

    def _normalise_address(self, entity: ExtractedEntity) -> ExtractedEntity:
        """Apply title-casing and abbreviation expansion to address strings."""
        value = entity.value
        if not isinstance(value, str):
            return entity

        # Title-case the whole string first
        normalised = value.title()

        # Expand known abbreviations (patterns already account for title-case)
        for pattern, expansion in _ADDRESS_ABBREVS:
            normalised = re.sub(pattern, expansion, normalised)

        if normalised == value:
            return entity

        return entity.model_copy(update={"value": normalised})
