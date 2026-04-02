# PlanProof — Implementation Plan

## Document Under Review

`PlanProof_Proposal.docx` — MSc Dissertation, Assessability-Aware Multimodal Planning Compliance Validation.

---

## 1. Project Overview at a Glance

```
INPUT                          CORE ENGINE                         OUTPUT
─────────────────             ──────────────────                   ──────────────────
Planning Application          ┌─ Document Classifier              Compliance Report
  ├─ Forms (PDF)         ───► ├─ Text Extractor (OCR + LLM)  ──► ├─ PASS / FAIL verdicts
  ├─ Drawings (images)   ───► ├─ VLM Pipeline                     ├─ NOT_ASSESSABLE verdicts
  └─ Reports (PDF)            ├─ SNKG (Neo4j + Shapely)           ├─ Min Evidence Requests
                              ├─ Evidence Reconciliation           └─ Decision Dashboard
                              ├─ Assessability Engine
                              ├─ Rule Engine
                              └─ Confidence Gating
```

**Core novelty**: Not "does it pass?" but "do we have enough trustworthy evidence to even evaluate?"

---

## 2. Architecture Dependency Graph

Understanding the dependency chain is critical to sequencing work correctly.

```
Layer 0 — Foundation
  ├── Project scaffolding, CI, Neo4j instance, dev environment
  ├── [M4] Unified Entity Schema (integration contract — ALL modules depend on this)
  ├── LLM response cache infrastructure
  ├── Pipeline skeleton (grows incrementally per phase)
  └── Dataset: real BCC data + synthetic generation pipeline

Layer 1 — Ingestion (no dependencies on each other; all output M4 schema objects)
  ├── [M1] Document Classifier
  ├── [M2] Text Extraction Pipeline (OCR + LLM entity extraction)
  └── [M3] VLM Pipeline (drawing analysis — sub-experiment)

Layer 2 — Representation (depends on Layer 1)
  └── [M5] Spatial Normative Knowledge Graph (populated from M4 entities)

Layer 3 — Reasoning (depends on Layer 2)
  ├── [M6] Evidence Reconciliation Engine (queries M5)
  ├── [M7] Confidence Gating (wraps M6 outputs)
  ├── [M8] Assessability Engine (queries M5 + M6 + M7)
  └── [M9] Normative Rule Engine (invoked when M8 returns ASSESSABLE)

Layer 4 — Output (depends on Layer 3)
  ├── [M10] Compliance Scoring (aggregates M8 + M9 results)
  ├── [M11] Min Evidence Request Generator (from M8 NOT_ASSESSABLE outputs)
  └── [M12] Decision Support Dashboard (FastAPI + React + Leaflet)

Layer 5 — Evaluation
  ├── Ablation study (toggle components)
  └── Metrics computation + analysis
```

---

## 3. Phased Implementation Plan

### PHASE 0: Project Foundation (Pre-requisite for everything)

**Goal**: Repo structure, tooling, infrastructure — so that all subsequent phases build on solid ground.

#### 0.1 Repository Structure

```
planproof/
├── src/
│   └── planproof/                    # Package root (importable as planproof.*)
│       ├── bootstrap.py              # ★ Composition root — wires all dependencies
│       ├── interfaces/               # ★ Protocol definitions (NO implementations)
│       │   ├── extraction.py         # DocumentClassifier, OCRExtractor, EntityExtractor, VLMExtractor
│       │   ├── graph.py              # EntityPopulator, ReferenceDataLoader, EvidenceProvider, RuleProvider
│       │   ├── reasoning.py          # Reconciler, ConfidenceGate, AssessabilityEvaluator, RuleEvaluator
│       │   ├── output.py             # ReportGenerator, EvidenceRequestGenerator
│       │   ├── pipeline.py           # PipelineStep, PipelineContext
│       │   ├── cache.py              # ResponseCache
│       │   └── llm.py                # LLMClient
│       ├── schemas/                  # ★ Pydantic data models (M4 — split by domain)
│       │   ├── entities.py           # EntityType, ExtractionMethod, ExtractedEntity, BoundingBox
│       │   ├── reconciliation.py     # ReconciliationStatus, ReconciledEvidence
│       │   ├── assessability.py      # BlockingReason, EvidenceRequirement, AssessabilityResult
│       │   ├── rules.py              # RuleConfig, RuleOutcome, RuleVerdict
│       │   ├── pipeline.py           # StepStatus, StepResult, ComplianceReport
│       │   └── config.py             # PipelineConfig, AblationConfig, ConfidenceThresholds
│       ├── ingestion/                # Layer 1: M1, M2, M3
│       │   ├── classifier.py         # RuleBasedClassifier
│       │   ├── ocr/
│       │   │   ├── pymupdf.py        # PyMuPDFExtractor
│       │   │   └── doctr.py          # DocTRExtractor
│       │   ├── entity_extractor.py   # LLMEntityExtractor
│       │   └── vlm/
│       │       ├── gpt4o_vlm.py      # GPT4oVLMExtractor
│       │       └── llava_vlm.py      # LLaVAVLMExtractor (stretch)
│       ├── representation/           # Layer 2: M5
│       │   ├── normalisation.py      # Unit conversion, address canonicalisation
│       │   ├── snkg.py               # SNKGRepository (implements 4 Protocols)
│       │   ├── reference_data.py     # External parcel/zone geometry loader
│       │   └── flat_evidence.py      # FlatEvidenceProvider (Ablation B)
│       ├── reasoning/                # Layer 3: M6, M7, M8, M9
│       │   ├── reconciliation.py     # PairwiseReconciler
│       │   ├── confidence.py         # ThresholdConfidenceGate
│       │   ├── assessability.py      # DefaultAssessabilityEvaluator
│       │   └── evaluators/           # Rule evaluators (one per evaluation_type)
│       │       ├── factory.py        # RuleFactory with registry
│       │       ├── numeric_threshold.py
│       │       ├── ratio_threshold.py
│       │       ├── enum_check.py
│       │       ├── fuzzy_match.py
│       │       ├── numeric_tolerance.py
│       │       └── attribute_diff.py
│       ├── output/                   # Layer 4: M10, M11, M12
│       │   ├── scoring.py
│       │   ├── evidence_request.py
│       │   └── api/
│       │       ├── main.py           # FastAPI app
│       │       ├── routes/
│       │       └── dependencies.py   # DI via bootstrap
│       ├── evaluation/               # Layer 5: Ablation infrastructure
│       │   ├── ablation_runner.py
│       │   ├── metrics.py            # Precision, recall, F2, bootstrap CI
│       │   └── baselines/
│       │       ├── naive_baseline.py
│       │       └── strong_baseline.py
│       ├── infrastructure/           # Concrete cross-cutting implementations
│       │   ├── llm_cache.py          # SQLiteLLMCache
│       │   ├── openai_client.py      # OpenAIClient
│       │   ├── cached_llm.py         # CachedLLMClient (decorator)
│       │   └── logging.py            # structlog config
│       └── pipeline/                 # Orchestration
│           ├── pipeline.py           # Pipeline class (step registry)
│           └── steps/                # Thin PipelineStep wrappers
│               ├── classification.py
│               ├── text_extraction.py
│               ├── vlm_extraction.py
│               ├── normalisation.py
│               ├── graph_population.py
│               ├── reconciliation.py
│               ├── confidence_gating.py
│               ├── assessability.py
│               ├── rule_evaluation.py
│               ├── scoring.py
│               └── evidence_request.py
├── tests/
│   ├── unit/                         # Mirror src/planproof/ structure
│   ├── integration/
│   ├── fixtures/
│   └── conftest.py
├── configs/
│   ├── rules/                        # YAML per rule (R001–R003, C001–C004)
│   ├── prompts/                      # LLM/VLM prompt templates
│   ├── ablation/                     # One YAML per ablation config (7 files)
│   ├── confidence_thresholds.yaml
│   └── default.yaml
├── data/
│   ├── raw/                          # BCC data (gitignored)
│   ├── synthetic/                    # Generated datasets
│   ├── reference/                    # External parcel/zone GeoJSON
│   ├── annotations/                  # Label Studio exports
│   ├── splits/                       # Sealed train/val/test splits
│   ├── results/                      # Evaluation outputs
│   └── .llm_cache/                   # LLM response cache (gitignored)
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── ARCHITECTURE.md               # Component diagram + architectural overview
│   ├── adr/                          # Architecture Decision Records
│   └── rule-encoding-worksheets/
├── notebooks/                        # EDA, prototyping (never production logic)
├── scripts/                          # One-off scripts: seeding, hashing, generation
├── dashboard/                        # React frontend (separate package)
├── docker/                           # Neo4j, API containerisation
├── .env.example
├── pyproject.toml
├── Makefile                          # lint, typecheck, test, verify-data, evaluate
└── README.md
```

#### 0.2 Tooling & Standards

| Concern | Tool | Rationale |
|---|---|---|
| Package management | `uv` or `poetry` | Lockfile, reproducibility |
| Python version | 3.11+ | Needed for modern type hints, performance |
| Linting / formatting | `ruff` | Fast, replaces flake8 + isort + black |
| Type checking | `mypy` (strict mode) | Catches schema mismatches early — critical when passing dicts between modules |
| Testing | `pytest` + `pytest-cov` | Coverage enforced in CI via `--cov-fail-under` (see Section 4.1) |
| CI | GitHub Actions | Lint → type-check → test on every push |
| Containerisation | Docker Compose | Neo4j + API + (optionally) dashboard |
| Secrets | `.env` + `python-dotenv` | API keys never in code |
| Config | Pydantic `BaseSettings` | Validated, typed configuration |
| Logging | `structlog` | JSON structured logs for debugging pipeline runs |

#### 0.3 Infrastructure

| Component | Setup |
|---|---|
| **Neo4j** | AuraDB Free (cloud) for dev/test. Docker `neo4j:5-community` for local. All Cypher queries behind a repository abstraction so the backend is swappable. |
| **Label Studio** | Local Docker instance for VLM ground truth annotation |
| **Object storage** | Local filesystem during development. BCC PDFs/images stored under `data/raw/` (gitignored). |

#### 0.4 Core Schemas (M4) — Integration Contracts

**This is the single most critical dependency in the entire project.** Every module downstream produces or consumes these types. Define them here, before any module code exists.

- [ ] Define all core Pydantic models in `src/shared/types.py`:

```python
# --- Extraction output schema ---
class EntityType(str, Enum):
    ADDRESS = "ADDRESS"
    MEASUREMENT = "MEASUREMENT"
    CERTIFICATE = "CERTIFICATE"
    BOUNDARY = "BOUNDARY"
    ZONE = "ZONE"
    OWNERSHIP = "OWNERSHIP"

class ExtractionMethod(str, Enum):
    OCR_LLM = "OCR_LLM"
    VLM_ZEROSHOT = "VLM_ZEROSHOT"
    VLM_STRUCTURED = "VLM_STRUCTURED"
    VLM_FINETUNED = "VLM_FINETUNED"
    MANUAL = "MANUAL"               # ground truth annotations

class BoundingBox(BaseModel):
    x: float; y: float; width: float; height: float
    page: int

class ExtractedEntity(BaseModel):
    entity_type: EntityType
    value: Any                       # typed per entity_type
    unit: str | None                 # metres, square_metres, etc.
    confidence: float                # 0.0 – 1.0
    source_document: str             # file path
    source_page: int | None
    source_region: BoundingBox | None
    extraction_method: ExtractionMethod
    timestamp: datetime

# --- Reconciliation output schema ---
class ReconciliationStatus(str, Enum):
    AGREED = "AGREED"
    CONFLICTING = "CONFLICTING"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    MISSING = "MISSING"

class ReconciledEvidence(BaseModel):
    attribute: str
    status: ReconciliationStatus
    best_value: Any | None
    sources: list[ExtractedEntity]
    conflict_details: str | None

# --- Assessability output schema ---
class BlockingReason(str, Enum):
    NONE = "NONE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"

class EvidenceRequirement(BaseModel):
    attribute: str
    acceptable_sources: list[str]
    min_confidence: float
    spatial_grounding: str | None

class ConflictDetail(BaseModel):
    attribute: str
    values: list[Any]
    sources: list[str]

class AssessabilityResult(BaseModel):
    rule_id: str
    status: Literal["ASSESSABLE", "NOT_ASSESSABLE"]
    blocking_reason: BlockingReason
    missing_evidence: list[EvidenceRequirement]
    conflicts: list[ConflictDetail]

# --- Rule engine output schema ---
class RuleOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"

class RuleVerdict(BaseModel):
    rule_id: str
    outcome: RuleOutcome
    evidence_used: list[ExtractedEntity]
    explanation: str                 # human-readable
    evaluated_value: Any
    threshold: Any

# --- Pipeline step result schema ---
class StepStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"              # some items failed, others succeeded
    FAILED = "FAILED"

class StepResult(BaseModel):
    step_name: str
    status: StepStatus
    outputs: list[Any]               # successful outputs
    errors: list[str]                # error descriptions for failed items
    duration_ms: float
```

- [ ] **Schema stability rule**: after Phase 0, changes to these types require a migration — update all consuming modules and add a regression test. Pydantic's strict validation at module boundaries will catch breakage.
- [ ] **No downstream module ever sees raw extraction output** — only validated `ExtractedEntity` objects
- [ ] Unit tests: validate schema serialisation round-trips, reject invalid data (missing fields, out-of-range confidence)

#### 0.5 LLM Response Cache

Every LLM/VLM call in the system (M2, M3, baseline) must go through this cache. It serves three purposes: cost control, reproducibility, and ablation speed.

- [ ] Implement `src/shared/llm_cache.py`:

```python
class LLMCache:
    """Disk-backed cache keyed by (prompt_hash, document_hash, model_version).

    Uses SQLite for the index and filesystem for response payloads.
    Cache hits return the stored response without an API call.
    """
    def __init__(self, cache_dir: Path):
        ...

    def get_or_call(
        self,
        prompt: str,
        document_hash: str,
        model: str,
        call_fn: Callable[..., str],  # the actual API call
    ) -> CachedResponse:
        ...
```

- [ ] Cache storage: `data/.llm_cache/` (gitignored)
- [ ] Cache invalidation: manual only (delete cache dir). No automatic expiry — deterministic calls should always return the same result.
- [ ] Every LLM-calling module (M2 text extraction, M3 VLM pipeline, baseline evaluator) must use `LLMCache.get_or_call()` — never call the API directly.

#### 0.6 Pipeline Skeleton

The pipeline orchestrator is **not a Phase 6 deliverable** — it starts here as a skeleton and grows incrementally as each phase adds its step.

- [ ] Implement `src/pipeline.py` with a step registry pattern:

```python
class Pipeline:
    """Orchestrator that runs registered steps in order.

    Each step is a callable: (StepInput) -> StepResult.
    Steps can be toggled on/off via ablation config.
    The pipeline is the integration seam — each phase registers its step here.
    """
    def __init__(self, config: PipelineConfig):
        self.steps: list[PipelineStep] = []
        self.config = config

    def register(self, step: PipelineStep) -> None: ...
    def run(self, input_dir: Path) -> PipelineReport: ...
```

- [ ] In Phase 0, the pipeline has zero steps — it just accepts input and returns an empty report
- [ ] Each subsequent phase registers its step(s). By Phase 5, the pipeline is complete without a separate integration phase.
- [ ] Ablation toggle config:

```yaml
# configs/ablation.yaml
ablation:
  use_snkg: true
  use_rule_engine: true
  use_confidence_gating: true
  use_assessability_engine: true
  use_evidence_reconciliation: true
```

#### 0.7 Error Handling Strategy

Pipeline steps process multiple documents. Some will fail (bad OCR, malformed PDF, LLM returns garbage). The error model ensures failures flow through the system naturally rather than crashing the pipeline.

- [ ] **Principle**: extraction failures become NOT_ASSESSABLE verdicts automatically. A failed extraction produces an `ExtractedEntity` with `confidence=0.0`, which confidence gating catches, which the assessability engine treats as missing evidence.
- [ ] Each pipeline step returns a `StepResult` (defined in 0.4 above) with `SUCCESS`, `PARTIAL`, or `FAILED` status
- [ ] `PARTIAL` means some items in the batch succeeded and some failed — the pipeline continues with successful items
- [ ] `FAILED` means the entire step failed — the pipeline logs the error and skips downstream steps that depend on this step's output
- [ ] All errors are logged with structured context (document path, step name, error type) via structlog
- [ ] **No silent swallowing of errors** — every error is either surfaced in the compliance report (as NOT_ASSESSABLE with reason) or logged for debugging

#### Deliverable: A green CI pipeline on an empty repo. `make lint`, `make typecheck`, `make test` all pass. Neo4j reachable. Core schemas importable. LLM cache functional. Pipeline skeleton accepts input and returns empty report. README documents setup steps.

---

### PHASE 1: Data Pipeline & Synthetic Generation

**Goal**: All datasets ready before any model code. This is the most under-estimated phase in ML projects.

#### 1.1 BCC Real Data Acquisition & Anonymisation

- [ ] Obtain 10 real BCC application sets (~70 documents)
- [ ] Implement PII anonymisation script (names, full addresses → pseudonyms)
- [ ] Store anonymised versions under `data/raw/`
- [ ] Document provenance and any use restrictions

#### 1.2 Synthetic Dataset Generation

This is the **critical evaluation dataset** — it's your ground truth for rule engine validation.

- [ ] Define violation matrix: for each rule (R001 height ≤ 8m, R002 rear garden ≥ 10m, R003 site coverage ≤ 50%), enumerate violation types
- [ ] Build a synthetic document generator:
  - Text-based PDFs: use `reportlab` or `fpdf2` with templates
  - Synthetic drawings: `matplotlib` or `Pillow` with dimension annotations
  - Inject known values (compliant + non-compliant) per the violation matrix
- [ ] Generate:
  - 20 compliant variation sets (~120 docs)
  - 20 non-compliant sets (~120 docs) — labelled with exact violations
  - 10 edge-case sets (~60 docs) — partial data, conflicting values, missing docs
- [ ] Each synthetic document must carry a metadata sidecar (JSON) with ground truth labels
- [ ] **Generate reference geometry for each synthetic set**: each application set must include a corresponding parcel GeoJSON (simple rectangle or polygon) and zone assignment file in `data/synthetic/{set_id}/reference/`. These are consumed by the SNKG reference data loader (Phase 3, Section 3.3). Without them, C3 (boundary validation) and zone-based rules have no reference data to validate against. Generate these alongside the PDFs/images — they are part of the synthetic ground truth.

#### 1.2.1 Synthetic Realism Validation (addresses F1)

The entire evaluation rests on synthetic data quality. If synthetic documents don't resemble real-world submissions, results won't generalise. Mitigate this explicitly:

- [ ] **Template from real documents**: base synthetic PDF templates on the layout, formatting, and field structure of actual BCC application forms — don't invent layouts from scratch
- [ ] **Domain expert review gate**: before generating the full batch, produce 3-5 synthetic sets and have your BCC partner contact review them for realism. Iterate on the generator based on feedback. **Do not proceed to full generation until at least one domain expert confirms plausibility.**
- [ ] **Controlled realism dimensions**: for each synthetic set, log which realism features are present:
  - Realistic noise (OCR artefacts, slight misalignment, low-resolution scans)?
  - Plausible measurement values (not just threshold +/- 1, but realistic architectural values)?
  - Realistic document bundle composition (some sets have 5 docs, some have 12)?
  - Realistic naming conventions (filenames like `2024-HH-1234_ElevationDrawing.pdf`)?
- [ ] **Dissertation disclosure**: document synthetic generation methodology and its limitations as a dedicated subsection. Acknowledge the generalisation gap honestly — this strengthens rather than weakens the dissertation.

#### 1.3 Test Set Sealing

- [ ] Implement seeded random train/val/test split (e.g. 60/20/20)
- [ ] Compute MD5 hash of each file in test set, store manifest
- [ ] Script that verifies test set integrity before any evaluation run
- [ ] **Rule: test set is NEVER used during development, only during Phase 7 evaluation**

#### Deliverable: `data/` directory populated. `make verify-data` confirms integrity. Ground truth labels loadable as Python dicts.

---

### PHASE 2: Ingestion Layer (Modules M1, M2, M3)

**Goal**: Convert raw documents into structured, typed, confidence-annotated entities.

#### 2.1 Document Classifier (M1)

- [ ] Classify each file in an application set into: `FORM`, `DRAWING`, `REPORT`, `CERTIFICATE`, `OTHER`
- [ ] Implementation: rule-based classifier using:
  - File metadata (filename patterns)
  - Text density (high → form/report; low → drawing)
  - Image feature heuristics (line density, aspect ratio)
- [ ] Output: `ClassifiedDocument` dataclass with `doc_type`, `confidence`, `file_path`
- [ ] Test: 100% of BCC real data correctly classified (manually verify, fix rules)

**Design note**: Keep this intentionally simple. A rule-based classifier with fallback to LLM classification for `OTHER` cases is the right call for a dissertation where the classifier isn't the research contribution.

#### 2.2 Text Extraction Pipeline (M2)

- [ ] PDF text extraction: `PyMuPDF` for text-layer PDFs, `DocTR` for scanned PDFs
- [ ] LLM structured extraction: send extracted text to LLM with a structured output prompt
  - Use function calling / JSON mode to extract: addresses, names, measurements, dates, certificate types
  - Every extracted value carries: `value`, `confidence`, `source_document`, `source_page`, `source_span`
- [ ] Prompt templates stored in `configs/prompts/` (version controlled, not hardcoded)
- [ ] Output: list of `ExtractedEntity` objects conforming to Unified Entity Schema
- [ ] **Critical**: extraction must be idempotent — same input always produces same output (set temperature=0, seed if available)

Compliance checks addressed here: **C1 (Certificate Type)**, **C2 (Address Consistency)**.

#### 2.3 VLM Pipeline (M3) — Sub-Experiment

This is a **bounded research investigation**, not a production pipeline. Structure it accordingly.

- [ ] **Stage 1 — Zero-shot baseline**
  - Pass drawing image to GPT-4o with minimal prompt: "Extract all dimensions and spatial attributes from this architectural drawing"
  - Record raw outputs
- [ ] **Stage 2 — Structured prompting**
  - Specify exact attributes to extract, dimension annotation cues, output JSON schema, few-shot examples
  - Prompt template in `configs/prompts/vlm_structured.yaml`
- [ ] **Stage 3 (stretch) — LoRA fine-tuning**
  - Fine-tune LLaVA-1.5 7B on annotated synthetic drawings
  - Only attempt if annotation volume ≥ 20 drawings and GPU available
- [ ] **Ground truth annotation**
  - Manually annotate 20–30 drawings using Label Studio
  - Export annotations as JSON with bounding boxes + attribute values
- [ ] Evaluation: Precision / Recall of extracted spatial attributes vs. ground truth at each stage

**Output**: Each extraction produces `ExtractedEntity` objects with confidence scores reflecting the VLM's uncertainty.

**Pipeline integration**: Register classification step (M1), text extraction step (M2), and VLM step (M3) into `pipeline.py`. After this phase, `pipeline.run()` accepts a document directory and returns a list of `ExtractedEntity` objects.

#### Deliverable: Given any document in a planning application, the system produces typed, confidence-annotated entities. End-to-end test: feed a complete BCC application set through the pipeline, get back structured entities.

---

### PHASE 3: Representation Layer (Module M5)

**Goal**: Extracted entities (already conforming to M4 schema from Phase 0) are stored in a queryable knowledge graph with spatial capabilities.

**Note**: The Unified Entity Schema (M4) was defined in Phase 0. This phase adds normalisation utilities and the graph layer.

#### 3.1 Entity Normalisation

- [ ] Implement normalisation rules in `src/representation/normalisation.py`:
  - Unit conversion (ft→m, sq ft→sq m, inches→cm)
  - Address canonicalisation (strip whitespace, normalise postcode format)
  - Measurement rounding (to appropriate precision per entity type)
- [ ] Normalisation is applied to all `ExtractedEntity` objects before graph population
- [ ] Test: round-trip normalisation preserves semantic equivalence

#### 3.2 Spatial Normative Knowledge Graph (M5)

- [ ] Define Neo4j node labels and relationship types:

```
(:Building)          -[:LOCATED_WITHIN]->  (:LandParcel)
(:LandParcel)        -[:IN_ZONE]->         (:ZoneCategory)
(:ZoneCategory)      -[:GOVERNED_BY]->     (:Policy)
(:Policy)            -[:CONTAINS_RULE]->   (:Rule)
(:Rule)              -[:REQUIRES]->        (:EvidenceRequirement)
(:ExtractedEntity)   -[:SUPPORTS]->        (:Rule)
(:ExtractedEntity)   -[:DERIVED_FROM]->    (:SourceDocument)
```

- [ ] Implement graph repository abstraction (`SNKGRepository` class) with methods:
  - `populate_from_entities(entities: list[ExtractedEntity])`
  - `get_rules_for_zone(zone: ZoneCategory) -> list[Rule]`
  - `get_evidence_for_rule(rule_id: str) -> list[ExtractedEntity]`
  - `get_conflicting_evidence(attribute: str) -> list[tuple[ExtractedEntity, ExtractedEntity]]`
- [ ] Pre-populate regulatory layer: NPPF rules, BCC Local Plan rules for householder development
  - **This is manual knowledge engineering** — encode the 3 rules (R001–R003) and 4 compliance checks (C1–C4) as graph nodes
  - Store rule templates in `configs/rules/` as YAML, load into graph on startup
  - **Encoding order (addresses F3 — knowledge engineering bottleneck)**:
    1. R001–R003 first — these have unambiguous numeric thresholds and clear pass/fail semantics
    2. C1 (certificate) and C2 (address) next — form-level checks with well-defined expected values
    3. C3 (boundary) — requires spatial ops but the rule logic is straightforward once geometry is available
    4. C4 (plan change) last and only if time permits — the "material change" concept is inherently ambiguous; descope to attribute-level diff (see Section 7, descoping strategy)
  - For each rule, create a **rule encoding worksheet** documenting: (a) the original policy text verbatim, (b) the interpretation as a deterministic condition, (c) any ambiguities or simplifications made, (d) sign-off from BCC contact if possible. This is both a quality control step and dissertation material.
- [ ] Spatial operations via Shapely:
  - Polygon containment (is building within parcel?)
  - Buffer intersection (setback distance check)
  - Area computation (site coverage ratio)
  - Results stored as edge attributes in the graph

#### 3.3 External Reference Data Ingestion

C3 (Boundary Validation) and zone-based rules require reference geometry that doesn't come from the applicant's documents — it comes from external authoritative sources. This needs an explicit ingestion path.

- [ ] **Parcel geometry**: Load OS/Land Registry parcel boundaries as `LandParcel` nodes with polygon geometry
  - For the dissertation: use GeoJSON fixture files in `data/reference/parcels/`, one per application site. These can be manually extracted from publicly available OS OpenData or the Land Registry INSPIRE Index.
  - Loader: `src/representation/reference_data.py` with `load_parcel(parcel_id: str) -> LandParcel`
  - Each synthetic application set must include a corresponding parcel GeoJSON in its metadata sidecar
- [ ] **Zone boundaries**: Load conservation areas, flood zones, and residential zone polygons as `ZoneCategory` nodes
  - Source: BCC's publicly available planning constraint maps (GeoJSON/Shapefile)
  - For synthetic data: generate simple rectangular zone polygons that match the synthetic site locations
- [ ] **Loading strategy**: Reference data is loaded into the SNKG as a setup step before per-application entity population. It is static across applications (parcels/zones don't change per submission).
- [ ] Add `SNKGRepository.load_reference_data(parcels_dir: Path, zones_dir: Path)` method
- [ ] **Scope boundary**: PlanProof does NOT geocode addresses or call live OS/Land Registry APIs. All reference data is pre-staged as local files. This is an explicit simplification documented in the dissertation's scope exclusions.

**Pipeline integration**: Register normalisation step, reference data loading, and SNKG population step into `pipeline.py`. After this phase, `pipeline.run()` produces a populated graph with both application entities and reference geometry.

#### Deliverable: Given a set of `ExtractedEntity` objects, the SNKG is populated and queryable. `make test-graph` runs Cypher queries and validates expected nodes/edges exist.

---

### PHASE 4: Reasoning Layer (Modules M6, M7, M8, M9)

**Goal**: The intellectual core of the system. This is where the research contribution lives.

#### 4.1 Evidence Reconciliation Engine (M6)

- [ ] For each attribute required by a rule, gather all `ExtractedEntity` objects that provide a value
- [ ] Pairwise comparison:
  - **Agreement**: values within tolerance (configurable per attribute type)
  - **Conflict**: values differ beyond tolerance
  - **Single-source**: only one extraction exists
- [ ] Output: `ReconciledEvidence` object per attribute (schema defined in Phase 0, Section 0.4)
- [ ] **Start with pairwise comparison only** (proposal acknowledges this as a scoping decision)
- [ ] Test: synthetic dataset with injected conflicts should produce CONFLICTING status

#### 4.2 Confidence Gating (M7)

- [ ] Define confidence thresholds per extraction method and entity type:

```yaml
# configs/confidence_thresholds.yaml
thresholds:
  OCR_LLM:
    ADDRESS: 0.85
    MEASUREMENT: 0.80
    CERTIFICATE: 0.90
  VLM_ZEROSHOT:
    MEASUREMENT: 0.70    # higher bar because VLM is less reliable
    BOUNDARY: 0.75
  VLM_STRUCTURED:
    MEASUREMENT: 0.60
    BOUNDARY: 0.65
```

- [ ] Gate logic: if `entity.confidence < threshold[entity.extraction_method][entity.entity_type]`, mark as `LOW_CONFIDENCE`
- [ ] Low-confidence entities are still stored in the graph but flagged — the assessability engine decides whether to use them
- [ ] **Calibration**: after Phase 2 is complete, calibrate thresholds empirically using the strategy defined in Section 4.2 (Confidence Score Sourcing Strategy). Plot reliability diagrams on the annotated set.

#### 4.3 Assessability Engine (M8) — Core Novelty

- [ ] For each rule, define an **evidence template** specifying required evidence:

```yaml
# configs/rules/r001_max_height.yaml
rule_id: R001
description: "Maximum building height shall not exceed 8 metres"
policy_source: "BCC Local Plan Policy DM30"
required_evidence:
  - attribute: building_height
    acceptable_sources: [DRAWING, REPORT]
    min_confidence: 0.80
    spatial_grounding: null
  - attribute: zone_category
    acceptable_sources: [FORM, EXTERNAL_DATA]
    min_confidence: 0.90
    spatial_grounding: LOCATED_WITHIN
```

- [ ] Assessability classification logic:

```
For each Rule:
  1. Query SNKG for all evidence supporting this rule
  2. For each required_evidence item:
     a. Is there at least one entity with acceptable source type?
     b. Does it pass confidence gating?
     c. If spatial_grounding required, is the spatial relationship verified?
  3. Run reconciliation on gathered evidence
  4. Decision:
     - All requirements met + no conflicts → ASSESSABLE
     - Any requirement unmet → NOT_ASSESSABLE (missing: list what's missing)
     - Requirements met but conflicts exist → NOT_ASSESSABLE (conflicting: list conflicts)
```

- [ ] Output: `AssessabilityResult` object per rule (schema defined in Phase 0, Section 0.4)
- [ ] Test: edge-case synthetic sets (missing documents, conflicting values) must produce NOT_ASSESSABLE with correct blocking reasons

#### 4.4 Normative Rule Engine (M9)

- [ ] Only invoked when Assessability Engine returns ASSESSABLE
- [ ] Implement each rule as a Python dataclass with a typed `evaluate()` method:

```python
@dataclass
class MaxHeightRule:
    rule_id: str = "R001"
    threshold: float = 8.0  # metres
    
    def evaluate(self, evidence: ReconciledEvidence) -> RuleVerdict:
        height = evidence.best_value
        if height <= self.threshold:
            return RuleVerdict(rule_id=self.rule_id, outcome="PASS", ...)
        else:
            return RuleVerdict(rule_id=self.rule_id, outcome="FAIL", ...)
```

- [ ] Rules for all in-scope checks, grouped by implementation complexity:

  **Tier 1 — Straightforward (implement first)**:
  - **R001**: Max height ≤ 8m — numeric threshold comparison
  - **R002**: Min rear garden ≥ 10m — numeric threshold comparison
  - **R003**: Max site coverage ≤ 50% — `building_footprint_area / parcel_area`, compare to threshold
  - **C1**: Certificate type validity — enum check: is the declared certificate type (A/B/C/D) consistent with ownership evidence?
  - **C2**: Address consistency — fuzzy string match at postcode level between form address and drawing title block address (use `rapidfuzz` or similar; threshold: Levenshtein ratio ≥ 0.85 on postcode)

  **Tier 2 — Simplified scope (addresses F6/F7)**:
  - **C3**: Boundary validation — **simplified implementation**: compare stated site area on the application form against the reference parcel area from Land Registry data. PASS if within ±15% tolerance. This tests the evidence reconciliation and assessability logic without requiring polygon extraction from hand-drawn drawings. If VLM extraction of boundary polygons proves viable in Phase 2, upgrade to Shapely polygon IoU comparison.
  - **C4**: Plan change detection — **simplified implementation**: extract key numeric attributes (height, footprint area, number of storeys) from both proposed and previously-approved document sets. Flag differences exceeding a per-attribute tolerance. Do NOT attempt visual/structural comparison of drawings. If the previously-approved drawing lacks dimension annotations, return NOT_ASSESSABLE — this is the assessability engine working exactly as designed.

- [ ] Every `RuleVerdict` includes: `outcome`, `rule_id`, `evidence_used` (with source provenance), `explanation` (human-readable)
- [ ] **Deterministic**: no LLM in the rule evaluation path. Same inputs → same outputs.

**Pipeline integration**: Register reconciliation, confidence gating, assessability, and rule engine steps into `pipeline.py`. After this phase, `pipeline.run()` produces per-rule verdicts.

#### Deliverable: Given a populated SNKG, the reasoning layer produces per-rule verdicts (PASS / FAIL / NOT_ASSESSABLE) with full provenance. Integration test: feed synthetic compliant set → all PASS. Feed non-compliant set → correct FAILs detected.

---

### PHASE 5: Output Layer (Modules M10, M11, M12)

**Goal**: Structured outputs consumable by planning officers.

#### 5.1 Compliance Scoring (M10)

- [ ] Aggregate rule verdicts into application-level report:
  - Per-rule: verdict, confidence, evidence trail
  - Summary: count of PASS / FAIL / NOT_ASSESSABLE
  - Overall risk indicator (not a single score — decomposable)
- [ ] Output as structured JSON (for API) and rendered Markdown (for human review)

#### 5.2 Minimum Evidence Request Generator (M11)

- [ ] For each NOT_ASSESSABLE rule, compute: "What is the minimum additional information needed to make this rule evaluable?"
- [ ] Implementation: set-difference between rule evidence requirements and available evidence
- [ ] Output: structured list of requests:

```json
{
  "rule_id": "R001",
  "missing": [
    {
      "attribute": "building_height",
      "acceptable_document_types": ["elevation drawing with dimension annotations"],
      "guidance": "Please provide an elevation drawing clearly showing the proposed ridge height with metric dimensions."
    }
  ]
}
```

- [ ] Guidance text templates stored in `configs/` — not hardcoded

#### 5.3 Decision Support Dashboard (M12)

- [ ] **Backend**: FastAPI
  - `POST /validate` — upload application set, trigger full pipeline
  - `GET /results/{application_id}` — retrieve compliance report
  - `GET /evidence/{rule_id}` — retrieve evidence trail for a specific rule
  - WebSocket for progress updates during processing
- [ ] **Frontend**: React
  - Application upload interface
  - Compliance report view with expandable rule verdicts
  - Evidence trail viewer (click a verdict → see source documents and extracted values)
  - Map view (Leaflet) showing site boundary, zone overlays
  - NOT_ASSESSABLE verdicts highlighted with minimum evidence requests
- [ ] **Priority**: The dashboard is a presentation layer, not a research contribution. Keep it functional, not polished. A simple table view with expandable rows is sufficient.

**Pipeline integration**: Register scoring and evidence request generation steps into `pipeline.py`. After this phase, `pipeline.run()` produces a complete `ComplianceReport`. The pipeline is now feature-complete.

#### Deliverable: End-to-end demo — upload a synthetic application set via the dashboard (or CLI), see compliance report with verdicts, evidence trails, and minimum evidence requests.

---

### PHASE 6: Final Integration & Ablation Preparation

**Goal**: The pipeline already works end-to-end (built incrementally since Phase 0). This phase hardens the integration and prepares for evaluation.

> **Why this phase is small**: The pipeline skeleton was created in Phase 0, and each subsequent phase registered its steps. By Phase 5, `python -m planproof.pipeline --input data/synthetic/compliant_001/ --config configs/default.yaml` already produces a complete compliance report. This phase adds polish, not plumbing.

- [ ] Verify ablation toggles work for all 7 configurations (see Phase 7 table)
- [ ] Each ablation configuration must produce valid output (see Section 7.1 for output contracts per config)
- [ ] End-to-end integration tests: run full pipeline on 3+ synthetic sets (compliant, non-compliant, edge-case), verify expected outputs against ground truth
- [ ] Performance profiling: identify bottlenecks (likely LLM calls — confirm caching works)
- [ ] Verify structured logging: every step's timing, inputs, and outputs are logged
- [ ] **Smoke test on real BCC data**: run full pipeline on 1-2 real application sets. Results won't have ground truth but should be manually inspectable for sanity.
- [ ] **Implement `FlatEvidenceProvider` adapter for Ablation B**: this adapter supplies evidence to the rule engine as a flat `list[ExtractedEntity]` (attribute name matching only, no graph traversal, no spatial relationship verification). It must be ready before evaluation runs in Phase 7. See Phase 7.1 Ablation B note for details.

#### Deliverable: All ablation configurations runnable. Integration tests green. Pipeline produces correct results on synthetic data.

---

### Pipeline Integration Points (per Phase)

Each phase registers its step(s) into the pipeline skeleton created in Phase 0. This table tracks what the pipeline can do after each phase:

| After Phase | Pipeline Steps Active | What You Can Run |
|---|---|---|
| Phase 0 | Empty skeleton | `pipeline.run()` → empty report |
| Phase 1 | (no pipeline steps — data only) | — |
| Phase 2 | Classify → Extract (text) → Extract (VLM) | Input docs → structured entities |
| Phase 3 | + Normalise → Populate SNKG | Input docs → populated graph |
| Phase 4 | + Reconcile → Gate → Assess → Evaluate rules | Input docs → per-rule verdicts |
| Phase 5 | + Score → Generate evidence requests | Input docs → full compliance report |
| Phase 6 | (hardening + ablation toggles) | All configs runnable |

---

### PHASE 7: Ablation Study & Evaluation

**Goal**: Rigorous experimental evaluation — this is what makes or breaks the dissertation.

#### 7.1 Ablation Configurations

| Config | Components Active | Isolates | Output Contract |
|---|---|---|---|
| **Naive Baseline** | LLM-only: concatenated OCR text → single GPT-4o prompt → PASS/FAIL per rule | Lower bound reference point | `list[RuleVerdict]` (forced PASS/FAIL, no NOT_ASSESSABLE) |
| **Strong Baseline** | LLM with CoT: rule-by-rule GPT-4o prompts, chain-of-thought, explicit evidence citation, structured JSON output | What prompt engineering alone achieves (without architecture) | `list[RuleVerdict]` (forced PASS/FAIL, with cited evidence) |
| **Ablation A** | Text extraction + SNKG (no rule engine) | KG contribution to evidence organisation | `list[ExtractedEntity]` + populated SNKG (no verdicts — measure evidence completeness and linkage quality) |
| **Ablation B** | Text extraction + rule engine (no SNKG) | Rule engine operating on a flat evidence list (no graph queries, no spatial joins) | `list[RuleVerdict]` (rules evaluate against flat entity list, missing graph-derived attributes like zone overlap) |
| **Ablation C** | Full pipeline minus confidence gating | Gating contribution to precision | Full output — but low-confidence extractions flow into rule evaluation unchecked |
| **Ablation D** | Full pipeline minus assessability engine | NOT_ASSESSABLE verdict contribution | All rules forced to PASS/FAIL (no NOT_ASSESSABLE) — matches traditional compliance tool behaviour |
| **Full System** | All components | Combined contribution | Full output including NOT_ASSESSABLE verdicts and minimum evidence requests |

**Ablation A note**: since this config produces no verdicts, evaluate it on **evidence quality metrics** (entity coverage, evidence-to-rule linkage completeness) rather than violation recall.

**Ablation B note**: the rule engine receives a flat `list[ExtractedEntity]` instead of querying the SNKG. Implement a `FlatEvidenceProvider` adapter that finds evidence by attribute name matching (no graph traversal, no spatial relationship verification). Rules requiring spatial grounding (e.g., zone-based rules) will receive incomplete evidence, isolating the graph's contribution.

#### 7.2 Evaluation Protocol

- [ ] Run each configuration on the **sealed test set only**
- [ ] Compute per-configuration:
  - **Primary**: Rule violation recall (on synthetic non-compliant set)
  - **Supporting**: Precision, F2 score, automation rate, assessability rate
  - Evidence consistency score, min evidence request quality (qualitative)
- [ ] Statistical significance: McNemar's test for paired comparisons (or bootstrap CI if sample too small)
- [ ] Report effect sizes alongside p-values — with ~20 test applications, confidence intervals will be wide. Frame this honestly.
- [ ] **Naive baseline implementation**:
  - Concatenate all OCR text from an application
  - Single GPT-4o call with a compliance prompt listing all rules
  - Parse structured JSON output
  - No graph, no reconciliation, no assessability
- [ ] **Strong baseline implementation**:
  - Same OCR text extraction as naive baseline
  - Separate GPT-4o call per rule with chain-of-thought prompting
  - Prompt includes: the rule text, instruction to cite specific evidence from the documents, instruction to flag uncertainty
  - Structured JSON output with: verdict, cited evidence, reasoning chain
  - **Domain knowledge parity**: the strong baseline prompt must include the same rule definitions (from `configs/rules/*.yaml`) that the rule engine uses. This ensures the comparison isolates *architectural* contribution (graph + reconciliation + assessability) rather than accidentally measuring "PlanProof has encoded domain rules but the baseline hasn't." Include rule thresholds, evidence requirements, and acceptable source types in the prompt context.
  - This isolates the contribution of the *architecture* (graph, reconciliation, assessability) vs. what sophisticated prompting achieves alone

#### 7.3 Addressing Small Sample Size (F4)

With ~20 test applications (~12 non-compliant, ~4 compliant, ~4 edge-case assuming 60/20/20 split), statistical power is limited. Mitigate this deliberately:

- [ ] **Evaluate per-rule, not just per-application**: each application tests multiple rules, so the effective sample size for rule-level metrics is larger (e.g., 20 apps × 7 rules = 140 rule evaluations). Report both application-level and rule-level metrics.
- [ ] **Use bootstrap confidence intervals** (1000+ resamples) rather than relying solely on McNemar's test, which assumes a larger sample.
- [ ] **Report effect sizes** (Cohen's h for proportions) alongside p-values. A large effect size with wide confidence intervals is still a meaningful finding — it says "the effect appears strong but more data is needed to confirm."
- [ ] **Qualitative error analysis**: for every misclassification (false positive, false negative, incorrect NOT_ASSESSABLE), write a paragraph explaining why it happened. With 20 apps, you can do this exhaustively. This is often more convincing to examiners than marginal p-values.
- [ ] **Frame honestly in the dissertation**: "This evaluation demonstrates feasibility and measures effect direction on a sample representative of BCC householder applications. Generalisability to other councils and application types requires larger-scale evaluation."

#### 7.4 Results Artefacts

- [ ] Per-configuration results stored as JSON in `data/results/`
- [ ] Confusion matrices per rule per configuration
- [ ] Precision-recall curves where applicable
- [ ] Bootstrap confidence interval plots for primary metrics
- [ ] Qualitative analysis of NOT_ASSESSABLE cases
- [ ] Per-misclassification error narrative (exhaustive for test set)

#### Deliverable: `make evaluate` runs all ablation configs, produces results tables and figures ready for the dissertation.

---

## 4. Cross-Cutting Concerns

### 4.1 Testing Strategy

| Layer | Test Type | Coverage Target | What to Test |
|---|---|---|---|
| Ingestion | Unit | 70% | Classifier rules, extraction parsing, prompt output parsing |
| Representation | Unit + Integration | 80% | Schema validation, Neo4j CRUD, Cypher queries return expected results |
| Reasoning | Unit + Integration | **90%** | Reconciliation logic, gating thresholds, assessability classification, rule evaluation — **this is the research contribution, test exhaustively** |
| Output | Unit | 60% | Report generation, evidence request formatting |
| Pipeline | Integration + E2E | — | Full pipeline on synthetic fixtures |

**CI enforcement**: Coverage targets are gates, not aspirations. Configure `pytest-cov` per package:

```ini
# pyproject.toml [tool.pytest.ini_options]
[tool.coverage.report]
fail_under = 70  # global floor

# Per-package overrides in CI script:
# pytest --cov=src/reasoning --cov-fail-under=90 tests/unit/reasoning/
# pytest --cov=src/representation --cov-fail-under=80 tests/unit/representation/
# pytest --cov=src/ingestion --cov-fail-under=70 tests/unit/ingestion/
```

### 4.2 Confidence Score Sourcing Strategy

Confidence scores are **load-bearing** in this architecture — they drive confidence gating (M7) and assessability decisions (M8). LLMs and VLMs do not produce calibrated probabilities natively. This section defines where confidence values come from.

**Strategy: Hybrid (heuristic baseline + empirical calibration)**

| Extraction Method | Initial Confidence Assignment | Calibration (after Phase 2) |
|---|---|---|
| `OCR_LLM` (text fields) | **Heuristic floor**: 0.85 for structured form fields, 0.70 for free-text extraction | Plot predicted confidence vs. actual accuracy on annotated BCC data. Adjust per entity type. |
| `OCR_LLM` (measurements) | **Heuristic floor**: 0.80 | Same calibration. Measurements from tables get +0.05 (more structured context). |
| `VLM_ZEROSHOT` | **Fixed**: 0.50 (reflecting known 50-60% VLM baseline accuracy) | Calibrate against annotated drawing ground truth from Label Studio. |
| `VLM_STRUCTURED` | **Fixed**: 0.60 (structured prompting expected to improve over zero-shot) | Same calibration set. Update after Stage 2 results. |
| `VLM_FINETUNED` | **Fixed**: 0.70 (only if Stage 3 is attempted) | Same calibration set. |
| `MANUAL` (ground truth) | **Fixed**: 1.0 | No calibration needed — this is the reference. |

**Implementation**:

- [ ] Phase 0: Assign heuristic floor values per extraction method (hardcoded in config, not in extraction code)
- [ ] Phase 2 checkpoint: After extraction is built, run on annotated BCC data. Plot reliability diagrams (predicted confidence vs. actual accuracy). Adjust thresholds in `configs/confidence_thresholds.yaml`.
- [ ] **Self-reported confidence** (asking the LLM "how confident are you?"): Do NOT use this as the primary signal — LLM self-confidence is poorly calibrated. However, log it as a secondary field for analysis in the dissertation.
- [ ] **Confidence is an extraction-method property, not a per-call property**: rather than asking each LLM call for a confidence score, assign confidence based on which method produced the extraction and calibrate that method's score empirically.

**Why this matters**: If confidence scores are garbage, the gating thresholds in M7 are meaningless, and the assessability engine in M8 makes arbitrary decisions about what's "sufficient." Getting this right is not optional.

### 4.3 Prompt Management

- All LLM/VLM prompts stored as versioned YAML files in `configs/prompts/`
- Each prompt has a version tag and a test fixture that validates expected output structure
- Never construct prompts via string concatenation in application code — use template rendering
- Log every LLM call: prompt hash, model, tokens, latency, raw response (to a separate log stream, not stdout)

### 4.4 Reproducibility

- All random operations use a configurable seed
- LLM calls use `temperature=0` and `seed` parameter where available
- Test set sealed with MD5 manifest
- Every evaluation run produces a metadata file: git commit hash, config used, timestamps, model versions
- Docker Compose for full environment reproducibility

### 4.5 Cost Control

- All LLM/VLM calls go through `LLMCache` (defined in Phase 0, Section 0.5) — keyed by `(prompt_hash, document_hash, model_version)`. No duplicate API calls.
- Use cheaper models (GPT-4o-mini, Mistral) for development iteration; GPT-4o for final evaluation runs only
- Track API spend per phase in a simple spreadsheet or script
- Ablation runs reuse cached responses from earlier runs — the cache makes re-evaluation nearly free

---

## 5. Recommended Execution Order

This deviates slightly from the proposal's 10-phase timeline to optimise for **risk reduction** and **iterative validation**.

```
PHASE 0  │ Foundation        │ Repo, CI, Neo4j, schemas (M4), LLM cache, pipeline skeleton
         │                   │ Validate: green CI, schemas importable, pipeline accepts input
         ▼
PHASE 1  │ Data              │ BCC data + synthetic generation + test sealing
         │                   │ Validate: ground truth labels loadable, test set sealed
         ▼
PHASE 2  │ Ingestion         │ M1 (classifier) + M2 (text extraction) + M3 (VLM stage 1-2)
         │                   │ Pipeline: input docs → ExtractedEntity objects
         │                   │ ⚠ CHECKPOINT 1: Review extraction quality + calibrate confidence scores
         ▼
PHASE 3  │ Representation    │ Normalisation + M5 (SNKG)
         │                   │ Pipeline: input docs → populated graph
         │                   │ Validate: Cypher queries return expected nodes/edges
         ▼
PHASE 4  │ Reasoning         │ M6 + M7 + M8 + M9
         │                   │ Pipeline: input docs → per-rule verdicts
         │                   │ ⚠ CHECKPOINT 2: Core research contribution works end-to-end
         ▼
PHASE 5  │ Output            │ M10 + M11 + M12
         │                   │ Pipeline: input docs → full compliance report (feature-complete)
         │                   │ Validate: full demo on synthetic data
         ▼
PHASE 6  │ Integration       │ Harden pipeline, verify ablation toggles, smoke-test real data
         │                   │ Validate: all 7 ablation configs runnable
         ▼
PHASE 7  │ Evaluation        │ Ablation study (7 configs) on sealed test set
         │                   │ Validate: all metrics computed, results tables ready
         ▼
WRITE-UP │ Dissertation      │ Chapters, figures, appendices
```

**Two critical checkpoints** are marked:

- **Checkpoint 1 (after Phase 2)**: Is extraction quality sufficient? Are confidence scores meaningfully calibrated? If VLM extraction is unusable, adjust confidence thresholds to route everything through NOT_ASSESSABLE. If text extraction quality is poor, investigate before building the reasoning layer on bad foundations.
- **Checkpoint 2 (after Phase 4)**: Does the core research contribution work end-to-end? Do correct verdicts appear for synthetic data? Does NOT_ASSESSABLE fire correctly for missing/conflicting evidence? If not, this is the last point to adjust scope (e.g., simplify C3/C4) before evaluation.

---

## 6. Challenges & Risks Flagged

### 6.1 High-Severity Concerns

| # | Challenge | Detail | Recommendation |
|---|---|---|---|
| **F1** | **Synthetic data realism** | The entire evaluation rests on synthetic non-compliant datasets. If these don't resemble real-world violations (layout, noise, formatting), the results may not generalise. The 10 real BCC sets cannot provide violation ground truth because you don't know the true compliance status. | Invest heavily in synthetic quality. Have a domain expert (BCC contact) review 3-5 synthetic sets for realism before generating the full batch. Document limitations honestly in the dissertation. |
| **F2** | **VLM extraction on real drawings** | The proposal correctly flags 50-60% VLM spatial accuracy. Real architectural drawings have scale bars, callouts, overlapping annotations, and variable quality. Zero-shot extraction will likely produce mostly unusable output. | This is already well-mitigated by the sub-experiment framing. Ensure confidence gating thresholds are set conservatively enough that bad VLM outputs don't leak into rule evaluation. Stage 3 (LoRA) is likely infeasible in dissertation timeline — don't over-invest. |
| **F3** | **Knowledge engineering bottleneck** | Encoding NPPF + BCC rules as graph nodes + rule templates is non-trivial manual work. Planning regulations are verbose, ambiguous, and context-dependent. Translating policy prose into deterministic evaluation logic requires deep domain understanding. | Start with the 3 quantitative rules (R001-R003) which have clear numeric thresholds. C1 (certificate) and C2 (address) are also tractable. C3 (boundary) and C4 (plan comparison) are significantly harder — be prepared to descope C4 if time is short. |
| **F4** | **Evaluation sample size** | ~60 application sets (~20 in test split) is small for statistical significance. McNemar's test or bootstrap CIs may show wide confidence intervals, making it hard to claim definitive improvements. | Acknowledge this as a limitation. Report effect sizes alongside p-values. Frame the contribution as demonstrating the approach's feasibility + the assessability concept, not as proving statistically robust superiority. |
| **F5** | **LLM baseline fairness** | A naive baseline (concatenated OCR → single GPT-4o prompt) is so weak that beating it proves very little. A dissertation examiner will scrutinise this. If the only comparison is against a strawman, the ablation loses credibility. | **Required** (not optional): implement both a naive baseline AND a strong baseline (rule-by-rule GPT-4o with CoT, evidence citation, structured output). The strong baseline isolates the architecture's contribution vs. what prompt engineering alone achieves. See Phase 7.1 for implementation details. |

### 6.2 Medium-Severity Concerns

| # | Challenge | Detail | Recommendation |
|---|---|---|---|
| **F6** | **C3 (Boundary Validation) complexity** | Comparing a hand-drawn or CAD site boundary from a planning drawing against OS/Land Registry parcel geometry requires: (a) extracting the polygon from the drawing, (b) geo-referencing it, (c) computing similarity against a reference polygon. Step (a) alone is a significant CV challenge. | Consider simplifying C3: instead of full polygon extraction, check whether the stated site area on the form approximately matches the Land Registry parcel area. This still tests the evidence reconciliation logic without requiring polygon extraction from drawings. |
| **F7** | **C4 (Plan Change Detection) scope** | Comparing proposed drawings against previously approved drawings for "material changes" is essentially a visual diff problem on architectural drawings — a research problem in its own right. | Descope to attribute-level comparison: extract key attributes (height, footprint, etc.) from both sets and flag differences. Do not attempt visual structural comparison. |
| **F8** | **Neo4j AuraDB Free limitations** | 200K nodes, 400K relationships. Should be fine for this scale, but monitor during population. | Track node/relationship counts. If approaching limits, consider pruning intermediate entities or switching to local Docker Neo4j. |

### 6.3 Architecture / Code Quality Concerns

| # | Challenge | Recommendation |
|---|---|---|
| **F9** | Module coupling risk: if the entity schema changes, every module downstream breaks | Schemas are defined in Phase 0 (Section 0.4) and frozen. Post-Phase 0 changes require updating all consuming modules + a regression test. Pydantic strict validation at module boundaries catches breakage immediately. |
| **F10** | LLM non-determinism breaks reproducibility | Always set temperature=0 and seed. Cache all LLM responses. Accept that exact reproduction may not be possible across API versions — document model version in every run's metadata. |
| **F11** | Dashboard effort vs. value | The dashboard is not a research contribution. If time is short, a CLI that outputs a Markdown report is sufficient for the dissertation. Only build the React dashboard if Phases 0-7 are complete and working. |

---

## 6.4 Boundary Verification Pipeline (Three-Tier)

> **Added**: 2026-03-31
> **Status**: Design complete, implementation not started
> **Motivation**: Real BCC (Birmingham) data analysis revealed that UK planning submissions use red-line boundaries on OS base maps — no lot/plan numbers, no survey coordinates, no cadastral identifiers. The boundary check must work with what's actually in the documents.

### Problem Statement

In UK householder planning applications, the applicant draws a **red line boundary** on an Ordnance Survey base map to define their site. The planning authority must verify this boundary is consistent with authoritative land records. If the red line extends beyond the property (encroachment) or includes highway land, the application has a fundamental problem.

### Three-Tier Design

#### Tier 1: VLM Visual Alignment Check (Primary — highest dissertation value)

**What it does:** Asks the VLM to examine the location plan and detect discrepancies between the red line and the OS property boundaries underneath.

| | Detail |
|---|---|
| **Input** | Location plan image (red line drawn on OS base map) |
| **Output** | Alignment verdict: ALIGNED / MISALIGNED / UNCLEAR; specific issues list; confidence score |
| **Method** | Structured VLM prompt asking: (1) Does red line follow OS property boundaries? (2) Does it include highway/road land? (3) Does it cut through neighbouring buildings? (4) Is enclosed area consistent with a single residential property? |
| **External data** | None — the OS base map is already in the document |
| **Novel contribution** | VLM-based replication of expert visual boundary verification on UK planning applications |

**Implementation tasks:**
- [ ] VLM prompt template: `configs/prompts/boundary_alignment.yaml`
- [ ] `BoundaryAlignmentExtractor` class in `ingestion/vlm/`
- [ ] `BoundaryAlignmentResult` schema (verdict, issues, confidence)
- [ ] `BoundaryCheckStep` pipeline step
- [ ] Unit tests with synthetic location plan images

#### Tier 2: Scale-Bar Grounded Measurement (Quantitative cross-check)

**What it does:** Uses the known scale (1:1250) and visible scale bar to estimate site dimensions, then compares against the declared site area on the application form.

| | Detail |
|---|---|
| **Input** | Location plan image + scale bar + application form (declared site area in hectares) |
| **Output** | Estimated frontage (m), depth (m), area (m²); discrepancy flag if >15% divergence from declared area |
| **Method** | VLM estimates approximate site dimensions using scale bar as reference; compare against 1APP form site area field |
| **External data** | None — uses submitted application form |

**Implementation tasks:**
- [ ] VLM prompt template: `configs/prompts/boundary_measurement.yaml`
- [ ] `ScaleBarMeasurementExtractor` class in `ingestion/vlm/`
- [ ] Area comparison logic in boundary check step
- [ ] Extract declared site area from application form (M2 text extraction enhancement)

#### Tier 3: Address Cross-Reference (Sanity check)

**What it does:** Resolves the site address to a known property, pulls the INSPIRE index polygon from HM Land Registry, and compares the approximate area.

| | Detail |
|---|---|
| **Input** | Site address + postcode (extracted from location plan or application form) |
| **Output** | UPRN match confirmation; INSPIRE polygon area (m²); area ratio vs Tier 2 estimate; over-claiming flag if ratio >1.5x |
| **Method** | Address → UPRN (OS Places API free tier) → INSPIRE index polygon (free bulk download from HMLR) → area comparison |
| **External data** | OS Places API (free, 1000 tx/month); HMLR INSPIRE polygons (free bulk download) |

**Implementation tasks:**
- [ ] `AddressResolver` class in `infrastructure/` (OS Places API client)
- [ ] `INSPIREPolygonLookup` class in `representation/` (HMLR data loader)
- [ ] `BoundaryReferenceProvider` protocol in `interfaces/`
- [ ] Area comparison and over-claiming detection logic
- [ ] Fallback: if API unavailable, Tier 3 returns INSUFFICIENT_DATA (non-blocking)

### Integration with SABLE

The boundary verification produces evidence that feeds into SABLE:
- **New rule**: `R004` (or `C3` enhancement) — site boundary consistency
- **SABLE gates assessability**: Are Tier 1/2/3 results available and trustworthy enough to evaluate the boundary rule?
- **New evidence requirement**: `site_boundary_alignment` with acceptable sources `[VLM_BOUNDARY, SCALE_MEASUREMENT, ADDRESS_CROSSREF]`
- **Concordance**: If all three tiers agree → high concordance; if Tier 1 says ALIGNED but Tier 3 flags over-claiming → CONFLICTING

### Key Design Decisions

1. **Tier 1 is primary because the reference data is already in the document** — no external dependencies, no API costs, no data licences
2. **VLM accuracy is sufficient** because planning officers also do a visual check — gross discrepancy detection is the actual requirement, not survey-grade precision
3. **Tier 3 is optional/degradable** — if OS Places API is unavailable, the system still produces Tier 1 + Tier 2 results
4. **UK-specific design** — this pipeline is designed for UK Planning Portal submissions with OS base maps. Australian (lot/plan) or US (plat map) systems would need different Tier 1 prompts and Tier 3 data sources

### Limitations (honest framing for dissertation)

- VLM catches gross discrepancies but not 1-2m marginal boundary offsets
- Scan/photo quality and red-line colour fading affect Tier 1 reliability
- Cannot detect cases where the OS base map is outdated relative to recent boundary changes
- INSPIRE polygons are approximate ("general boundaries" under Land Registration Act 2002 s.60)
- Tier 2 scale-bar measurement is approximate — VLM spatial reasoning is not pixel-accurate

### Future Work (deferred)

- **Multi-plan consistency**: Compare red line on location plan (1:1250) vs block plan (1:500) — should show same boundary
- **Automated red-line segmentation**: Train a semantic segmentation model to extract precise red-line polygon coordinates from location plans
- **OS MasterMap vector overlay**: If council-grade MasterMap access available, render authoritative boundary polygon on top of submitted plan for direct geometric comparison

---

## 7. Descoping Strategy (if needed)

If time pressure forces scope reduction, cut in this order (last item cut first):

1. **Keep**: Assessability engine, SNKG, rule engine, evidence reconciliation, ablation study — this is the research contribution
2. **Keep**: R001–R003 + C1 + C2 (Tier 1 rules) — these are tractable and sufficient to demonstrate the system
3. **Simplify**: Dashboard → CLI that outputs a Markdown compliance report
4. **Simplify**: C4 (plan change detection) → attribute-level diff only (already the default in Phase 4 Tier 2 specification)
5. **Simplify**: Boundary Verification → Tier 1 (VLM visual alignment) only, drop Tier 2 (scale-bar measurement) and Tier 3 (address cross-reference) if time-constrained
6. **Drop**: C4 entirely if attribute extraction from approved plans proves unreliable — the NOT_ASSESSABLE verdict for "approved plan lacks dimensions" is itself a valid result
7. **Drop**: VLM Stage 3 (LoRA fine-tuning)
8. **Drop**: Leaflet map visualisation
9. **Last resort**: Reduce synthetic dataset from 60 to 40 application sets

---

## 8. Definition of Done (per Phase)

Each phase is only "done" when:

- [ ] All code passes `make lint` + `make typecheck` + `make test`
- [ ] New modules have unit tests covering core logic paths
- [ ] Integration tests pass on at least one synthetic fixture
- [ ] Changes are committed to a feature branch and merged via PR
- [ ] README / module docstrings updated if new setup steps are required
- [ ] No hardcoded API keys, paths, or magic numbers
