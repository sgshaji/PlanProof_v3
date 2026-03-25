"""Tests for reference_writer — parcel GeoJSON and zone JSON generation.

# WHY: Reference files supply spatial and zoning context that the rule engine
# needs alongside the submission documents.  Tests here verify schema compliance
# (valid GeoJSON Feature, correct zone fields) so downstream consumers never
# encounter malformed reference data.
"""

from __future__ import annotations

import json
from pathlib import Path

from planproof.datagen.output.reference_writer import write_reference_files
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


def _make_scenario() -> Scenario:
    """Minimal Scenario sufficient to exercise reference file generation."""
    return Scenario(
        set_id="SET_COMPLIANT_99",
        category="compliant",
        seed=99,
        profile_id="standard",
        difficulty="medium",
        degradation_preset="clean",
        values=(
            Value(
                attribute="front_setback",
                value=7.5,
                unit="metres",
                display_text="7.5m",
            ),
        ),
        verdicts=(
            Verdict(
                rule_id="R001",
                outcome="PASS",
                evaluated_value=7.5,
                threshold=8.0,
            ),
        ),
        documents=(
            DocumentSpec(
                doc_type="FORM",
                file_format="pdf",
                values_to_place=("front_setback",),
            ),
        ),
        edge_case_strategy=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteReferenceFiles:
    """Tests for write_reference_files()."""

    def test_writes_geojson(self, tmp_path: Path) -> None:
        """reference/parcel.geojson must be a valid GeoJSON FeatureCollection.

        # WHY: GeoJSON consumers (e.g. the spatial rule engine) rely on the
        # standard 'type', 'features' structure.  A missing 'type' field would
        # cause a silent parse failure that may not surface until evaluation time.
        """
        scenario = _make_scenario()
        write_reference_files(scenario, tmp_path)

        geojson_path = tmp_path / "reference" / "parcel.geojson"
        assert geojson_path.exists(), "parcel.geojson was not written"

        with geojson_path.open(encoding="utf-8") as fh:
            data = json.load(fh)

        # Must be a valid GeoJSON FeatureCollection
        assert data.get("type") == "FeatureCollection", (
            f"Expected 'FeatureCollection', got {data.get('type')!r}"
        )
        assert "features" in data, "GeoJSON is missing 'features'"
        assert len(data["features"]) > 0, "FeatureCollection has no features"

        # Each feature must have geometry and properties with parcel_id
        feature = data["features"][0]
        assert feature.get("type") == "Feature"
        assert "geometry" in feature
        assert "properties" in feature
        assert "parcel_id" in feature["properties"], (
            "parcel feature missing 'parcel_id' property"
        )

    def test_writes_zone_json(self, tmp_path: Path) -> None:
        """reference/zone.json must contain zone_code and applicable_rules.

        # WHY: The rule engine reads zone_code to select which rules to
        # apply, and applicable_rules to know which rule IDs are in scope.
        # Missing either field causes the engine to silently skip all rules.
        """
        scenario = _make_scenario()
        write_reference_files(scenario, tmp_path)

        zone_path = tmp_path / "reference" / "zone.json"
        assert zone_path.exists(), "zone.json was not written"

        with zone_path.open(encoding="utf-8") as fh:
            data = json.load(fh)

        assert "zone_code" in data, "zone.json missing 'zone_code'"
        assert "applicable_rules" in data, "zone.json missing 'applicable_rules'"
        assert isinstance(data["applicable_rules"], list), (
            "'applicable_rules' must be a list"
        )

    def test_geojson_geometry_is_polygon(self, tmp_path: Path) -> None:
        """The parcel geometry must be a GeoJSON Polygon.

        # WHY: The spatial rule engine performs polygon-specific operations
        # (area, perimeter, setback distance).  A non-Polygon geometry type
        # (e.g. Point) would cause a type error in those operations.
        """
        scenario = _make_scenario()
        write_reference_files(scenario, tmp_path)

        with (tmp_path / "reference" / "parcel.geojson").open(encoding="utf-8") as fh:
            data = json.load(fh)

        geom = data["features"][0]["geometry"]
        assert geom["type"] == "Polygon", (
            f"Expected Polygon geometry, got {geom['type']!r}"
        )
        # Polygon coordinates must be a non-empty list of rings
        assert len(geom["coordinates"]) > 0

    def test_zone_json_has_zone_name(self, tmp_path: Path) -> None:
        """zone.json should include a human-readable zone_name field.

        # WHY: The zone_name provides a human-readable label for the zone
        # that appears in evaluation reports.  An absent zone_name forces
        # report generators to look up the name from a separate registry.
        """
        scenario = _make_scenario()
        write_reference_files(scenario, tmp_path)

        with (tmp_path / "reference" / "zone.json").open(encoding="utf-8") as fh:
            data = json.load(fh)

        assert "zone_name" in data, "zone.json missing 'zone_name'"

    def test_seeded_determinism(self, tmp_path: Path) -> None:
        """Same seed must produce identical parcel geometry on repeated calls.

        # WHY: Parcel dimensions are seeded so that the corpus is reproducible.
        # Non-deterministic parcels would prevent exact comparison between
        # generated corpora, breaking the --seed guarantee.
        """
        scenario = _make_scenario()

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        write_reference_files(scenario, dir_a)
        write_reference_files(scenario, dir_b)

        with (dir_a / "reference" / "parcel.geojson").open(encoding="utf-8") as fh:
            data_a = json.load(fh)
        with (dir_b / "reference" / "parcel.geojson").open(encoding="utf-8") as fh:
            data_b = json.load(fh)

        coords_a = data_a["features"][0]["geometry"]["coordinates"]
        coords_b = data_b["features"][0]["geometry"]["coordinates"]
        assert coords_a == coords_b, "Parcel geometry is not reproducible for same seed"
