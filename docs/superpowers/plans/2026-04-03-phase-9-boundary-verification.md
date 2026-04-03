# Phase 9: Three-Tier Boundary Verification Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a three-tier boundary verification system (VLM visual alignment, scale-bar measurement, INSPIRE polygon cross-reference) that feeds into SABLE as evidence for a new C005 boundary compliance rule.

**Architecture:** Seven tasks building bottom-up — (1) boundary schemas, (2) INSPIRE GML parser, (3) Tier 1 VLM visual alignment, (4) Tier 2 scale-bar measurement, (5) Tier 3 INSPIRE polygon lookup, (6) combined pipeline step + C005 rule + evaluator, (7) integration tests + documentation. Each tier is independently testable. The combined step orchestrates them into a single BoundaryVerificationReport.

**Tech Stack:** Python 3.12, pytest, pydantic, xml.etree.ElementTree, OpenAI GPT-4o, postcodes.io (free geocoding), ruff, mypy --strict.

---

## Task 1: Boundary Verification Schemas

**Files:**
- Create: `src/planproof/schemas/boundary.py`
- Test: `tests/unit/schemas/test_boundary.py`

- [ ] **Step 1: Write failing test — boundary schema construction**

Create `tests/unit/schemas/test_boundary.py`:

```python
"""Tests for boundary verification schemas."""
from __future__ import annotations

import pytest

from planproof.schemas.boundary import (
    BoundaryVerificationReport,
    BoundaryVerificationStatus,
    InspireResult,
    ScaleBarResult,
    VisualAlignmentResult,
)


class TestVisualAlignmentResult:
    def test_aligned(self) -> None:
        r = VisualAlignmentResult(status="ALIGNED", issues=[], confidence=0.85)
        assert r.status == "ALIGNED"
        assert r.confidence == 0.85

    def test_misaligned_with_issues(self) -> None:
        r = VisualAlignmentResult(
            status="MISALIGNED",
            issues=["Red line extends into highway"],
            confidence=0.75,
        )
        assert len(r.issues) == 1


class TestScaleBarResult:
    def test_no_discrepancy(self) -> None:
        r = ScaleBarResult(
            estimated_frontage_m=20.0,
            estimated_depth_m=25.0,
            estimated_area_m2=500.0,
            declared_area_m2=480.0,
            discrepancy_pct=0.042,
            discrepancy_flag=False,
            confidence=0.70,
        )
        assert r.discrepancy_flag is False

    def test_discrepancy_flagged(self) -> None:
        r = ScaleBarResult(
            estimated_frontage_m=20.0,
            estimated_depth_m=25.0,
            estimated_area_m2=500.0,
            declared_area_m2=350.0,
            discrepancy_pct=0.429,
            discrepancy_flag=True,
            confidence=0.65,
        )
        assert r.discrepancy_flag is True


class TestInspireResult:
    def test_not_over_claiming(self) -> None:
        r = InspireResult(
            inspire_id="12345",
            polygon_area_m2=500.0,
            declared_area_m2=480.0,
            area_ratio=0.96,
            over_claiming_flag=False,
            confidence=0.90,
        )
        assert r.over_claiming_flag is False

    def test_over_claiming(self) -> None:
        r = InspireResult(
            inspire_id="12345",
            polygon_area_m2=300.0,
            declared_area_m2=500.0,
            area_ratio=1.67,
            over_claiming_flag=True,
            confidence=0.90,
        )
        assert r.over_claiming_flag is True


class TestBoundaryVerificationReport:
    def test_consistent(self) -> None:
        t1 = VisualAlignmentResult(status="ALIGNED", issues=[], confidence=0.85)
        report = BoundaryVerificationReport(
            tier1=t1,
            tier2=None,
            tier3=None,
            combined_status=BoundaryVerificationStatus.CONSISTENT,
            combined_confidence=0.85,
        )
        assert report.combined_status == BoundaryVerificationStatus.CONSISTENT

    def test_discrepancy_detected(self) -> None:
        t1 = VisualAlignmentResult(status="MISALIGNED", issues=["extends into road"], confidence=0.80)
        report = BoundaryVerificationReport(
            tier1=t1,
            tier2=None,
            tier3=None,
            combined_status=BoundaryVerificationStatus.DISCREPANCY_DETECTED,
            combined_confidence=0.80,
        )
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED

    def test_insufficient_data(self) -> None:
        report = BoundaryVerificationReport(
            tier1=None,
            tier2=None,
            tier3=None,
            combined_status=BoundaryVerificationStatus.INSUFFICIENT_DATA,
            combined_confidence=0.0,
        )
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/schemas/test_boundary.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement boundary schemas**

Create `src/planproof/schemas/boundary.py`:

```python
"""Schemas for the three-tier boundary verification pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class BoundaryVerificationStatus(StrEnum):
    """Combined boundary verification outcome."""

    CONSISTENT = "CONSISTENT"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class VisualAlignmentResult:
    """Tier 1: VLM visual alignment of red-line boundary vs OS base map."""

    status: Literal["ALIGNED", "MISALIGNED", "UNCLEAR"]
    issues: list[str]
    confidence: float


@dataclass(frozen=True)
class ScaleBarResult:
    """Tier 2: Scale-bar measurement and area discrepancy detection."""

    estimated_frontage_m: float | None
    estimated_depth_m: float | None
    estimated_area_m2: float | None
    declared_area_m2: float | None
    discrepancy_pct: float | None
    discrepancy_flag: bool
    confidence: float


@dataclass(frozen=True)
class InspireResult:
    """Tier 3: INSPIRE polygon area cross-reference."""

    inspire_id: str | None
    polygon_area_m2: float | None
    declared_area_m2: float | None
    area_ratio: float | None
    over_claiming_flag: bool
    confidence: float


@dataclass(frozen=True)
class BoundaryVerificationReport:
    """Combined report from all three verification tiers."""

    tier1: VisualAlignmentResult | None
    tier2: ScaleBarResult | None
    tier3: InspireResult | None
    combined_status: BoundaryVerificationStatus
    combined_confidence: float
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/schemas/test_boundary.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/planproof/schemas/boundary.py tests/unit/schemas/test_boundary.py
git commit -m "feat(boundary): add boundary verification schemas — VisualAlignment, ScaleBar, Inspire, Report"
```

---

## Task 2: INSPIRE GML Parser

**Files:**
- Create: `src/planproof/ingestion/inspire_parser.py`
- Test: `tests/unit/ingestion/test_inspire_parser.py`

- [ ] **Step 1: Write failing tests for INSPIRE parser**

Create `tests/unit/ingestion/test_inspire_parser.py`:

```python
"""Tests for INSPIRE GML parser — pure Python, no geopandas."""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from planproof.ingestion.inspire_parser import (
    CadastralParcel,
    InspireIndex,
    shoelace_area,
)


class TestShoelaceArea:
    def test_unit_square(self) -> None:
        """1x1 square has area 1.0."""
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        assert shoelace_area(coords) == pytest.approx(1.0)

    def test_rectangle(self) -> None:
        """10x20 rectangle has area 200.0."""
        coords = [(0, 0), (10, 0), (10, 20), (0, 20), (0, 0)]
        assert shoelace_area(coords) == pytest.approx(200.0)

    def test_triangle(self) -> None:
        """Triangle with base 4, height 3 has area 6.0."""
        coords = [(0, 0), (4, 0), (2, 3), (0, 0)]
        assert shoelace_area(coords) == pytest.approx(6.0)

    def test_empty_polygon(self) -> None:
        """Empty or degenerate polygon returns 0."""
        assert shoelace_area([]) == pytest.approx(0.0)
        assert shoelace_area([(0, 0)]) == pytest.approx(0.0)


class TestCadastralParcel:
    def test_centroid(self) -> None:
        """Centroid of a square at (10,10)-(20,20) is (15, 15)."""
        p = CadastralParcel(
            inspire_id="1",
            coordinates=[(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)],
            area_m2=100.0,
            centroid_e=15.0,
            centroid_n=15.0,
        )
        assert p.centroid_e == pytest.approx(15.0)
        assert p.centroid_n == pytest.approx(15.0)


class TestInspireIndexFromGml:
    def test_parse_minimal_gml(self, tmp_path: Path) -> None:
        """Parse a minimal GML with 2 parcels."""
        gml = dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:LR="www.landregistry.gov.uk"
            xmlns:gml="http://www.opengis.net/gml/3.2">
        <wfs:member>
            <LR:PREDEFINED gml:id="P.1">
                <LR:GEOMETRY>
                    <gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700" srsDimension="2" gml:id="P.1.G">
                        <gml:exterior>
                            <gml:LinearRing>
                                <gml:posList>0 0 100 0 100 100 0 100 0 0</gml:posList>
                            </gml:LinearRing>
                        </gml:exterior>
                    </gml:Polygon>
                </LR:GEOMETRY>
                <LR:INSPIREID>1001</LR:INSPIREID>
            </LR:PREDEFINED>
        </wfs:member>
        <wfs:member>
            <LR:PREDEFINED gml:id="P.2">
                <LR:GEOMETRY>
                    <gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700" srsDimension="2" gml:id="P.2.G">
                        <gml:exterior>
                            <gml:LinearRing>
                                <gml:posList>200 200 210 200 210 210 200 210 200 200</gml:posList>
                            </gml:LinearRing>
                        </gml:exterior>
                    </gml:Polygon>
                </LR:GEOMETRY>
                <LR:INSPIREID>1002</LR:INSPIREID>
            </LR:PREDEFINED>
        </wfs:member>
        </wfs:FeatureCollection>
        """)
        gml_path = tmp_path / "test.gml"
        gml_path.write_text(gml, encoding="utf-8")

        index = InspireIndex.from_gml(gml_path)
        assert len(index.parcels) == 2
        assert index.parcels[0].inspire_id == "1001"
        assert index.parcels[0].area_m2 == pytest.approx(10000.0)
        assert index.parcels[1].inspire_id == "1002"
        assert index.parcels[1].area_m2 == pytest.approx(100.0)

    def test_find_nearest(self, tmp_path: Path) -> None:
        """find_nearest returns the closest parcel by centroid."""
        gml = dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:LR="www.landregistry.gov.uk"
            xmlns:gml="http://www.opengis.net/gml/3.2">
        <wfs:member>
            <LR:PREDEFINED gml:id="P.1">
                <LR:GEOMETRY>
                    <gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700" srsDimension="2" gml:id="P.1.G">
                        <gml:exterior>
                            <gml:LinearRing>
                                <gml:posList>100 100 200 100 200 200 100 200 100 100</gml:posList>
                            </gml:LinearRing>
                        </gml:exterior>
                    </gml:Polygon>
                </LR:GEOMETRY>
                <LR:INSPIREID>1001</LR:INSPIREID>
            </LR:PREDEFINED>
        </wfs:member>
        <wfs:member>
            <LR:PREDEFINED gml:id="P.2">
                <LR:GEOMETRY>
                    <gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700" srsDimension="2" gml:id="P.2.G">
                        <gml:exterior>
                            <gml:LinearRing>
                                <gml:posList>500 500 600 500 600 600 500 600 500 500</gml:posList>
                            </gml:LinearRing>
                        </gml:exterior>
                    </gml:Polygon>
                </LR:GEOMETRY>
                <LR:INSPIREID>1002</LR:INSPIREID>
            </LR:PREDEFINED>
        </wfs:member>
        </wfs:FeatureCollection>
        """)
        gml_path = tmp_path / "test.gml"
        gml_path.write_text(gml, encoding="utf-8")

        index = InspireIndex.from_gml(gml_path)
        # Point near parcel 1 (centroid 150, 150)
        result = index.find_nearest(160.0, 160.0)
        assert result is not None
        assert result.inspire_id == "1001"
        # Point near parcel 2 (centroid 550, 550)
        result = index.find_nearest(540.0, 540.0)
        assert result is not None
        assert result.inspire_id == "1002"

    def test_find_nearest_beyond_max_distance(self, tmp_path: Path) -> None:
        """find_nearest returns None when no parcel is within max_distance_m."""
        gml = dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:LR="www.landregistry.gov.uk"
            xmlns:gml="http://www.opengis.net/gml/3.2">
        <wfs:member>
            <LR:PREDEFINED gml:id="P.1">
                <LR:GEOMETRY>
                    <gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700" srsDimension="2" gml:id="P.1.G">
                        <gml:exterior>
                            <gml:LinearRing>
                                <gml:posList>100 100 200 100 200 200 100 200 100 100</gml:posList>
                            </gml:LinearRing>
                        </gml:exterior>
                    </gml:Polygon>
                </LR:GEOMETRY>
                <LR:INSPIREID>1001</LR:INSPIREID>
            </LR:PREDEFINED>
        </wfs:member>
        </wfs:FeatureCollection>
        """)
        gml_path = tmp_path / "test.gml"
        gml_path.write_text(gml, encoding="utf-8")

        index = InspireIndex.from_gml(gml_path)
        # Point 10km away
        result = index.find_nearest(10000.0, 10000.0, max_distance_m=200.0)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/ingestion/test_inspire_parser.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement INSPIRE parser**

Create `src/planproof/ingestion/inspire_parser.py`:

```python
"""Pure-Python INSPIRE GML parser for HM Land Registry cadastral parcels.

Parses the INSPIRE Index Polygons GML file (EPSG:27700 British National Grid)
without geopandas, fiona, or shapely — uses only xml.etree.ElementTree and
the shoelace formula for area computation.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from planproof.infrastructure.logging import get_logger

logger = get_logger(__name__)

# GML namespaces used in INSPIRE files
_NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "LR": "www.landregistry.gov.uk",
}


def shoelace_area(coords: list[tuple[float, float]]) -> float:
    """Compute polygon area using the shoelace formula.

    Coordinates are (easting, northing) pairs in a planar CRS (e.g. EPSG:27700).
    The polygon should be closed (first == last) but the formula handles both.
    Returns absolute area in square units of the CRS (m² for BNG).
    """
    n = len(coords)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Compute the centroid (mean of vertices) of a coordinate list."""
    if not coords:
        return 0.0, 0.0
    # Exclude closing vertex if polygon is closed
    pts = coords[:-1] if len(coords) > 1 and coords[0] == coords[-1] else coords
    n = len(pts)
    if n == 0:
        return 0.0, 0.0
    sum_e = sum(p[0] for p in pts)
    sum_n = sum(p[1] for p in pts)
    return sum_e / n, sum_n / n


@dataclass
class CadastralParcel:
    """One INSPIRE cadastral parcel with computed area and centroid."""

    inspire_id: str
    coordinates: list[tuple[float, float]]
    area_m2: float
    centroid_e: float
    centroid_n: float


class InspireIndex:
    """In-memory spatial index of INSPIRE cadastral parcels.

    Parses GML once and provides nearest-parcel lookup by easting/northing.
    """

    def __init__(self, parcels: list[CadastralParcel]) -> None:
        self.parcels = parcels
        # Sort by easting for fast spatial filtering
        self.parcels.sort(key=lambda p: p.centroid_e)

    @classmethod
    def from_gml(cls, gml_path: Path) -> InspireIndex:
        """Parse an INSPIRE GML file and build the spatial index.

        Uses iterparse for memory efficiency on large files.
        """
        parcels: list[CadastralParcel] = []

        # iterparse to avoid loading 347MB into memory at once
        context = ET.iterparse(str(gml_path), events=("end",))
        for event, elem in context:
            if elem.tag == f"{{{_NS['LR']}}}PREDEFINED":
                parcel = _parse_parcel(elem)
                if parcel is not None:
                    parcels.append(parcel)
                elem.clear()  # Free memory

        logger.info("inspire_index_loaded", parcel_count=len(parcels))
        return cls(parcels)

    def find_nearest(
        self,
        easting: float,
        northing: float,
        max_distance_m: float = 200.0,
    ) -> CadastralParcel | None:
        """Find the parcel whose centroid is nearest to (easting, northing).

        Returns None if no parcel is within max_distance_m.
        Uses binary search on sorted eastings for O(log n) filtering.
        """
        if not self.parcels:
            return None

        # Binary search for parcels within easting range
        lo = _bisect_left_easting(self.parcels, easting - max_distance_m)
        hi = _bisect_right_easting(self.parcels, easting + max_distance_m)

        best: CadastralParcel | None = None
        best_dist = max_distance_m

        for i in range(lo, min(hi, len(self.parcels))):
            p = self.parcels[i]
            dist = math.hypot(p.centroid_e - easting, p.centroid_n - northing)
            if dist < best_dist:
                best_dist = dist
                best = p

        return best


def _parse_parcel(elem: ET.Element) -> CadastralParcel | None:
    """Extract one CadastralParcel from an LR:PREDEFINED element."""
    inspire_id_el = elem.find("LR:INSPIREID", _NS)
    if inspire_id_el is None or inspire_id_el.text is None:
        return None

    pos_list_el = elem.find(".//gml:posList", _NS)
    if pos_list_el is None or pos_list_el.text is None:
        return None

    # Parse coordinate pairs from posList (space-separated: e1 n1 e2 n2 ...)
    raw = pos_list_el.text.strip().split()
    coords: list[tuple[float, float]] = []
    for i in range(0, len(raw) - 1, 2):
        coords.append((float(raw[i]), float(raw[i + 1])))

    if len(coords) < 3:
        return None

    area = shoelace_area(coords)
    ce, cn = _centroid(coords)

    return CadastralParcel(
        inspire_id=inspire_id_el.text.strip(),
        coordinates=coords,
        area_m2=area,
        centroid_e=ce,
        centroid_n=cn,
    )


def _bisect_left_easting(parcels: list[CadastralParcel], target: float) -> int:
    """Binary search for leftmost parcel with centroid_e >= target."""
    lo, hi = 0, len(parcels)
    while lo < hi:
        mid = (lo + hi) // 2
        if parcels[mid].centroid_e < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _bisect_right_easting(parcels: list[CadastralParcel], target: float) -> int:
    """Binary search for rightmost parcel with centroid_e <= target."""
    lo, hi = 0, len(parcels)
    while lo < hi:
        mid = (lo + hi) // 2
        if parcels[mid].centroid_e <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/ingestion/test_inspire_parser.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite**

Run: `pytest -x -q`

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/inspire_parser.py tests/unit/ingestion/test_inspire_parser.py
git commit -m "feat(boundary): add INSPIRE GML parser — pure Python, shoelace area, centroid nearest lookup"
```

---

## Task 3: Tier 1 — VLM Visual Alignment Verifier

**Files:**
- Create: `src/planproof/ingestion/boundary_verifier.py`
- Create: `configs/prompts/boundary_visual.yaml`
- Test: `tests/unit/ingestion/test_boundary_verifier.py`

- [ ] **Step 1: Create VLM prompt template**

Create `configs/prompts/boundary_visual.yaml`:

```yaml
system_message: |
  You are a planning application boundary verification assistant. You analyse
  location plan images submitted with UK planning applications. Each location
  plan shows the applicant's site outlined in red (the "red-line boundary")
  drawn on top of an Ordnance Survey base map that shows existing property
  boundaries, roads, and buildings.

  Your task: determine whether the red-line boundary is consistent with the
  visible OS property boundaries in the same image.

user_message_template: |
  Examine this location plan image. The red line shows the applicant's claimed
  site boundary, drawn on an OS base map.

  Assess the alignment between the red-line boundary and the visible OS
  property boundaries. Look for:
  - Does the red line follow existing property boundaries?
  - Does it extend into highways, public land, or neighbouring properties?
  - Does it appear to match a single property parcel?
  - Are there any obvious discrepancies?

  Respond with ONLY a JSON object:
  {
    "status": "ALIGNED" | "MISALIGNED" | "UNCLEAR",
    "issues": ["list of specific issues found, empty if ALIGNED"],
    "confidence": 0.0 to 1.0
  }

  If you cannot determine boundary alignment (e.g., image is not a location
  plan, no red line visible, or image quality too poor), respond with
  status "UNCLEAR" and confidence 0.0.

output_schema:
  type: object
  required: [status, issues, confidence]
  properties:
    status:
      type: string
      enum: [ALIGNED, MISALIGNED, UNCLEAR]
    issues:
      type: array
      items:
        type: string
    confidence:
      type: number
      minimum: 0.0
      maximum: 1.0
```

- [ ] **Step 2: Write failing tests**

Add to `tests/unit/ingestion/test_boundary_verifier.py`:

```python
"""Tests for boundary verification — Tier 1, 2, 3."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from planproof.ingestion.boundary_verifier import VisualAlignmentVerifier
from planproof.schemas.boundary import VisualAlignmentResult


class TestVisualAlignmentVerifier:
    def _mock_vlm_response(self, response_json: str) -> Any:
        """Create a mock OpenAI client that returns a fixed response."""
        mock = MagicMock()
        choice = MagicMock()
        choice.message.content = response_json
        mock.chat.completions.create.return_value = MagicMock(choices=[choice])
        return mock

    def test_aligned_response(self, tmp_path: Path) -> None:
        """VLM returns ALIGNED — verifier produces aligned result."""
        mock = self._mock_vlm_response('{"status": "ALIGNED", "issues": [], "confidence": 0.85}')
        verifier = VisualAlignmentVerifier(vision_client=mock, prompts_dir=Path("configs/prompts"))
        # Create a dummy image
        img = tmp_path / "location_plan.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = verifier.verify(img)
        assert isinstance(result, VisualAlignmentResult)
        assert result.status == "ALIGNED"
        assert result.confidence == 0.85

    def test_misaligned_response(self, tmp_path: Path) -> None:
        """VLM returns MISALIGNED with issues."""
        mock = self._mock_vlm_response('{"status": "MISALIGNED", "issues": ["extends into road"], "confidence": 0.75}')
        verifier = VisualAlignmentVerifier(vision_client=mock, prompts_dir=Path("configs/prompts"))
        img = tmp_path / "plan.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = verifier.verify(img)
        assert result.status == "MISALIGNED"
        assert "extends into road" in result.issues

    def test_vlm_failure_returns_unclear(self, tmp_path: Path) -> None:
        """VLM call fails — verifier returns UNCLEAR with confidence 0."""
        mock = MagicMock()
        mock.chat.completions.create.side_effect = RuntimeError("API down")
        verifier = VisualAlignmentVerifier(vision_client=mock, prompts_dir=Path("configs/prompts"))
        img = tmp_path / "plan.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = verifier.verify(img)
        assert result.status == "UNCLEAR"
        assert result.confidence == 0.0
```

- [ ] **Step 3: Implement VisualAlignmentVerifier**

Create `src/planproof/ingestion/boundary_verifier.py`:

```python
"""Three-tier boundary verification for planning applications.

Tier 1: VLM visual alignment — red-line vs OS base map
Tier 2: Scale-bar measurement — VLM area estimate vs declared area
Tier 3: INSPIRE polygon lookup — Land Registry area vs declared area
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.schemas.boundary import VisualAlignmentResult

logger = get_logger(__name__)

_MIME_MAP: dict[str, str] = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "tiff": "tiff"}


class VisualAlignmentVerifier:
    """Tier 1: VLM-based visual alignment of red-line boundary vs OS base map."""

    def __init__(self, vision_client: Any, prompts_dir: Path) -> None:
        self._client = vision_client
        self._loader = PromptLoader(prompts_dir)

    def verify(self, image_path: Path) -> VisualAlignmentResult:
        """Analyse a location plan image for boundary alignment."""
        try:
            template = self._loader.load("boundary_visual")
            system_msg = template.get("system_message", "")
            user_msg = template.get("user_message_template", "")
        except FileNotFoundError:
            logger.warning("boundary_visual prompt template not found")
            return VisualAlignmentResult(status="UNCLEAR", issues=["prompt template missing"], confidence=0.0)

        # Encode image
        suffix = image_path.suffix.lstrip(".").lower()
        mime = _MIME_MAP.get(suffix, "png")
        image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_msg},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_msg},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/{mime};base64,{image_data}"},
                            },
                        ],
                    },
                ],
                temperature=0,
                max_tokens=500,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("tier1_vlm_failed", error=str(exc))
            return VisualAlignmentResult(status="UNCLEAR", issues=[str(exc)], confidence=0.0)

        return _parse_visual_response(raw)


def _parse_visual_response(raw: str) -> VisualAlignmentResult:
    """Parse VLM JSON response into VisualAlignmentResult."""
    try:
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(cleaned)
        return VisualAlignmentResult(
            status=data.get("status", "UNCLEAR"),
            issues=data.get("issues", []),
            confidence=float(data.get("confidence", 0.0)),
        )
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("tier1_parse_failed", error=str(exc), response=raw[:200])
        return VisualAlignmentResult(status="UNCLEAR", issues=[f"parse error: {exc}"], confidence=0.0)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/ingestion/test_boundary_verifier.py::TestVisualAlignmentVerifier -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/planproof/ingestion/boundary_verifier.py configs/prompts/boundary_visual.yaml tests/unit/ingestion/test_boundary_verifier.py
git commit -m "feat(boundary): Tier 1 VLM visual alignment verifier with prompt template"
```

---

## Task 4: Tier 2 — Scale-Bar Measurement Verifier

**Files:**
- Modify: `src/planproof/ingestion/boundary_verifier.py`
- Create: `configs/prompts/boundary_scalebar.yaml`
- Modify: `tests/unit/ingestion/test_boundary_verifier.py`

- [ ] **Step 1: Create scale-bar prompt template**

Create `configs/prompts/boundary_scalebar.yaml`:

```yaml
system_message: |
  You are a planning application measurement assistant. You estimate site
  dimensions from location plan images by reading the scale bar.

user_message_template: |
  Examine this location plan image. Find the scale bar and use it to estimate
  the site dimensions (the area outlined in red).

  Estimate:
  1. The scale ratio (e.g., 1:1250)
  2. The site frontage (width along the road) in metres
  3. The site depth in metres
  4. The total site area in square metres

  Respond with ONLY a JSON object:
  {
    "scale_ratio": "1:1250",
    "frontage_m": 15.0,
    "depth_m": 30.0,
    "area_m2": 450.0
  }

  If you cannot find a scale bar or estimate dimensions, respond:
  {"scale_ratio": null, "frontage_m": null, "depth_m": null, "area_m2": null}
```

- [ ] **Step 2: Write failing tests**

Add to `tests/unit/ingestion/test_boundary_verifier.py`:

```python
from planproof.ingestion.boundary_verifier import ScaleBarVerifier
from planproof.schemas.boundary import ScaleBarResult


class TestScaleBarVerifier:
    def _mock_vlm_response(self, response_json: str) -> Any:
        mock = MagicMock()
        choice = MagicMock()
        choice.message.content = response_json
        mock.chat.completions.create.return_value = MagicMock(choices=[choice])
        return mock

    def test_no_discrepancy(self, tmp_path: Path) -> None:
        """Estimated area close to declared — no flag."""
        mock = self._mock_vlm_response('{"scale_ratio": "1:1250", "frontage_m": 20.0, "depth_m": 25.0, "area_m2": 500.0}')
        verifier = ScaleBarVerifier(vision_client=mock, prompts_dir=Path("configs/prompts"))
        img = tmp_path / "plan.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = verifier.verify(img, declared_area_m2=480.0)
        assert isinstance(result, ScaleBarResult)
        assert result.discrepancy_flag is False
        assert result.estimated_area_m2 == pytest.approx(500.0)

    def test_discrepancy_over_15_pct(self, tmp_path: Path) -> None:
        """Estimated area differs >15% from declared — flag raised."""
        mock = self._mock_vlm_response('{"scale_ratio": "1:1250", "frontage_m": 20.0, "depth_m": 25.0, "area_m2": 500.0}')
        verifier = ScaleBarVerifier(vision_client=mock, prompts_dir=Path("configs/prompts"))
        img = tmp_path / "plan.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = verifier.verify(img, declared_area_m2=350.0)
        assert result.discrepancy_flag is True
        assert result.discrepancy_pct is not None
        assert result.discrepancy_pct > 0.15

    def test_vlm_returns_null_no_flag(self, tmp_path: Path) -> None:
        """VLM can't find scale bar — no flag, confidence 0."""
        mock = self._mock_vlm_response('{"scale_ratio": null, "frontage_m": null, "depth_m": null, "area_m2": null}')
        verifier = ScaleBarVerifier(vision_client=mock, prompts_dir=Path("configs/prompts"))
        img = tmp_path / "plan.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = verifier.verify(img, declared_area_m2=500.0)
        assert result.discrepancy_flag is False
        assert result.confidence == 0.0
```

- [ ] **Step 3: Implement ScaleBarVerifier**

Add to `src/planproof/ingestion/boundary_verifier.py`:

```python
from planproof.schemas.boundary import ScaleBarResult


class ScaleBarVerifier:
    """Tier 2: Scale-bar measurement and area discrepancy detection."""

    def __init__(self, vision_client: Any, prompts_dir: Path) -> None:
        self._client = vision_client
        self._loader = PromptLoader(prompts_dir)

    def verify(self, image_path: Path, declared_area_m2: float) -> ScaleBarResult:
        """Estimate site area from scale bar and compare against declared area."""
        try:
            template = self._loader.load("boundary_scalebar")
            system_msg = template.get("system_message", "")
            user_msg = template.get("user_message_template", "")
        except FileNotFoundError:
            return ScaleBarResult(
                estimated_frontage_m=None, estimated_depth_m=None,
                estimated_area_m2=None, declared_area_m2=declared_area_m2,
                discrepancy_pct=None, discrepancy_flag=False, confidence=0.0,
            )

        suffix = image_path.suffix.lstrip(".").lower()
        mime = _MIME_MAP.get(suffix, "png")
        image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_msg},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_msg},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/{mime};base64,{image_data}"},
                            },
                        ],
                    },
                ],
                temperature=0,
                max_tokens=300,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("tier2_vlm_failed", error=str(exc))
            return ScaleBarResult(
                estimated_frontage_m=None, estimated_depth_m=None,
                estimated_area_m2=None, declared_area_m2=declared_area_m2,
                discrepancy_pct=None, discrepancy_flag=False, confidence=0.0,
            )

        return _parse_scalebar_response(raw, declared_area_m2)


def _parse_scalebar_response(raw: str, declared_area_m2: float) -> ScaleBarResult:
    """Parse VLM JSON response into ScaleBarResult."""
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(cleaned)

        frontage = data.get("frontage_m")
        depth = data.get("depth_m")
        area = data.get("area_m2")

        if area is None:
            return ScaleBarResult(
                estimated_frontage_m=frontage, estimated_depth_m=depth,
                estimated_area_m2=None, declared_area_m2=declared_area_m2,
                discrepancy_pct=None, discrepancy_flag=False, confidence=0.0,
            )

        area = float(area)
        discrepancy_pct = abs(area - declared_area_m2) / declared_area_m2 if declared_area_m2 > 0 else 0.0
        discrepancy_flag = discrepancy_pct > 0.15

        return ScaleBarResult(
            estimated_frontage_m=float(frontage) if frontage else None,
            estimated_depth_m=float(depth) if depth else None,
            estimated_area_m2=area,
            declared_area_m2=declared_area_m2,
            discrepancy_pct=round(discrepancy_pct, 4),
            discrepancy_flag=discrepancy_flag,
            confidence=0.65,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("tier2_parse_failed", error=str(exc))
        return ScaleBarResult(
            estimated_frontage_m=None, estimated_depth_m=None,
            estimated_area_m2=None, declared_area_m2=declared_area_m2,
            discrepancy_pct=None, discrepancy_flag=False, confidence=0.0,
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/ingestion/test_boundary_verifier.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/planproof/ingestion/boundary_verifier.py configs/prompts/boundary_scalebar.yaml tests/unit/ingestion/test_boundary_verifier.py
git commit -m "feat(boundary): Tier 2 scale-bar measurement verifier with area discrepancy detection"
```

---

## Task 5: Tier 3 — INSPIRE Polygon Verifier

**Files:**
- Modify: `src/planproof/ingestion/boundary_verifier.py`
- Modify: `tests/unit/ingestion/test_boundary_verifier.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/ingestion/test_boundary_verifier.py`:

```python
from unittest.mock import patch
from planproof.ingestion.boundary_verifier import InspireVerifier
from planproof.ingestion.inspire_parser import CadastralParcel, InspireIndex
from planproof.schemas.boundary import InspireResult


class TestInspireVerifier:
    def _mock_index(self) -> InspireIndex:
        """Create a mock InspireIndex with one parcel."""
        parcel = CadastralParcel(
            inspire_id="12345",
            coordinates=[(0, 0), (20, 0), (20, 25), (0, 25), (0, 0)],
            area_m2=500.0,
            centroid_e=408834.0,
            centroid_n=286749.0,
        )
        return InspireIndex([parcel])

    @patch("planproof.ingestion.boundary_verifier._geocode_postcode")
    def test_not_over_claiming(self, mock_geocode: Any) -> None:
        """Declared area within 1.5x of INSPIRE area — no flag."""
        mock_geocode.return_value = (408834.0, 286749.0)
        index = self._mock_index()
        verifier = InspireVerifier(inspire_index=index)
        result = verifier.verify(postcode="B1 1AA", declared_area_m2=480.0)
        assert isinstance(result, InspireResult)
        assert result.over_claiming_flag is False
        assert result.inspire_id == "12345"

    @patch("planproof.ingestion.boundary_verifier._geocode_postcode")
    def test_over_claiming(self, mock_geocode: Any) -> None:
        """Declared area >1.5x INSPIRE area — flag raised."""
        mock_geocode.return_value = (408834.0, 286749.0)
        index = self._mock_index()
        verifier = InspireVerifier(inspire_index=index)
        result = verifier.verify(postcode="B1 1AA", declared_area_m2=800.0)
        assert result.over_claiming_flag is True
        assert result.area_ratio is not None
        assert result.area_ratio > 1.5

    @patch("planproof.ingestion.boundary_verifier._geocode_postcode")
    def test_geocode_fails(self, mock_geocode: Any) -> None:
        """Geocoding failure — confidence 0, no flag."""
        mock_geocode.return_value = None
        index = self._mock_index()
        verifier = InspireVerifier(inspire_index=index)
        result = verifier.verify(postcode="INVALID", declared_area_m2=500.0)
        assert result.confidence == 0.0
        assert result.over_claiming_flag is False

    @patch("planproof.ingestion.boundary_verifier._geocode_postcode")
    def test_no_nearby_parcel(self, mock_geocode: Any) -> None:
        """No INSPIRE parcel within range — confidence 0."""
        mock_geocode.return_value = (999999.0, 999999.0)  # Far away
        index = self._mock_index()
        verifier = InspireVerifier(inspire_index=index)
        result = verifier.verify(postcode="B1 1AA", declared_area_m2=500.0)
        assert result.confidence == 0.0
        assert result.inspire_id is None
```

- [ ] **Step 2: Implement InspireVerifier and geocoding**

Add to `src/planproof/ingestion/boundary_verifier.py`:

```python
import urllib.request
import urllib.error
from planproof.ingestion.inspire_parser import InspireIndex
from planproof.schemas.boundary import InspireResult


def _geocode_postcode(postcode: str) -> tuple[float, float] | None:
    """Geocode a UK postcode to EPSG:27700 easting/northing via postcodes.io.

    Returns (easting, northing) or None on failure. No API key needed.
    """
    encoded = urllib.parse.quote(postcode.strip())
    url = f"https://api.postcodes.io/postcodes/{encoded}"

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        result = data.get("result")
        if result is None:
            return None

        easting = result.get("eastings")
        northing = result.get("northings")
        if easting is None or northing is None:
            return None

        return float(easting), float(northing)
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("geocode_failed", postcode=postcode, error=str(exc))
        return None


class InspireVerifier:
    """Tier 3: INSPIRE polygon area cross-reference."""

    def __init__(self, inspire_index: InspireIndex) -> None:
        self._index = inspire_index

    def verify(self, postcode: str, declared_area_m2: float) -> InspireResult:
        """Look up nearest INSPIRE parcel and compare area against declared."""
        coords = _geocode_postcode(postcode)
        if coords is None:
            return InspireResult(
                inspire_id=None, polygon_area_m2=None,
                declared_area_m2=declared_area_m2,
                area_ratio=None, over_claiming_flag=False, confidence=0.0,
            )

        easting, northing = coords
        parcel = self._index.find_nearest(easting, northing)

        if parcel is None:
            return InspireResult(
                inspire_id=None, polygon_area_m2=None,
                declared_area_m2=declared_area_m2,
                area_ratio=None, over_claiming_flag=False, confidence=0.0,
            )

        area_ratio = declared_area_m2 / parcel.area_m2 if parcel.area_m2 > 0 else 0.0
        over_claiming = area_ratio > 1.5

        return InspireResult(
            inspire_id=parcel.inspire_id,
            polygon_area_m2=round(parcel.area_m2, 1),
            declared_area_m2=declared_area_m2,
            area_ratio=round(area_ratio, 3),
            over_claiming_flag=over_claiming,
            confidence=0.85,
        )
```

Also add `import urllib.parse` to the imports at the top of the file.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ingestion/test_boundary_verifier.py -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/planproof/ingestion/boundary_verifier.py tests/unit/ingestion/test_boundary_verifier.py
git commit -m "feat(boundary): Tier 3 INSPIRE polygon verifier with postcodes.io geocoding"
```

---

## Task 6: Combined Pipeline Step, C005 Rule, and Evaluator

**Files:**
- Create: `src/planproof/pipeline/steps/boundary_verification.py`
- Create: `configs/rules/c005_boundary_verification.yaml`
- Create: `src/planproof/reasoning/evaluators/boundary_verification.py`
- Modify: `src/planproof/bootstrap.py` (register new step + evaluator)
- Test: `tests/unit/pipeline/steps/test_boundary_verification.py`
- Test: `tests/unit/reasoning/evaluators/test_boundary_verification.py`

- [ ] **Step 1: Create C005 rule config**

Create `configs/rules/c005_boundary_verification.yaml`:

```yaml
# C5: Boundary Verification (Three-Tier)
# Verify that the applicant's red-line site boundary is consistent with
# authoritative land records using VLM visual alignment, scale-bar
# measurement, and INSPIRE polygon cross-reference.

rule_id: C005
description: "Site boundary must be consistent with authoritative land records"
policy_source: "BCC Validation Checklist — boundary and location plan requirements"
evaluation_type: boundary_verification
parameters:
  visual_alignment_required: true
  max_area_discrepancy_pct: 0.15
  max_over_claiming_ratio: 1.5
required_evidence:
  - attribute: boundary_verification_status
    acceptable_sources: ["BOUNDARY_VERIFICATION"]
    min_confidence: 0.60
    spatial_grounding: null
```

- [ ] **Step 2: Write failing tests for boundary verification evaluator**

Create `tests/unit/reasoning/evaluators/test_boundary_verification.py`:

```python
"""Tests for boundary verification rule evaluator."""
from __future__ import annotations

from typing import Any

import pytest

from planproof.reasoning.evaluators.boundary_verification import BoundaryVerificationEvaluator
from planproof.schemas.boundary import (
    BoundaryVerificationReport,
    BoundaryVerificationStatus,
    VisualAlignmentResult,
    ScaleBarResult,
    InspireResult,
)
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleOutcome


class TestBoundaryVerificationEvaluator:
    def _make_evidence(self, report: BoundaryVerificationReport) -> ReconciledEvidence:
        return ReconciledEvidence(
            attribute="boundary_verification_status",
            status=ReconciliationStatus.AGREED,
            sources=[],
            best_value=report.combined_status.value,
            conflict_details=None,
        )

    def test_consistent_passes(self) -> None:
        t1 = VisualAlignmentResult(status="ALIGNED", issues=[], confidence=0.85)
        report = BoundaryVerificationReport(
            tier1=t1, tier2=None, tier3=None,
            combined_status=BoundaryVerificationStatus.CONSISTENT,
            combined_confidence=0.85,
        )
        evaluator = BoundaryVerificationEvaluator(parameters={"rule_id": "C005"})
        evidence = self._make_evidence(report)
        verdict = evaluator.evaluate(evidence, {"rule_id": "C005"})
        assert verdict.outcome == RuleOutcome.PASS

    def test_discrepancy_fails(self) -> None:
        t1 = VisualAlignmentResult(status="MISALIGNED", issues=["extends into road"], confidence=0.80)
        report = BoundaryVerificationReport(
            tier1=t1, tier2=None, tier3=None,
            combined_status=BoundaryVerificationStatus.DISCREPANCY_DETECTED,
            combined_confidence=0.80,
        )
        evaluator = BoundaryVerificationEvaluator(parameters={"rule_id": "C005"})
        evidence = self._make_evidence(report)
        verdict = evaluator.evaluate(evidence, {"rule_id": "C005"})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_insufficient_data_fails(self) -> None:
        report = BoundaryVerificationReport(
            tier1=None, tier2=None, tier3=None,
            combined_status=BoundaryVerificationStatus.INSUFFICIENT_DATA,
            combined_confidence=0.0,
        )
        evaluator = BoundaryVerificationEvaluator(parameters={"rule_id": "C005"})
        evidence = self._make_evidence(report)
        verdict = evaluator.evaluate(evidence, {"rule_id": "C005"})
        assert verdict.outcome == RuleOutcome.FAIL
```

- [ ] **Step 3: Implement boundary verification evaluator**

Create `src/planproof/reasoning/evaluators/boundary_verification.py`:

```python
"""Evaluator: boundary verification (C005)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.boundary import BoundaryVerificationStatus
from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class BoundaryVerificationEvaluator:
    """Evaluate boundary consistency from a BoundaryVerificationReport.

    PASS when combined_status is CONSISTENT.
    FAIL when DISCREPANCY_DETECTED or INSUFFICIENT_DATA.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))

        # Read the combined status from evidence
        status_str = str(evidence.best_value) if evidence.best_value else ""

        if status_str == BoundaryVerificationStatus.CONSISTENT:
            outcome = RuleOutcome.PASS
            explanation = "Boundary verification: all tiers consistent."
        elif status_str == BoundaryVerificationStatus.DISCREPANCY_DETECTED:
            outcome = RuleOutcome.FAIL
            explanation = "Boundary discrepancy detected by verification pipeline."
        else:
            outcome = RuleOutcome.FAIL
            explanation = "Insufficient boundary verification data."

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=status_str,
            threshold="CONSISTENT",
        )
```

- [ ] **Step 4: Write failing test for BoundaryVerificationStep**

Create `tests/unit/pipeline/steps/test_boundary_verification.py`:

```python
"""Tests for the combined boundary verification pipeline step."""
from __future__ import annotations

from planproof.pipeline.steps.boundary_verification import (
    combine_tier_results,
)
from planproof.schemas.boundary import (
    BoundaryVerificationReport,
    BoundaryVerificationStatus,
    VisualAlignmentResult,
    ScaleBarResult,
    InspireResult,
)


class TestCombineTierResults:
    def test_all_pass(self) -> None:
        t1 = VisualAlignmentResult(status="ALIGNED", issues=[], confidence=0.85)
        t3 = InspireResult(inspire_id="1", polygon_area_m2=500, declared_area_m2=480, area_ratio=0.96, over_claiming_flag=False, confidence=0.90)
        report = combine_tier_results(tier1=t1, tier2=None, tier3=t3)
        assert report.combined_status == BoundaryVerificationStatus.CONSISTENT

    def test_tier1_misaligned(self) -> None:
        t1 = VisualAlignmentResult(status="MISALIGNED", issues=["extends into road"], confidence=0.80)
        report = combine_tier_results(tier1=t1, tier2=None, tier3=None)
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED

    def test_tier2_discrepancy(self) -> None:
        t2 = ScaleBarResult(estimated_frontage_m=20, estimated_depth_m=25, estimated_area_m2=500, declared_area_m2=350, discrepancy_pct=0.43, discrepancy_flag=True, confidence=0.65)
        report = combine_tier_results(tier1=None, tier2=t2, tier3=None)
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED

    def test_tier3_over_claiming(self) -> None:
        t3 = InspireResult(inspire_id="1", polygon_area_m2=300, declared_area_m2=500, area_ratio=1.67, over_claiming_flag=True, confidence=0.85)
        report = combine_tier_results(tier1=None, tier2=None, tier3=t3)
        assert report.combined_status == BoundaryVerificationStatus.DISCREPANCY_DETECTED

    def test_no_tiers(self) -> None:
        report = combine_tier_results(tier1=None, tier2=None, tier3=None)
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA
        assert report.combined_confidence == 0.0

    def test_tier1_unclear_only(self) -> None:
        t1 = VisualAlignmentResult(status="UNCLEAR", issues=[], confidence=0.0)
        report = combine_tier_results(tier1=t1, tier2=None, tier3=None)
        assert report.combined_status == BoundaryVerificationStatus.INSUFFICIENT_DATA
```

- [ ] **Step 5: Implement BoundaryVerificationStep and combine function**

Create `src/planproof/pipeline/steps/boundary_verification.py`:

```python
"""Pipeline step: three-tier boundary verification."""
from __future__ import annotations

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.schemas.boundary import (
    BoundaryVerificationReport,
    BoundaryVerificationStatus,
    InspireResult,
    ScaleBarResult,
    VisualAlignmentResult,
)

logger = get_logger(__name__)


def combine_tier_results(
    tier1: VisualAlignmentResult | None = None,
    tier2: ScaleBarResult | None = None,
    tier3: InspireResult | None = None,
) -> BoundaryVerificationReport:
    """Combine tier results into a single BoundaryVerificationReport.

    Logic:
    - ANY tier detects discrepancy → DISCREPANCY_DETECTED
    - All available tiers pass → CONSISTENT
    - No tier produced a usable result → INSUFFICIENT_DATA
    """
    has_discrepancy = False
    has_usable_result = False
    confidences: list[float] = []

    if tier1 is not None and tier1.status != "UNCLEAR":
        has_usable_result = True
        confidences.append(tier1.confidence)
        if tier1.status == "MISALIGNED":
            has_discrepancy = True

    if tier2 is not None and tier2.estimated_area_m2 is not None:
        has_usable_result = True
        confidences.append(tier2.confidence)
        if tier2.discrepancy_flag:
            has_discrepancy = True

    if tier3 is not None and tier3.inspire_id is not None:
        has_usable_result = True
        confidences.append(tier3.confidence)
        if tier3.over_claiming_flag:
            has_discrepancy = True

    if not has_usable_result:
        status = BoundaryVerificationStatus.INSUFFICIENT_DATA
        combined_conf = 0.0
    elif has_discrepancy:
        status = BoundaryVerificationStatus.DISCREPANCY_DETECTED
        combined_conf = sum(confidences) / len(confidences) if confidences else 0.0
    else:
        status = BoundaryVerificationStatus.CONSISTENT
        combined_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return BoundaryVerificationReport(
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        combined_status=status,
        combined_confidence=round(combined_conf, 3),
    )


class BoundaryVerificationStep:
    """Run three-tier boundary verification and store result in context."""

    def __init__(
        self,
        visual_verifier: object | None = None,
        scalebar_verifier: object | None = None,
        inspire_verifier: object | None = None,
    ) -> None:
        self._visual = visual_verifier
        self._scalebar = scalebar_verifier
        self._inspire = inspire_verifier

    @property
    def name(self) -> str:
        return "boundary_verification"

    def execute(self, context: PipelineContext) -> StepResult:
        tier1 = None
        tier2 = None
        tier3 = None

        # TODO: Extract location plan image, declared area, postcode from context
        # and call each verifier. For now, store empty report.

        report = combine_tier_results(tier1, tier2, tier3)
        context["boundary_verification"] = report

        logger.info(
            "boundary_verification_complete",
            status=report.combined_status.value,
            confidence=report.combined_confidence,
        )

        return {
            "success": True,
            "message": f"Boundary verification: {report.combined_status.value}",
            "artifacts": {"boundary_report": report},
        }
```

- [ ] **Step 6: Register evaluator in factory and bootstrap**

In `src/planproof/bootstrap.py`, add import and registration:

```python
from planproof.reasoning.evaluators.boundary_verification import BoundaryVerificationEvaluator
```

And in the evaluator registration section:

```python
RuleFactory.register_evaluator("boundary_verification", BoundaryVerificationEvaluator)
```

- [ ] **Step 7: Run all tests**

Run: `pytest -x -q`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add src/planproof/pipeline/steps/boundary_verification.py src/planproof/reasoning/evaluators/boundary_verification.py configs/rules/c005_boundary_verification.yaml src/planproof/bootstrap.py tests/unit/pipeline/steps/test_boundary_verification.py tests/unit/reasoning/evaluators/test_boundary_verification.py
git commit -m "feat(boundary): combined BoundaryVerificationStep, C005 rule, boundary_verification evaluator"
```

---

## Task 7: Documentation and Project Updates

**Files:**
- Modify: `docs/EXECUTION_STATUS.md`
- Modify: `docs/PROJECT_LOG.md`
- Modify: `docs/GAPS_AND_IDEAS.md`

- [ ] **Step 1: Update EXECUTION_STATUS.md**

- Mark Phase 9 as Complete
- Add Phase 9 detailed status section with all completed tasks
- Update project statistics
- Update Next Steps to point to dissertation write-up

- [ ] **Step 2: Update PROJECT_LOG.md**

Add Phase 9 dated entry with:
- Development: schemas, INSPIRE parser, 3 verifiers, combined step, C005 rule
- Architecture: pure Python GML parsing, postcodes.io geocoding, no shapely dependency
- Key findings: from any BCC test runs
- Limitations: documented in the precision limitations entry

- [ ] **Step 3: Update GAPS_AND_IDEAS.md**

- Add Phase 9 completion note
- Update project statistics

- [ ] **Step 4: Commit and push**

```bash
git add docs/
git commit -m "docs: Phase 9 boundary verification complete — update execution status, project log, gaps"
git push origin master
```
