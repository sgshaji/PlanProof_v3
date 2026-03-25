"""Reference writer — generates parcel GeoJSON and zone JSON reference files.

Each application set includes a ``reference/`` sub-directory with two files:

  parcel.geojson — A GeoJSON FeatureCollection containing a single Polygon
                   feature representing the property parcel.  Parcel dimensions
                   are generated from the scenario seed so they are reproducible.

  zone.json      — A JSON object describing the planning zone: zone_code,
                   zone_name, and a list of applicable rule IDs derived from
                   the scenario's verdicts.

# DESIGN: Parcel geometry is deliberately simple (an axis-aligned rectangle)
# because the evaluation rules (front setback, site coverage, etc.) do not
# depend on irregular boundary shapes.  More complex shapes can be added later
# without changing the interface.
#
# WHY: Using the scenario seed for parcel dimension sampling ensures the corpus
# is fully reproducible — two runs with the same seed always produce the same
# parcel, which is essential for diffing generated datasets and for CI.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from planproof.datagen.scenario.models import Scenario

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# WHY: The parcel dimensions below represent typical residential plot sizes in
# Australian suburban planning contexts (the target domain).  They are used as
# the sampling range so generated parcels look realistic.
_PARCEL_WIDTH_MIN: float = 10.0   # metres
_PARCEL_WIDTH_MAX: float = 30.0   # metres
_PARCEL_DEPTH_MIN: float = 20.0   # metres
_PARCEL_DEPTH_MAX: float = 50.0   # metres

# WHY: A fixed geographic origin (Sydney CBD area) grounds the coordinates in
# a plausible real-world location without requiring a spatial database lookup.
# The small per-seed offsets keep parcels spread across a plausible suburb.
_ORIGIN_LON: float = 151.0      # longitude degrees east
_ORIGIN_LAT: float = -33.87     # latitude degrees south

# WHY: A consistent zone code keeps the test corpus coherent.  Real datasets
# can override this by replacing the reference files post-generation.
_DEFAULT_ZONE_CODE: str = "R2"
_DEFAULT_ZONE_NAME: str = "Low Density Residential"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate_parcel_polygon(
    seed: int,
) -> list[list[list[float]]]:
    """Return a GeoJSON Polygon coordinate ring for a rectangular parcel.

    The parcel width and depth are sampled from seeded random within the
    realistic residential ranges defined by the module-level constants.

    # WHY: A seeded RNG ensures that the same scenario seed always produces the
    # same parcel dimensions.  We construct a fresh Random instance here (not
    # the module-level random) so this function is free of shared state.

    Args:
        seed: The scenario seed used for reproducible dimension sampling.

    Returns:
        A GeoJSON Polygon coordinate array: [[ [lon, lat], ... ]] — a single
        outer ring with 5 coordinate pairs (the first and last are equal, per
        the GeoJSON specification for closed rings).
    """
    rng = random.Random(seed)

    width = round(rng.uniform(_PARCEL_WIDTH_MIN, _PARCEL_WIDTH_MAX), 2)
    depth = round(rng.uniform(_PARCEL_DEPTH_MIN, _PARCEL_DEPTH_MAX), 2)

    # DESIGN: Convert metres to approximate decimal degrees for the GeoJSON.
    # At ~34° south, 1° latitude ≈ 111 km, 1° longitude ≈ 91 km.
    # WHY: Approximate conversion is fine here — parcel geometry is for
    # spatial rule evaluation, not geodetic survey precision.
    lat_per_metre = 1.0 / 111_000
    lon_per_metre = 1.0 / 91_000

    # Apply a small per-seed offset so multiple parcels in the same corpus
    # are not all stacked at exactly the same origin.
    # WHY: Distinct geographic locations prevent bounding-box collisions in
    # any future spatial-index-based evaluation tools.
    lon_offset = (seed % 1000) * 0.0005
    lat_offset = (seed % 500) * 0.0003

    x0 = _ORIGIN_LON + lon_offset
    y0 = _ORIGIN_LAT - lat_offset

    dx = width * lon_per_metre
    dy = depth * lat_per_metre

    # Build the closed ring: bottom-left → bottom-right → top-right → top-left → close
    ring: list[list[float]] = [
        [round(x0, 7),       round(y0, 7)],
        [round(x0 + dx, 7),  round(y0, 7)],
        [round(x0 + dx, 7),  round(y0 + dy, 7)],
        [round(x0, 7),       round(y0 + dy, 7)],
        [round(x0, 7),       round(y0, 7)],  # closed ring
    ]
    return [ring]


def _build_parcel_geojson(scenario: Scenario) -> dict[str, Any]:
    """Construct the parcel FeatureCollection dict for this scenario.

    # WHY: Separating construction from writing lets tests inspect the
    # GeoJSON dict directly without touching the file system.

    Args:
        scenario: The parent Scenario supplying seed and set_id.

    Returns:
        A GeoJSON FeatureCollection dict with one Polygon feature.
    """
    coordinates = _generate_parcel_polygon(scenario.seed)

    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": coordinates,
        },
        "properties": {
            # WHY: parcel_id mirrors the set_id so evaluation tools can link
            # the parcel back to its application set without a lookup table.
            "parcel_id": scenario.set_id,
            "set_id": scenario.set_id,
        },
    }

    return {
        "type": "FeatureCollection",
        "features": [feature],
    }


def _build_zone_json(scenario: Scenario) -> dict[str, Any]:
    """Construct the zone descriptor dict for this scenario.

    The applicable_rules list is derived from the scenario's verdicts so the
    zone record always reflects the actual rules evaluated in this set.

    # WHY: Deriving applicable_rules from verdicts (rather than hard-coding a
    # static list) means the zone.json stays accurate if the profile changes the
    # set of rules without the reference writer needing an update.

    Args:
        scenario: The parent Scenario supplying verdicts.

    Returns:
        A plain dict with zone_code, zone_name, and applicable_rules.
    """
    # Extract unique rule IDs from verdicts in their original order.
    # WHY: Using a dict for deduplication preserves insertion order (Python 3.7+),
    # which keeps the applicable_rules list deterministic.
    applicable_rules = list(dict.fromkeys(v.rule_id for v in scenario.verdicts))

    return {
        "zone_code": _DEFAULT_ZONE_CODE,
        "zone_name": _DEFAULT_ZONE_NAME,
        "applicable_rules": applicable_rules,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_reference_files(scenario: Scenario, output_dir: Path) -> None:
    """Write parcel.geojson and zone.json into a ``reference/`` sub-directory.

    Creates the ``reference/`` directory if it does not already exist.

    Args:
        scenario:   The fully built Scenario for this application set.
        output_dir: The root output directory for the application set
                    (e.g. ``data/synthetic/compliant/SET_C001/``).

    # WHY: Creating the reference/ sub-directory here (rather than in the caller)
    # keeps the contract self-contained — any caller that supplies an output_dir
    # will always get the reference sub-directory created automatically.
    """
    reference_dir = output_dir / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)

    # --- parcel.geojson ---
    parcel_data = _build_parcel_geojson(scenario)
    parcel_path = reference_dir / "parcel.geojson"
    parcel_path.write_text(
        json.dumps(parcel_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # --- zone.json ---
    zone_data = _build_zone_json(scenario)
    zone_path = reference_dir / "zone.json"
    zone_path.write_text(
        json.dumps(zone_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
