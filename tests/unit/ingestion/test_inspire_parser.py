"""Tests for INSPIRE GML parser — shoelace area, centroid, parsing, and nearest lookup."""
from __future__ import annotations

from pathlib import Path

import pytest

from planproof.ingestion.inspire_parser import (
    CadastralParcel,
    InspireIndex,
    shoelace_area,
)

# ---------------------------------------------------------------------------
# Minimal 2-parcel GML for parse tests
# ---------------------------------------------------------------------------
_GML_TWO_PARCELS = """\
<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:LR="www.landregistry.gov.uk"
    xmlns:gml="http://www.opengis.net/gml/3.2">
<wfs:member>
    <LR:PREDEFINED gml:id="P.1">
        <LR:GEOMETRY>
            <gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700" srsDimension="2" gml:id="P.1.G">
                <gml:exterior><gml:LinearRing>
                    <gml:posList>0 0 100 0 100 100 0 100 0 0</gml:posList>
                </gml:LinearRing></gml:exterior>
            </gml:Polygon>
        </LR:GEOMETRY>
        <LR:INSPIREID>1001</LR:INSPIREID>
    </LR:PREDEFINED>
</wfs:member>
<wfs:member>
    <LR:PREDEFINED gml:id="P.2">
        <LR:GEOMETRY>
            <gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700" srsDimension="2" gml:id="P.2.G">
                <gml:exterior><gml:LinearRing>
                    <gml:posList>500 500 600 500 600 600 500 600 500 500</gml:posList>
                </gml:LinearRing></gml:exterior>
            </gml:Polygon>
        </LR:GEOMETRY>
        <LR:INSPIREID>1002</LR:INSPIREID>
    </LR:PREDEFINED>
</wfs:member>
</wfs:FeatureCollection>
"""


# ---------------------------------------------------------------------------
# TestShoelaceArea
# ---------------------------------------------------------------------------
class TestShoelaceArea:
    def test_unit_square(self) -> None:
        coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
        assert shoelace_area(coords) == pytest.approx(1.0)

    def test_rectangle_200(self) -> None:
        coords = [(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
        assert shoelace_area(coords) == pytest.approx(200.0)

    def test_triangle_6(self) -> None:
        # Right triangle with legs 3 and 4 → area = 6
        coords = [(0.0, 0.0), (3.0, 0.0), (0.0, 4.0), (0.0, 0.0)]
        assert shoelace_area(coords) == pytest.approx(6.0)

    def test_empty_polygon(self) -> None:
        assert shoelace_area([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TestCadastralParcel
# ---------------------------------------------------------------------------
class TestCadastralParcel:
    def test_centroid_of_known_square(self) -> None:
        # Square from (0,0) to (100,100), closed ring
        coords = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0)]
        parcel = CadastralParcel(
            inspire_id="TEST",
            coordinates=coords,
            area_m2=10_000.0,
            centroid_e=50.0,
            centroid_n=50.0,
        )
        assert parcel.centroid_e == pytest.approx(50.0)
        assert parcel.centroid_n == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# TestInspireIndexFromGml
# ---------------------------------------------------------------------------
class TestInspireIndexFromGml:
    def test_parses_two_parcels(self, tmp_path: Path) -> None:
        gml_file = tmp_path / "inspire.gml"
        gml_file.write_text(_GML_TWO_PARCELS, encoding="utf-8")

        index = InspireIndex.from_gml(gml_file)

        assert len(index.parcels) == 2

    def test_inspire_ids_correct(self, tmp_path: Path) -> None:
        gml_file = tmp_path / "inspire.gml"
        gml_file.write_text(_GML_TWO_PARCELS, encoding="utf-8")

        index = InspireIndex.from_gml(gml_file)
        ids = {p.inspire_id for p in index.parcels}

        assert ids == {"1001", "1002"}

    def test_parcel_1_area(self, tmp_path: Path) -> None:
        gml_file = tmp_path / "inspire.gml"
        gml_file.write_text(_GML_TWO_PARCELS, encoding="utf-8")

        index = InspireIndex.from_gml(gml_file)
        p1 = next(p for p in index.parcels if p.inspire_id == "1001")

        # 100×100 square
        assert p1.area_m2 == pytest.approx(10_000.0)

    def test_parcel_1_centroid(self, tmp_path: Path) -> None:
        gml_file = tmp_path / "inspire.gml"
        gml_file.write_text(_GML_TWO_PARCELS, encoding="utf-8")

        index = InspireIndex.from_gml(gml_file)
        p1 = next(p for p in index.parcels if p.inspire_id == "1001")

        assert p1.centroid_e == pytest.approx(50.0)
        assert p1.centroid_n == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# TestFindNearest
# ---------------------------------------------------------------------------
class TestFindNearest:
    @pytest.fixture()
    def index(self, tmp_path: Path) -> InspireIndex:
        gml_file = tmp_path / "inspire.gml"
        gml_file.write_text(_GML_TWO_PARCELS, encoding="utf-8")
        return InspireIndex.from_gml(gml_file)

    def test_near_parcel_1_returns_1001(self, index: InspireIndex) -> None:
        # Query point just inside parcel 1 centroid (50, 50)
        result = index.find_nearest(55.0, 55.0)
        assert result is not None
        assert result.inspire_id == "1001"

    def test_near_parcel_2_returns_1002(self, index: InspireIndex) -> None:
        # Query point near parcel 2 centroid (550, 550)
        result = index.find_nearest(548.0, 552.0)
        assert result is not None
        assert result.inspire_id == "1002"


# ---------------------------------------------------------------------------
# TestFindNearestBeyondMax
# ---------------------------------------------------------------------------
class TestFindNearestBeyondMax:
    def test_far_point_returns_none(self, tmp_path: Path) -> None:
        gml_file = tmp_path / "inspire.gml"
        gml_file.write_text(_GML_TWO_PARCELS, encoding="utf-8")
        index = InspireIndex.from_gml(gml_file)

        # Point 10 km away from both parcels
        result = index.find_nearest(50_000.0, 50_000.0, max_distance_m=200.0)
        assert result is None
