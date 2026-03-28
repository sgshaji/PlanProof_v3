# Phase 2a Design — Document Classifier (M1) + Text Extraction Pipeline (M2)

> **Date**: 2026-03-26
> **Scope**: M1 (Document Classifier) + M2 (Text Extraction Pipeline)
> **Out of scope**: M3 (VLM Pipeline) — separate design to follow
> **Approach**: Two-Path Router — text path (pdfplumber + Groq) and vision path (GPT-4o)

---

## 1. Overview

Phase 2a implements the first two modules of the Ingestion Layer. Given a directory of planning application documents, M1 classifies each file by type and text-layer availability, then M2 extracts structured entities through one of two paths depending on the classification.

```
input_dir/
  ├── form.pdf
  ├── elevation.png
  ├── site_plan_scan.png
  └── certificate.pdf

         │
         ▼
  ┌──────────────────┐
  │  M1: Classifier   │  → ClassifiedDocument (type + has_text_layer)
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │  M2: Extraction   │  → routes per document:
  │                    │     text_layer=true  → pdfplumber → Groq LLM
  │                    │     text_layer=false → rasterise → GPT-4o vision
  └──────┬───────────┘
         │
         ▼
  list[ExtractedEntity]   → stored in PipelineContext["entities"]
```

Both extraction paths produce identical `ExtractedEntity` output. Downstream pipeline steps (normalisation, reconciliation, assessability) are agnostic to which path was used.

---

## 2. Design Principles

1. **Protocol-first extensibility**: All components implement existing Protocols (`DocumentClassifier`, `OCRExtractor`, `EntityExtractor`). New implementations can be swapped via `bootstrap.py` config without touching downstream code.

2. **Scalability to next phases**: Infrastructure built here is reused by M3 (VLM):
   - Vision path client and image prompting → reused for spatial drawing analysis
   - Prompt template system → new templates for VLM-specific extraction
   - Rasterisation utility → shared by both M2 vision and M3
   - Entity parsing logic → identical output type regardless of extraction method

3. **Plugin-style extensibility**:
   - New document types → add a regex pattern to the classifier config + a prompt template YAML
   - New entity types → add to `EntityType` enum + update relevant prompt templates
   - New extraction providers → implement Protocol, register in `bootstrap.py`
   - New LLM providers → already handled by `LLMClient` Protocol + `CachedLLMClient`

4. **Cost efficiency**: Groq (free) handles text-layer documents. GPT-4o (paid) only invoked for scanned/image documents. LLM cache ensures each document is only processed once.

5. **Idempotency**: `temperature=0` on all providers, deterministic prompt construction, cached responses. Same input always produces same output.

---

## 3. M1 — Document Classifier

### 3.1 Responsibility

Given a file path, determine:
- `doc_type`: FORM, DRAWING, REPORT, CERTIFICATE, OTHER
- `has_text_layer`: whether the file contains extractable text (routing signal for M2)
- `confidence`: how certain the classification is (0.0–1.0)

### 3.2 Implementation — Rule-Based, Three-Signal Cascade

No LLM involvement. The classifier is intentionally simple — it is not the research contribution.

**Signal 1 — Filename pattern matching (high confidence)**

A configurable regex map from filename patterns to document types:

```yaml
# configs/classifier_patterns.yaml
patterns:
  - pattern: "(?i)(form|application)"
    doc_type: FORM
    confidence: 0.90
  - pattern: "(?i)(elevation|section)"
    doc_type: DRAWING
    confidence: 0.90
  - pattern: "(?i)(site.?plan|block.?plan)"
    doc_type: DRAWING
    confidence: 0.90
  - pattern: "(?i)(floor.?plan)"
    doc_type: DRAWING
    confidence: 0.90
  - pattern: "(?i)(certificate|lawful)"
    doc_type: CERTIFICATE
    confidence: 0.90
  - pattern: "(?i)(report|statement|assessment)"
    doc_type: REPORT
    confidence: 0.85
```

Adding new patterns requires no code changes — just edit the YAML.

**Signal 2 — Text density heuristic (medium confidence)**

Open the file with `pdfplumber` (if PDF). Count characters per page:
- High density (>200 chars/page average) → FORM or REPORT. `has_text_layer = True`.
- Low density (<50 chars/page average) → likely DRAWING. `has_text_layer = True` but sparse.
- Zero text → scanned document or image. `has_text_layer = False`.

For image files (PNG, JPG, TIFF): `has_text_layer = False` by definition.

**Signal 3 — Image feature heuristic (low confidence, fallback)**

For files with no text layer and no filename match:
- Aspect ratio: landscape → DRAWING, portrait → scanned FORM
- File size heuristic: large image → DRAWING, small → OTHER

**Confidence scoring:**
- Filename match alone → 0.90
- Filename + text density agreement → 0.95
- Text density only (no filename match) → 0.75
- Image heuristic fallback → 0.60–0.70
- No signals match → OTHER with confidence 0.50

### 3.3 Schema Change

Add `has_text_layer: bool` to `ClassifiedDocument`:

```python
class ClassifiedDocument(BaseModel):
    file_path: str
    doc_type: DocumentType
    confidence: float  # 0.0–1.0
    has_text_layer: bool  # NEW — routing signal for M2
```

### 3.4 Extensibility

- New document types: add enum value to `DocumentType`, add regex pattern to YAML, add prompt template for M2.
- New classification signals: add a method to the classifier, update confidence aggregation. Protocol interface unchanged.
- Replace with ML classifier later: implement `DocumentClassifier` Protocol with an ML model, swap in `bootstrap.py`.

---

## 4. M2 — Text Extraction Pipeline

### 4.1 Responsibility

Given a `ClassifiedDocument`, extract structured `ExtractedEntity` objects. Route through text path or vision path based on `has_text_layer`.

### 4.2 Text Path — pdfplumber + Groq

**Step 1: Raw text extraction**

```
PDF file → pdfplumber → RawTextResult
```

- Extract text page-by-page using `pdfplumber`.
- Preserve page numbers for source attribution.
- Output: `RawTextResult(text, source_document, source_pages, extraction_method="PDFPLUMBER")`

**Step 2: LLM structured extraction**

```
RawTextResult → prompt template (by doc type) → Groq (llama-3.1-70b) → JSON → list[ExtractedEntity]
```

- Load prompt template from `configs/prompts/{doc_type}_extraction.yaml`
- Inject raw text into the prompt's `{text}` placeholder
- Call Groq via `CachedLLMClient` with `temperature=0`
- Parse JSON response into `ExtractedEntity` objects
- Set `extraction_method=OCR_LLM` on all entities

**Extensibility**: Swap pdfplumber for pymupdf by implementing the same `OCRExtractor` Protocol. Change is config-level — install `pip install -e ".[pdf]"` and update the factory in `bootstrap.py`.

### 4.3 Vision Path — GPT-4o

**Step 1: Rasterisation (if needed)**

```
PDF (no text layer) → rasterise to PNG
Image file (PNG/JPG) → use directly
```

- For synthetic data: `_scan.png` variants already exist — use them directly.
- For real BCC data: thin rasterisation utility wrapping `pymupdf` when available, or Pillow for image format conversion.
- The rasteriser is a utility function, not a Protocol — it's an internal implementation detail of the vision path.

**Step 2: Vision extraction**

```
Image(s) → prompt template (by doc type) → GPT-4o vision → JSON → list[ExtractedEntity]
```

- Load vision-specific prompt template from `configs/prompts/{doc_type}_extraction.yaml` (same template can handle both text and vision via conditional sections, or separate vision templates if needed)
- Send image(s) to GPT-4o via OpenAI client's vision API
- Call goes through `CachedLLMClient` — cache key includes image hash
- Parse JSON response into `ExtractedEntity` objects
- Set `extraction_method=OCR_LLM` on all entities

**Note on extraction_method**: Both paths use `OCR_LLM` because this is text/form-level extraction, not spatial drawing analysis. M3 (VLM) will use `VLM_ZEROSHOT` / `VLM_STRUCTURED` / `VLM_FINETUNED` when it's implemented later.

**Extensibility**: The vision path infrastructure (image handling, GPT-4o client, image prompting, response parsing) is reused directly by M3. M3 adds spatial-specific prompts and different `ExtractionMethod` tags but uses the same plumbing.

### 4.4 Prompt Templates

Four YAML templates in `configs/prompts/`:

| Template | Document Types | Key Entities |
|----------|---------------|--------------|
| `form_extraction.yaml` | FORM | ADDRESS, MEASUREMENT, CERTIFICATE, OWNERSHIP |
| `report_extraction.yaml` | REPORT | MEASUREMENT, BOUNDARY, ZONE |
| `certificate_extraction.yaml` | CERTIFICATE | CERTIFICATE (type, issuer, date, property ref) |
| `drawing_extraction.yaml` | DRAWING (vision path) | MEASUREMENT (dimensions, annotations, scale) |

Each template contains:
- `system_message`: role and context for the LLM
- `user_message_template`: with `{text}` or `{image_description}` placeholder
- `output_schema`: exact JSON schema the LLM must return
- `few_shot_examples`: 1–2 examples of input/output pairs for grounding

**Extensibility**: New document types → new YAML template. New entity types → update relevant templates' output schemas. No code changes required.

### 4.5 Confidence Assignment

Initial confidence values come from `configs/default.yaml` thresholds, keyed by `(extraction_method, entity_type)`:

```yaml
OCR_LLM:
  ADDRESS: 0.85
  MEASUREMENT: 0.80
  CERTIFICATE: 0.90
  BOUNDARY: 0.75
  ZONE: 0.85
  OWNERSHIP: 0.80
```

These are **pre-calibration defaults**. Per the implementation plan, calibration happens after Phase 2 is complete — run extraction on annotated BCC data, plot reliability diagrams, adjust thresholds empirically.

### 4.6 Error Handling

- **Malformed LLM JSON response**: Log the raw response, attempt partial parsing (extract entities that are valid, skip malformed ones). Step returns `StepResult(status=PARTIAL)`.
- **pdfplumber fails to open file**: Log error, skip file. If all files fail, step returns `StepResult(status=FAILED)`.
- **Vision API error** (rate limit, timeout): Log error, skip file. LLM cache prevents re-billing on retry.
- **Empty extraction** (LLM returns no entities): Valid result — some documents legitimately contain no extractable entities of interest. Log as informational, not error.
- **Principle**: Extraction failures become NOT_ASSESSABLE verdicts automatically. A failed extraction produces no entities, which downstream assessability treats as missing evidence.

---

## 5. Pipeline Integration

### 5.1 Step Execution Flow

```python
# Step 1: Classification
ClassificationStep.execute(context):
    input_dir = context["metadata"]["input_dir"]
    files = list_files(input_dir)  # PDF, PNG, JPG, TIFF
    classified = [classifier.classify(f) for f in files]
    context["classified_documents"] = classified
    return StepResult(step_name="classification", status=StepStatus.SUCCESS,
                      outputs=classified, errors=[], duration_ms=...)

# Step 2: Text Extraction
TextExtractionStep.execute(context):
    classified_docs = context["classified_documents"]
    all_entities: list[ExtractedEntity] = []
    errors: list[str] = []
    for doc in classified_docs:
        try:
            if doc.has_text_layer:
                raw = ocr_extractor.extract_text(Path(doc.file_path))
                entities = entity_extractor.extract_entities(raw)
            else:
                entities = vision_extractor.extract_from_image(
                    Path(doc.file_path), doc.doc_type
                )
            all_entities.extend(entities)
        except Exception as e:
            errors.append(f"{doc.file_path}: {e}")
    context["entities"] = all_entities
    status = StepStatus.SUCCESS if not errors else (
        StepStatus.PARTIAL if all_entities else StepStatus.FAILED
    )
    return StepResult(step_name="text_extraction", status=status,
                      outputs=all_entities, errors=errors, duration_ms=...)
```

**Note on StepResult**: The codebase has two `StepResult` types — `schemas.pipeline.StepResult` (Pydantic BaseModel with `status: StepStatus`) and `interfaces.pipeline.StepResult` (TypedDict with `success: bool`). The pipeline steps should return the Pydantic `StepResult` from `schemas.pipeline` which supports the three-state SUCCESS/PARTIAL/FAILED semantics. The TypedDict version in `interfaces.pipeline` should be reconciled during implementation — either removed or aligned.

### 5.2 PipelineContext Changes

Add one new key to `PipelineContext` TypedDict:

```python
class PipelineContext(TypedDict, total=False):
    classified_documents: list[ClassifiedDocument]  # NEW — M1 output, M2 input
    entities: list[ExtractedEntity]                 # Already defined — M2 output
    graph_ref: Any
    verdicts: list[RuleVerdict]
    assessability_results: list[AssessabilityResult]
    metadata: dict[str, Any]
```

### 5.3 Bootstrap Wiring

Replace stubs with concrete implementations:

```python
# In bootstrap.py — replace stub factories
def _create_classifier(config: PipelineConfig) -> DocumentClassifier:
    return RuleBasedClassifier(patterns_path=config.configs_dir / "classifier_patterns.yaml")

def _create_ocr(config: PipelineConfig) -> OCRExtractor:
    return PdfPlumberExtractor()

def _create_entity_extractor(config: PipelineConfig, llm: CachedLLMClient) -> EntityExtractor:
    return LLMEntityExtractor(
        llm=llm,
        prompts_dir=config.configs_dir / "prompts",
    )
```

The `_StubVLM` remains as-is until M3 is designed and implemented.

### 5.4 File Organisation

```
src/planproof/ingestion/
    ├── __init__.py
    ├── classifier.py          # RuleBasedClassifier — implements DocumentClassifier Protocol
    ├── text_extractor.py      # PdfPlumberExtractor — implements OCRExtractor Protocol
    ├── vision_extractor.py    # GPT4oVisionExtractor — vision path extraction
    ├── entity_extractor.py    # LLMEntityExtractor — implements EntityExtractor Protocol
    └── rasteriser.py          # PDF/image → PNG conversion utility

configs/
    ├── prompts/
    │   ├── form_extraction.yaml
    │   ├── report_extraction.yaml
    │   ├── certificate_extraction.yaml
    │   └── drawing_extraction.yaml
    └── classifier_patterns.yaml   # NEW — regex patterns for M1
```

---

## 6. Testing Strategy

### 6.1 Unit Tests

| Component | Test Approach |
|-----------|--------------|
| `RuleBasedClassifier` | Feed known filenames + sample PDFs, assert correct `doc_type` and `has_text_layer` |
| `PdfPlumberExtractor` | Feed a text-layer PDF fixture, assert `RawTextResult` contains expected text |
| `LLMEntityExtractor` | Mock the `CachedLLMClient`, feed canned JSON responses, assert correct `ExtractedEntity` parsing |
| `GPT4oVisionExtractor` | Mock the OpenAI client, feed canned vision responses, assert correct entity parsing |
| Prompt templates | Validate YAML loads, placeholders resolve, output schema is valid JSON Schema |

### 6.2 Integration Test

Feed a complete synthetic application set through `ClassificationStep` → `TextExtractionStep`. Compare extracted entities against `ground_truth.json`:
- Entity types match
- Values within tolerance
- Source documents correctly attributed
- Page numbers correct

This is the primary quality gate for Phase 2a.

### 6.3 Determinism Test

Run the same synthetic set twice. Assert identical `ExtractedEntity` output — validates caching, temperature=0, and deterministic prompt construction.

### 6.4 Cross-Path Consistency Test

For synthetic documents that have both PDF and PNG variants, run both through their respective paths. Compare extracted entities — values should agree within tolerance. Disagreements flag prompt or extraction quality issues.

---

## 7. Dependencies

### New dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `pdfplumber` | Text-layer PDF extraction | Pure Python, no build issues |

### Existing dependencies (no changes)

- `openai` — GPT-4o vision API
- `groq` — Groq text extraction API
- `Pillow` — Image handling, basic rasterisation
- `pydantic` — Entity schemas, prompt config validation
- `pyyaml` — Prompt templates, classifier patterns

### Deferred dependencies

- `pymupdf` — PDF rasterisation for real scanned PDFs. Install via `pip install -e ".[pdf]"` when needed. The rasteriser utility has a clean interface for swapping in pymupdf later.

---

## 8. Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Classifier approach | Rule-based, no LLM | Not the research contribution. Simple, fast, deterministic. |
| Text extraction library | pdfplumber | Pure Python, no ARM64 build issues. Easy swap to pymupdf later. |
| Text LLM provider | Groq (llama-3.1-70b) | Free tier, fast, good structured JSON output. |
| Vision LLM provider | OpenAI GPT-4o | Best vision quality, cached to control cost. |
| Prompt management | One YAML template per doc type | Tailored extraction per document structure. New types = new YAML. |
| Rasterisation scope | Pragmatic — use existing PNGs, thin utility for future | Synthetic data already has PNG variants. Full PDF rasterisation deferred. |
| M3 VLM scope | Separate design | Different risk profile (research vs engineering). Decoupled timeline. |
