# PlanProof Architecture

PlanProof is a neurosymbolic system for automated planning compliance
validation. It combines neural components (LLM-based entity extraction, VLM
drawing analysis) with symbolic components (a spatial normative knowledge graph,
deterministic rule evaluation) to produce auditable compliance verdicts. The
architecture's distinguishing feature is its assessability engine, which
introduces three-valued logic (ASSESSABLE / NOT_ASSESSABLE) to prevent false
verdicts when evidence is insufficient. The system is designed as an MSc
dissertation prototype with ablation study infrastructure as a first-class
architectural concern.

---

## Component Diagram

```
Layer 0 -- Foundation
  +-- Project scaffolding, CI, Neo4j instance, dev environment
  +-- [M4] Unified Entity Schema (integration contract -- ALL modules depend on this)
  +-- LLM response cache infrastructure
  +-- Pipeline skeleton (grows incrementally per phase)
  +-- Dataset: real BCC data + synthetic generation pipeline

Layer 1 -- Ingestion (no dependencies on each other; all output M4 schema objects)
  +-- [M1] Document Classifier
  +-- [M2] Text Extraction Pipeline (OCR + LLM entity extraction)
  +-- [M3] VLM Pipeline (drawing analysis -- sub-experiment)

Layer 2 -- Representation (depends on Layer 1)
  +-- [M5] Spatial Normative Knowledge Graph (populated from M4 entities)

Layer 3 -- Reasoning (depends on Layer 2)
  +-- [M6] Evidence Reconciliation Engine (queries M5)
  +-- [M7] Confidence Gating (wraps M6 outputs)
  +-- [M8] Assessability Engine (queries M5 + M6 + M7)
  +-- [M9] Normative Rule Engine (invoked when M8 returns ASSESSABLE)

Layer 4 -- Output (depends on Layer 3)
  +-- [M10] Compliance Scoring (aggregates M8 + M9 results)
  +-- [M11] Min Evidence Request Generator (from M8 NOT_ASSESSABLE outputs)
  +-- [M12] Decision Support Dashboard (FastAPI + React + Leaflet)

Layer 5 -- Evaluation
  +-- Ablation study (toggle components)
  +-- Metrics computation + analysis
```

---

## Interface Boundaries

Layers communicate exclusively through Protocols defined in
`src/planproof/interfaces/`. No module imports a concrete class from another
layer. The interfaces are grouped by architectural layer:

| Module | Protocols | Layer |
|---|---|---|
| `interfaces/extraction.py` | `DocumentClassifier`, `OCRExtractor`, `EntityExtractor`, `VLMExtractor` | 1 |
| `interfaces/graph.py` | `GraphRepository` | 2 |
| `interfaces/reasoning.py` | `Reconciler`, `ConfidenceGate`, `AssessabilityEvaluator`, `RuleEvaluator` | 3 |
| `interfaces/pipeline.py` | `PipelineStep`, `PipelineContext`, `StepResult` | Cross-cutting |
| `interfaces/output.py` | `ReportRenderer` | 4 |
| `interfaces/cache.py` | `LLMCache` | Infrastructure |
| `interfaces/llm.py` | `LLMClient` | Infrastructure |

These are `typing.Protocol` classes (structural subtyping). A concrete class
satisfies a Protocol by implementing the required methods -- no inheritance
required. See ADR-002 for the rationale.

---

## Data Flow

The pipeline processes a planning application through a linear chain of
transformations. Each transformation produces a well-typed schema object that
the next step consumes:

```
Path (input directory)
  |
  v
ClassifiedDocument          -- M1 Document Classifier
  |
  v
RawTextResult               -- M2 OCR extraction
  |
  v
ExtractedEntity[]           -- M2 LLM entity extraction + M3 VLM extraction
  |
  v
ExtractedEntity[] (normalised, graph-populated)
  |                         -- M4 Normalisation + M5 SNKG population
  v
ReconciledEvidence[]        -- M6 Evidence Reconciliation
  |
  v
ExtractedEntity[] (trusted) -- M7 Confidence Gating
  |
  v
AssessabilityResult[]       -- M8 Assessability Engine
  |                              ASSESSABLE rules --> Rule Engine
  |                              NOT_ASSESSABLE rules --> Evidence Request Generator
  v
RuleVerdict[]               -- M9 Rule Engine (PASS / FAIL per rule)
  |
  v
ComplianceReport            -- M10 Scoring + M11 Evidence Requests
```

State is threaded between steps via `PipelineContext`, a `TypedDict` that
accumulates results. Each step reads keys populated by earlier steps and writes
its own keys. The pipeline orchestrator iterates steps in registration order
and assembles the final `ComplianceReport` from the context after all steps
complete.

---

## Composition Root

`src/planproof/bootstrap.py` is the composition root -- the single file that
knows about every concrete type in the system. Its responsibilities:

1. **Read configuration** from `PipelineConfig` (environment variables / YAML).
2. **Instantiate infrastructure**: LLM client, cache, logging.
3. **Register rule evaluators** with the `RuleFactory` (one line per evaluator
   type: `numeric_threshold`, `ratio_threshold`, `enum_check`, etc.).
4. **Conditionally register pipeline steps** based on `AblationConfig` flags.
   Steps for disabled ablation components are simply not registered.
5. **Return a wired `Pipeline`** ready to process applications.

No other module in the system instantiates its own dependencies. If a step
needs an `OCRExtractor`, it receives one via constructor injection in
`bootstrap.py`. This guarantees that swapping an implementation (for ablation,
testing, or future replacement) requires changes in exactly one file.

During early development, `bootstrap.py` defines `_Stub*` placeholder classes
that satisfy Protocol interfaces structurally but raise `NotImplementedError`.
These are replaced with concrete implementations as each phase is built.

---

## Extensibility: YAML Rules and the RuleFactory

Compliance rules are defined declaratively in YAML files under `configs/rules/`.
Each rule specifies:

- `rule_id`, `description`, `policy_source` -- metadata
- `evaluation_type` -- dispatches to the correct evaluator (e.g.
  `numeric_threshold`, `ratio_threshold`, `enum_check`)
- `parameters` -- evaluator-specific configuration (thresholds, tolerances,
  allowed values)
- `required_evidence` -- what the assessability engine checks before allowing
  evaluation (attribute names, acceptable sources, minimum confidence, spatial
  grounding requirements)

The `RuleFactory` maintains a registry of evaluator classes keyed by
`evaluation_type`. At startup, `bootstrap.py` registers all built-in evaluator
types. At runtime, `RuleFactory.load_rules(rules_dir)` reads every `*.yaml`
file, parses it into a `RuleConfig`, and instantiates the corresponding
evaluator.

Adding a new rule type requires:
1. A new evaluator class implementing the `RuleEvaluator` Protocol.
2. One registration line in `bootstrap._register_evaluators()`.
3. YAML files for the specific rules of that type.

Existing evaluators are never modified (Open-Closed Principle).

---

## Ablation Architecture

The ablation study is not bolted on after the fact -- it is a first-class
architectural concern that shaped the system's decomposition. The goal is to
measure the marginal contribution of each major component to overall compliance
accuracy.

`AblationConfig` (in `schemas/config.py`) defines six boolean toggles:

| Flag | Component controlled | Ablation label |
|---|---|---|
| `use_snkg` | Spatial Normative Knowledge Graph | Ablation B |
| `use_rule_engine` | Deterministic rule evaluation | Ablation C |
| `use_confidence_gating` | Confidence threshold filtering | Ablation E |
| `use_assessability_engine` | Three-state assessability gate | Ablation D |
| `use_evidence_reconciliation` | Multi-source evidence reconciliation | Ablation F |
| `use_vlm` | VLM drawing analysis pipeline | Ablation A |

The mechanism is conditional step registration in `bootstrap.py`. When a flag
is `False`, the corresponding pipeline step is not registered. The step class
still exists in the codebase but is never instantiated. Steps themselves are
completely unaware of ablation -- they contain no conditional logic.

This design means:
- An ablation run is a configuration change (set flags in environment
  variables), not a code change.
- Each ablation variant produces a `ComplianceReport` with identical schema,
  making automated metric comparison straightforward.
- The full pipeline and any ablation variant share the same orchestration code;
  only the set of registered steps differs.

---

## Note on Scope

This document is a reference for the system's structural design. It is intended
to feed the dissertation chapter on system architecture and to serve as the
authoritative guide for contributors navigating the codebase. For implementation
sequencing, see `docs/IMPLEMENTATION_PLAN.md`. For individual design decisions,
see the ADRs in `docs/adr/`.
