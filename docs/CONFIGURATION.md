# PlanProof — Configuration Guide

Every configurable aspect of PlanProof is documented here. No configuration lives in code — it's all in `.env`, YAML files, or Docker environment variables.

---

## 1. Choosing an LLM Provider

PlanProof supports multiple LLM providers. Switch between them with a single config change.

| Provider | Cost | API Key Needed | Quality | Best For |
|----------|------|---------------|---------|----------|
| **Ollama** (default) | **Free** | No | Good (Llama 3.1, Mistral) | Development, iteration, offline work |
| **Groq** | **Free tier** (30 RPM) | Yes (free) | Good (Llama 3.1 70B) | Fast cloud inference during development |
| **OpenAI** | Paid (~$2.50/M tokens) | Yes (paid) | Excellent (GPT-4o) | Final evaluation runs, VLM (drawing analysis) |

**Recommendation:**
- **Day-to-day development**: Use Ollama (runs inside Docker, no key needed)
- **Final ablation study**: Switch to OpenAI GPT-4o for best extraction quality

### How to Switch Providers

In your `.env` file:
```bash
# Ollama (default — free, no API key)
PLANPROOF_LLM_PROVIDER=ollama
PLANPROOF_LLM_MODEL=llama3.1

# Groq (free tier — needs free API key from https://console.groq.com)
PLANPROOF_LLM_PROVIDER=groq
PLANPROOF_LLM_MODEL=llama-3.1-70b-versatile
PLANPROOF_LLM_API_KEY=gsk_your_key_here

# OpenAI (paid — needs API key from https://platform.openai.com)
PLANPROOF_LLM_PROVIDER=openai
PLANPROOF_LLM_MODEL=gpt-4o
PLANPROOF_LLM_API_KEY=sk-your-key-here
```

No code changes. Just change the env vars and restart.

---

## 2. Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in your values. This file is **never committed** (gitignored).

```bash
# LLM Provider (default: ollama — free, no API key)
PLANPROOF_LLM_PROVIDER=ollama
PLANPROOF_LLM_MODEL=llama3.1
PLANPROOF_LLM_API_KEY=                    # Only needed for groq/openai

# Neo4j connection (defaults work with Docker Compose)
# PLANPROOF_NEO4J_URI=bolt://localhost:7687
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PLANPROOF_LLM_PROVIDER` | No | `ollama` | LLM provider: `ollama`, `groq`, or `openai` |
| `PLANPROOF_LLM_MODEL` | No | `llama3.1` | Model name for the chosen provider |
| `PLANPROOF_LLM_API_KEY` | Only for groq/openai | `""` | API key (not needed for Ollama) |
| `PLANPROOF_OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `PLANPROOF_VLM_PROVIDER` | No | `ollama` | VLM provider (can differ from LLM) |
| `PLANPROOF_VLM_MODEL` | No | `llava` | VLM model name |
| `PLANPROOF_NEO4J_URI` | No | `bolt://localhost:7687` | Neo4j Bolt connection URI |
| `PLANPROOF_NEO4J_USER` | No | `neo4j` | Neo4j username |
| `PLANPROOF_NEO4J_PASSWORD` | No | `planproof-dev` | Neo4j password |

> **Docker note**: When running inside Docker Compose, Neo4j and Ollama URLs are automatically set to use container-internal addresses. With the default Ollama provider, **no configuration is needed at all** — just `cp .env.example .env` and go.

---

## 3. Pipeline Configuration (`configs/default.yaml`)

The main pipeline configuration file. Environment variables with `PLANPROOF_` prefix override these values.

```yaml
# LLM Provider
llm_provider: "ollama"            # ollama | groq | openai
llm_model: "llama3.1"
llm_api_key: ""                   # Set via PLANPROOF_LLM_API_KEY for groq/openai
ollama_base_url: "http://localhost:11434"

# Paths
cache_dir: "data/.llm_cache"      # LLM response cache location
configs_dir: "configs"             # Where to find rule/prompt YAML files

# Performance
max_concurrent_llm_calls: 5       # Semaphore limit for parallel API calls

# Confidence thresholds (see Section 3)
confidence:
  thresholds:
    OCR_LLM:
      ADDRESS: 0.85
      MEASUREMENT: 0.80
      # ... (see configs/default.yaml for full list)

# Ablation toggles (see Section 5)
ablation:
  use_snkg: true
  use_rule_engine: true
  use_confidence_gating: true
  use_assessability_engine: true
  use_evidence_reconciliation: true
  use_vlm: true
```

---

## 4. Confidence Thresholds (`configs/confidence_thresholds.yaml`)

Controls the minimum confidence score required for an extracted entity to be considered "trustworthy" by the confidence gating module (M7).

**Structure**: `extraction_method → entity_type → threshold`

```yaml
thresholds:
  OCR_LLM:           # Text extracted via OCR + LLM structured extraction
    ADDRESS: 0.85     # High bar — addresses must be reliable for C2
    MEASUREMENT: 0.80 # Numeric values need reasonable confidence
    CERTIFICATE: 0.90 # Certificate type is critical for C1
    BOUNDARY: 0.80
    ZONE: 0.85
    OWNERSHIP: 0.85

  VLM_ZEROSHOT:       # Zero-shot GPT-4o on architectural drawings
    MEASUREMENT: 0.70 # Higher bar than structured because less reliable
    BOUNDARY: 0.75
    ADDRESS: 0.80     # Drawing title blocks are often hard to read
    ZONE: 0.80

  VLM_STRUCTURED:     # GPT-4o with structured prompting (Stage 2)
    MEASUREMENT: 0.60 # Lower bar — structured prompting improves accuracy
    BOUNDARY: 0.65
    ADDRESS: 0.70
    ZONE: 0.70

  VLM_FINETUNED:      # LoRA fine-tuned LLaVA (Stage 3, stretch goal)
    MEASUREMENT: 0.50
    BOUNDARY: 0.55
    ADDRESS: 0.60
    ZONE: 0.60

  MANUAL:             # Ground truth annotations — always trusted
    ADDRESS: 0.30     # Low threshold = always passes gating
    MEASUREMENT: 0.30
    CERTIFICATE: 0.30
    BOUNDARY: 0.30
    ZONE: 0.30
    OWNERSHIP: 0.30
```

**How thresholds work**: An `ExtractedEntity` with `confidence < threshold` for its method+type combination is flagged as `LOW_CONFIDENCE`. The assessability engine treats low-confidence entities as missing evidence → rule becomes NOT_ASSESSABLE.

**Calibration**: These are initial heuristic values. After Phase 2, plot reliability diagrams on annotated data and adjust empirically. See Implementation Plan Section 4.2.

---

## 5. Rule Definitions (`configs/rules/*.yaml`)

Each compliance rule is a YAML file. The rule engine loads all `*.yaml` files from this directory at startup.

### Schema

```yaml
rule_id: "R001"                              # Unique identifier
description: "Human-readable rule description"
policy_source: "BCC Local Plan Policy DM30"  # Legal source for traceability
evaluation_type: "numeric_threshold"          # Maps to a registered evaluator class
parameters:                                   # Evaluator-specific parameters
  attribute: "building_height"
  operator: "<="
  threshold: 8.0
  unit: "metres"
required_evidence:                            # What the assessability engine checks
  - attribute: "building_height"
    acceptable_sources: ["DRAWING", "REPORT"]
    min_confidence: 0.80
    spatial_grounding: null                   # null = no spatial check needed
  - attribute: "zone_category"
    acceptable_sources: ["FORM", "EXTERNAL_DATA"]
    min_confidence: 0.90
    spatial_grounding: "LOCATED_WITHIN"       # Requires spatial relationship verification
```

### Available Evaluation Types

| `evaluation_type` | Evaluator | Parameters | Used By |
|---|---|---|---|
| `numeric_threshold` | `NumericThresholdEvaluator` | `attribute`, `operator` (`<=`, `>=`, `<`, `>`, `==`), `threshold`, `unit` | R001 (height), R002 (garden) |
| `ratio_threshold` | `RatioThresholdEvaluator` | `numerator_attribute`, `denominator_attribute`, `operator`, `threshold` | R003 (site coverage) |
| `enum_check` | `EnumCheckEvaluator` | `attribute`, `valid_values` (list) | C1 (certificate type) |
| `fuzzy_string_match` | `FuzzyMatchEvaluator` | `attribute_a`, `attribute_b`, `min_similarity` (0-1) | C2 (address consistency) |
| `numeric_tolerance` | `NumericToleranceEvaluator` | `attribute_a`, `attribute_b`, `tolerance_pct` | C3 (boundary area) |
| `attribute_diff` | `AttributeDiffEvaluator` | `attributes` (list of attribute names to compare) | C4 (plan changes) |

### Adding a New Rule (No Code Change)

If the evaluation logic matches an existing type:

1. Create `configs/rules/r004_your_rule.yaml`
2. Set `evaluation_type` to one of the existing types
3. Fill in `parameters` and `required_evidence`
4. Done — the system picks it up automatically on next run

If you need new evaluation logic:

1. Create a new evaluator class in `src/planproof/reasoning/evaluators/`
2. Register it in `src/planproof/bootstrap.py`:
   ```python
   RuleFactory.register_evaluator("your_type", YourEvaluator)
   ```
3. Reference `evaluation_type: "your_type"` in the YAML

### Current Rules

| File | Rule | Type |
|------|------|------|
| `r001_max_height.yaml` | Building height ≤ 8m | `numeric_threshold` |
| `r002_rear_garden.yaml` | Rear garden ≥ 10m | `numeric_threshold` |
| `r003_site_coverage.yaml` | Site coverage ≤ 50% | `ratio_threshold` |
| `c001_certificate_type.yaml` | Certificate A/B/C/D validity | `enum_check` |
| `c002_address_consistency.yaml` | Form address matches drawing | `fuzzy_string_match` |
| `c003_boundary_validation.yaml` | Stated area ±15% of Land Registry | `numeric_tolerance` |
| `c004_plan_change.yaml` | Proposed vs approved attributes | `attribute_diff` |

---

## 6. Ablation Configurations (`configs/ablation/*.yaml`)

Each file defines which pipeline components are active for one ablation study run. The evaluation runner (Phase 7) iterates through all files in this directory.

### Schema

```yaml
# configs/ablation/full_system.yaml
use_snkg: true
use_rule_engine: true
use_confidence_gating: true
use_assessability_engine: true
use_evidence_reconciliation: true
use_vlm: true
```

### Current Configurations

| File | What's Enabled | What it Tests |
|------|---------------|---------------|
| `full_system.yaml` | Everything | Combined system performance |
| `naive_baseline.yaml` | Only rule_engine | LLM-only lower bound |
| `strong_baseline.yaml` | snkg + rule_engine + vlm | What prompt engineering achieves |
| `ablation_a.yaml` | snkg only (no rule engine) | KG contribution to evidence quality |
| `ablation_b.yaml` | rule_engine only (no snkg) | Rules without graph context |
| `ablation_c.yaml` | Everything minus confidence_gating | Gating contribution to precision |
| `ablation_d.yaml` | Everything minus assessability_engine | NOT_ASSESSABLE contribution |

---

## 7. Prompt Templates (`configs/prompts/*.yaml`)

LLM and VLM prompt templates used by the extraction pipeline. Versioned in git, never hardcoded in application code.

### Schema

```yaml
# configs/prompts/text_entity_extraction.yaml
version: "1.0"
model: "gpt-4o"
temperature: 0                    # WHY: Deterministic output for cache consistency
system_prompt: |
  You are a planning document entity extractor. Extract structured
  entities from the provided text. Return JSON matching the schema.
user_prompt_template: |
  Extract all planning entities from the following document text.
  Document type: {doc_type}

  Text:
  {text}
output_schema:
  type: array
  items:
    type: object
    properties:
      entity_type: { type: string, enum: [ADDRESS, MEASUREMENT, CERTIFICATE, BOUNDARY, ZONE, OWNERSHIP] }
      value: { type: string }
      unit: { type: string }
      confidence: { type: number, minimum: 0, maximum: 1 }
```

**Placeholder files to create during Phase 2:**
- `text_entity_extraction.yaml` — OCR + LLM entity extraction
- `vlm_zeroshot.yaml` — VLM Stage 1
- `vlm_structured.yaml` — VLM Stage 2
- `naive_baseline.yaml` — Concatenated OCR → single prompt
- `strong_baseline.yaml` — Rule-by-rule CoT prompts

---

## 8. Cloud Services

### Neo4j Aura (Graph Database)

1. Sign up at [aura.neo4j.io](https://aura.neo4j.io) and create a **free instance**
2. Copy the connection URI, username, and password into `.env`:
   ```
   PLANPROOF_NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
   PLANPROOF_NEO4J_USER=neo4j
   PLANPROOF_NEO4J_PASSWORD=your-aura-password
   ```

**Local fallback**: Install Neo4j on Windows and use `bolt://localhost:7687`.

### LLM Provider (Groq / OpenAI)

Default is **Groq** (free tier, 30 requests/minute):
1. Get an API key at [console.groq.com](https://console.groq.com)
2. Set in `.env`:
   ```
   PLANPROOF_LLM_PROVIDER=groq
   PLANPROOF_LLM_MODEL=llama-3.1-70b-versatile
   PLANPROOF_LLM_API_KEY=your-groq-key
   ```

**Local fallback**: Install [Ollama](https://ollama.ai) and set `PLANPROOF_LLM_PROVIDER=ollama`.

---

## 9. Configuration Precedence

From highest to lowest priority:

1. **Environment variables** (`PLANPROOF_*`) — always win
2. **`.env` file** — loaded by pydantic-settings
3. **`configs/default.yaml`** — baseline defaults
4. **Code defaults** — in `PipelineConfig` Pydantic model

This means: `.env` for secrets, YAML for tunable parameters, env vars for Docker overrides.
