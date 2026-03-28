"""Tests for reference data loaders (parcels and zones)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from planproof.representation.reference_data import (
    ParcelData,
    ZoneData,
    load_parcel,
    load_reference_set,
    load_zone,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [151.0, -33.87],
                        [151.0001304, -33.87],
                        [151.0001304, -33.8696069],
                        [151.0, -33.8696069],
                        [151.0, -33.87],
                    ]
                ],
            },
            "properties": {
                "parcel_id": "TEST_PARCEL_001",
                "set_id": "SET_TEST_001",
            },
        }
    ],
}

SAMPLE_ZONE = {
    "zone_code": "R2",
    "zone_name": "Low Density Residential",
    "applicable_rules": ["R001", "R002", "R003"],
}


@pytest.fixture()
def parcel_geojson(tmp_path: Path) -> Path:
    """Write a sample parcel.geojson to a temp directory."""
    path = tmp_path / "parcel.geojson"
    path.write_text(json.dumps(SAMPLE_GEOJSON))
    return path


@pytest.fixture()
def zone_json(tmp_path: Path) -> Path:
    """Write a sample zone.json to a temp directory."""
    path = tmp_path / "zone.json"
    path.write_text(json.dumps(SAMPLE_ZONE))
    return path


@pytest.fixture()
def reference_dir(tmp_path: Path) -> Path:
    """Create a reference directory with both parcel.geojson and zone.json."""
    (tmp_path / "parcel.geojson").write_text(json.dumps(SAMPLE_GEOJSON))
    (tmp_path / "zone.json").write_text(json.dumps(SAMPLE_ZONE))
    return tmp_path


# ---------------------------------------------------------------------------
# ParcelData tests
# ---------------------------------------------------------------------------


class TestLoadParcel:
    def test_loads_parcel_id(self, parcel_geojson: Path) -> None:
        parcel = load_parcel(parcel_geojson)
        assert parcel.parcel_id == "TEST_PARCEL_001"

    def test_loads_set_id(self, parcel_geojson: Path) -> None:
        parcel = load_parcel(parcel_geojson)
        assert parcel.set_id == "SET_TEST_001"

    def test_geometry_wkt_contains_polygon(self, parcel_geojson: Path) -> None:
        parcel = load_parcel(parcel_geojson)
        assert "POLYGON" in parcel.geometry_wkt

    def test_geometry_wkt_contains_coordinates(self, parcel_geojson: Path) -> None:
        parcel = load_parcel(parcel_geojson)
        # The WKT should contain at least one coordinate value from the fixture
        assert "151.0" in parcel.geometry_wkt

    def test_returns_frozen_dataclass(self, parcel_geojson: Path) -> None:
        parcel = load_parcel(parcel_geojson)
        assert isinstance(parcel, ParcelData)
        with pytest.raises((AttributeError, TypeError)):
            parcel.parcel_id = "mutated"  # type: ignore[misc]

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_parcel(tmp_path / "nonexistent.geojson")


# ---------------------------------------------------------------------------
# ZoneData tests
# ---------------------------------------------------------------------------


class TestLoadZone:
    def test_loads_zone_code(self, zone_json: Path) -> None:
        zone = load_zone(zone_json)
        assert zone.zone_code == "R2"

    def test_loads_zone_name(self, zone_json: Path) -> None:
        zone = load_zone(zone_json)
        assert zone.zone_name == "Low Density Residential"

    def test_loads_applicable_rules(self, zone_json: Path) -> None:
        zone = load_zone(zone_json)
        assert zone.applicable_rules == ("R001", "R002", "R003")

    def test_applicable_rules_is_tuple(self, zone_json: Path) -> None:
        zone = load_zone(zone_json)
        assert isinstance(zone.applicable_rules, tuple)

    def test_returns_frozen_dataclass(self, zone_json: Path) -> None:
        zone = load_zone(zone_json)
        assert isinstance(zone, ZoneData)
        with pytest.raises((AttributeError, TypeError)):
            zone.zone_code = "mutated"  # type: ignore[misc]

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_zone(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# load_reference_set tests
# ---------------------------------------------------------------------------


class TestLoadReferenceSet:
    def test_returns_parcel_and_zone(self, reference_dir: Path) -> None:
        parcel, zone = load_reference_set(reference_dir)
        assert isinstance(parcel, ParcelData)
        assert isinstance(zone, ZoneData)

    def test_parcel_data_correct(self, reference_dir: Path) -> None:
        parcel, _ = load_reference_set(reference_dir)
        assert parcel.parcel_id == "TEST_PARCEL_001"
        assert "POLYGON" in parcel.geometry_wkt

    def test_zone_data_correct(self, reference_dir: Path) -> None:
        _, zone = load_reference_set(reference_dir)
        assert zone.zone_code == "R2"
        assert zone.applicable_rules == ("R001", "R002", "R003")

    def test_missing_parcel_raises_file_not_found(self, tmp_path: Path) -> None:
        (tmp_path / "zone.json").write_text(json.dumps(SAMPLE_ZONE))
        with pytest.raises(FileNotFoundError):
            load_reference_set(tmp_path)
