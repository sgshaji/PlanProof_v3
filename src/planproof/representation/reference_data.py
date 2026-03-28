"""Reference data loaders for parcels and zones.

Provides lightweight frozen dataclasses and loader functions for reading
parcel geometry (GeoJSON) and zone rules (JSON) from the reference directory
that accompanies each planning application set.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from planproof.infrastructure.logging import get_logger

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParcelData:
    """Immutable container for a single parcel's identity and geometry."""

    parcel_id: str
    set_id: str
    geometry_wkt: str


@dataclass(frozen=True)
class ZoneData:
    """Immutable container for a planning zone and its applicable rules."""

    zone_code: str
    zone_name: str
    applicable_rules: tuple[str, ...]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _polygon_coords_to_wkt(coordinates: list[list[list[float]]]) -> str:
    """Convert GeoJSON polygon coordinate arrays to a WKT POLYGON string.

    Parameters
    ----------
    coordinates:
        GeoJSON ``Polygon`` coordinates — a list of rings, where each ring is
        a list of ``[lon, lat]`` pairs.

    Returns
    -------
    str
        WKT representation, e.g. ``POLYGON ((lon lat, ...))``.
    """
    rings: list[str] = []
    for ring in coordinates:
        pairs = ", ".join(f"{lon} {lat}" for lon, lat in ring)
        rings.append(f"({pairs})")
    return f"POLYGON ({', '.join(rings)})"


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_parcel(geojson_path: Path) -> ParcelData:
    """Load a parcel from a GeoJSON FeatureCollection file.

    Takes the first feature in the collection, reads ``parcel_id`` and
    ``set_id`` from its properties, and converts the polygon geometry to WKT.

    Parameters
    ----------
    geojson_path:
        Path to the GeoJSON file.

    Raises
    ------
    FileNotFoundError
        If *geojson_path* does not exist.
    """
    if not geojson_path.exists():
        raise FileNotFoundError(f"Parcel GeoJSON not found: {geojson_path}")

    _log.info("loading_parcel", path=str(geojson_path))
    raw = json.loads(geojson_path.read_text(encoding="utf-8"))

    feature = raw["features"][0]
    props = feature["properties"]
    coords = feature["geometry"]["coordinates"]
    wkt = _polygon_coords_to_wkt(coords)

    return ParcelData(
        parcel_id=props["parcel_id"],
        set_id=props["set_id"],
        geometry_wkt=wkt,
    )


def load_zone(zone_path: Path) -> ZoneData:
    """Load zone metadata from a JSON file.

    Parameters
    ----------
    zone_path:
        Path to the zone JSON file.

    Raises
    ------
    FileNotFoundError
        If *zone_path* does not exist.
    """
    if not zone_path.exists():
        raise FileNotFoundError(f"Zone JSON not found: {zone_path}")

    _log.info("loading_zone", path=str(zone_path))
    raw = json.loads(zone_path.read_text(encoding="utf-8"))

    return ZoneData(
        zone_code=raw["zone_code"],
        zone_name=raw["zone_name"],
        applicable_rules=tuple(raw["applicable_rules"]),
    )


def load_reference_set(reference_dir: Path) -> tuple[ParcelData, ZoneData]:
    """Load both parcel and zone data from a reference directory.

    Expects ``parcel.geojson`` and ``zone.json`` to exist inside
    *reference_dir*.

    Parameters
    ----------
    reference_dir:
        Directory containing ``parcel.geojson`` and ``zone.json``.

    Returns
    -------
    tuple[ParcelData, ZoneData]
        Parcel and zone data in that order.

    Raises
    ------
    FileNotFoundError
        If either file is missing.
    """
    _log.info("loading_reference_set", directory=str(reference_dir))
    parcel = load_parcel(reference_dir / "parcel.geojson")
    zone = load_zone(reference_dir / "zone.json")
    return parcel, zone
