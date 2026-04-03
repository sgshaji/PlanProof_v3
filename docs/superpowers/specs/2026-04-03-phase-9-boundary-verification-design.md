# Phase 9: Three-Tier Boundary Verification Pipeline — Design Spec

> **Date:** 2026-04-03
> **Status:** Approved
> **Goal:** Verify that the applicant's red-line site boundary is consistent with authoritative land records using three independent verification tiers: VLM visual alignment, scale-bar measurement, and INSPIRE polygon cross-reference.

---

## 1. Architecture

Three independent verification tiers, each producing a tier-specific result. A `BoundaryVerificationStep` combines them into a single `BoundaryVerificationReport` with status: `CONSISTENT / DISCREPANCY_DETECTED / INSUFFICIENT_DATA`. The combined result feeds into SABLE as evidence for a new boundary compliance rule `C005_boundary_verification`.

```
Location Plan Image ──→ Tier 1: VLM Visual Alignment ──→ ALIGNED/MISALIGNED/UNCLEAR
                    ──→ Tier 2: Scale-Bar Measurement ──→ estimated area + discrepancy flag
Site Address ─────────→ Tier 3: INSPIRE Polygon Lookup ──→ polygon area + over-claiming flag
                                                            ↓
                                          BoundaryVerificationStep
                                                            ↓
                                    CONSISTENT / DISCREPANCY_DETECTED / INSUFFICIENT_DATA
                                                            ↓
                                          SABLE evidence for C005
```

Each tier is a standalone class implementing a `BoundaryVerifier` Protocol. They can run independently and fail gracefully — if Tier 3 data isn't available, the system still has Tiers 1+2.

---

## 2. Schemas

**File:** `src/planproof/schemas/boundary.py`

```python
class BoundaryVerificationStatus(StrEnum):
    CONSISTENT = "CONSISTENT"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

@dataclass
class VisualAlignmentResult:
    status: Literal["ALIGNED", "MISALIGNED", "UNCLEAR"]
    issues: list[str]       # e.g., "Red line extends into highway on north side"
    confidence: float       # 0.0–1.0

@dataclass
class ScaleBarResult:
    estimated_frontage_m: float | None
    estimated_depth_m: float | None
    estimated_area_m2: float | None
    declared_area_m2: float | None
    discrepancy_pct: float | None   # abs % difference
    discrepancy_flag: bool          # True if >15%
    confidence: float

@dataclass
class InspireResult:
    inspire_id: str | None
    polygon_area_m2: float | None
    declared_area_m2: float | None
    area_ratio: float | None        # declared / polygon
    over_claiming_flag: bool         # True if ratio > 1.5x
    confidence: float

@dataclass
class BoundaryVerificationReport:
    tier1: VisualAlignmentResult | None
    tier2: ScaleBarResult | None
    tier3: InspireResult | None
    combined_status: BoundaryVerificationStatus
    combined_confidence: float
```

---

## 3. Tier 1: VLM Visual Alignment

**File:** `src/planproof/ingestion/boundary_verifier.py` → `VisualAlignmentVerifier`

**Input:** Location plan image (PNG/PDF)
**Output:** `VisualAlignmentResult`

**Prompt template:** `configs/prompts/boundary_visual.yaml`
- System message: explain the task — inspect the red-line boundary drawn on the OS base map
- Ask for: alignment status (ALIGNED/MISALIGNED/UNCLEAR), list of specific issues, confidence
- Output format: JSON with `status`, `issues`, `confidence`
- Wrap any user-supplied context in `<document>` tags per P1 convention

**Implementation:**
- Accepts a vision client (raw `openai.OpenAI` instance, same as VLM extractor)
- Loads `boundary_visual` prompt template
- Sends location plan image to GPT-4o with the prompt
- Parses JSON response into `VisualAlignmentResult`
- Returns `UNCLEAR` with confidence 0.0 on failure

**Limitation:** Detects gross discrepancies only — not survey-grade (1-2m) precision. See PROJECT_LOG.md 2026-04-03 entry for full analysis of what survey-grade would require.

---

## 4. Tier 2: Scale-Bar Measurement

**File:** `src/planproof/ingestion/boundary_verifier.py` → `ScaleBarVerifier`

**Input:** Location plan image + declared site area (float, m²)
**Output:** `ScaleBarResult`

**Prompt template:** `configs/prompts/boundary_scalebar.yaml`
- System message: find the scale bar, estimate site dimensions
- Ask for: scale ratio, estimated frontage (m), depth (m), area (m²)
- Output format: JSON with `scale_ratio`, `frontage_m`, `depth_m`, `area_m2`

**Implementation:**
- Accepts a vision client + declared area
- Sends image + prompt to GPT-4o
- Parses response, computes `discrepancy_pct = abs(estimated - declared) / declared`
- Sets `discrepancy_flag = True` if `discrepancy_pct > 0.15`
- Returns `discrepancy_flag=False` with confidence 0.0 if no scale bar found

**Limitation:** VLM area estimates are approximate (±20-30%). The 15% threshold catches major discrepancies only.

---

## 5. Tier 3: INSPIRE Polygon Lookup

### 5a. INSPIRE GML Parser

**File:** `src/planproof/ingestion/inspire_parser.py`

Pure Python GML parser using `xml.etree.ElementTree` — no geopandas/fiona/shapely.

**What it does:**
- Parses `data/gml/Land_Registry_Cadastral_Parcels.gml` (346K parcels, EPSG:27700)
- Extracts polygon coordinates, INSPIRE ID, and computed area/centroid per parcel
- Provides a `find_nearest(easting, northing, max_distance_m=200)` method

**Data structures:**
```python
@dataclass
class CadastralParcel:
    inspire_id: str
    coordinates: list[tuple[float, float]]  # [(easting, northing), ...]
    area_m2: float      # computed via shoelace formula
    centroid_e: float    # mean easting
    centroid_n: float    # mean northing

class InspireIndex:
    parcels: list[CadastralParcel]

    @classmethod
    def from_gml(cls, gml_path: Path) -> InspireIndex: ...

    def find_nearest(self, easting: float, northing: float, max_distance_m: float = 200.0) -> CadastralParcel | None: ...
```

**Shoelace formula** for polygon area:
```
A = 0.5 * |Σ(x_i * y_{i+1} - x_{i+1} * y_i)|
```

**Spatial lookup:** Sort parcels by easting, binary search to find candidates within `max_distance_m`, then Euclidean distance to centroids. O(log n) per lookup after O(n log n) sort.

**Caching:** Parse GML once, cache the index in memory. The 347MB GML produces ~346K parcels — manageable in memory (~50MB as Python objects).

### 5b. Geocoding

**Free API:** `postcodes.io` — no key needed, returns EPSG:27700 easting/northing for UK postcodes.

```
GET https://api.postcodes.io/postcodes/{postcode}
→ { "result": { "eastings": 408834, "northings": 286749, ... } }
```

### 5c. INSPIRE Verifier

**File:** `src/planproof/ingestion/boundary_verifier.py` → `InspireVerifier`

**Input:** Site postcode + declared site area
**Output:** `InspireResult`

**Implementation:**
1. Geocode postcode → easting/northing via postcodes.io
2. `InspireIndex.find_nearest(easting, northing)` → nearest parcel
3. Compare `declared_area / parcel.area_m2`
4. Flag over-claiming if ratio > 1.5

**Limitation:** Centroid proximity matching is approximate in dense urban areas. Proper matching would use point-in-polygon with shapely.

---

## 6. Combined Pipeline Step

**File:** `src/planproof/pipeline/steps/boundary_verification.py` → `BoundaryVerificationStep`

**Combination logic:**
- If ANY tier detects discrepancy (`MISALIGNED`, `discrepancy_flag`, `over_claiming_flag`) → `DISCREPANCY_DETECTED`
- If all available tiers pass → `CONSISTENT`
- If no tier produced a result → `INSUFFICIENT_DATA`
- Combined confidence = weighted average of tier confidences (only tiers that ran)

**Pipeline integration:**
- Registered in bootstrap after VLM extraction step
- Reads location plan image from context (classified as DRAWING with subtype containing "location" or "site")
- Reads declared site area from context entities (attribute `stated_site_area` or `total_site_area`)
- Reads site postcode from context entities (attribute `site_address`, extract postcode)
- Stores `BoundaryVerificationReport` in `context["boundary_verification"]`

---

## 7. New Rule: C005 Boundary Verification

**File:** `configs/rules/c005_boundary_verification.yaml`

```yaml
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

New evaluator type `boundary_verification` in the rule engine that reads the `BoundaryVerificationReport` from context and produces a `RuleVerdict`.

---

## 8. Testing

- **INSPIRE parser:** Unit tests for GML parsing, shoelace area, centroid computation, nearest-parcel lookup
- **Each verifier:** Unit tests with mocked VLM responses and mocked postcodes.io
- **Combination logic:** Unit tests for all status combinations
- **Integration:** Run on available BCC data (Tier 1 on drawings, Tiers 2-3 limited by missing form data)

---

## 9. Limitations (documented for dissertation)

- VLM detects gross discrepancies, not survey-grade precision (see PROJECT_LOG.md)
- Centroid proximity matching may select wrong parcel in dense urban areas
- INSPIRE data gives indicative extent, not legal boundary (general boundaries principle)
- Scale-bar VLM estimates are ±20-30% accurate
- No synthetic location plan generation — evaluation uses real BCC data only
- postcodes.io geocoding accuracy is ~10m (postcode centroid, not exact address)

---

## Out of Scope

- Shapely/geopandas dependency (pure Python throughout)
- Point-in-polygon matching (centroid proximity only)
- Synthetic location plan generation
- Multi-plan boundary consistency (location plan vs block plan)
- OS MasterMap integration (paid data)
- LiDAR point cloud analysis

---

## Dependencies

- OpenAI API key (GPT-4o for Tiers 1-2)
- postcodes.io (free, no key)
- INSPIRE GML data in `data/gml/` (already provided)
- xml.etree.ElementTree (stdlib)
- urllib/requests for postcodes.io (minimal HTTP)

---

## Success Criteria

1. INSPIRE parser loads 346K parcels and computes areas within 1% of reference
2. Tier 1 produces ALIGNED/MISALIGNED/UNCLEAR from location plan images
3. Tier 2 estimates area and flags >15% discrepancies
4. Tier 3 finds nearest INSPIRE parcel and flags >1.5x over-claiming
5. Combined step produces correct status from tier results
6. C005 rule wired into pipeline and SABLE evaluates boundary evidence
7. All existing tests pass, new tests cover all tiers
8. Run on at least 1 BCC set with location plan drawings
