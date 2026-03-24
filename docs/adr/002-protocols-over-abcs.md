# ADR-002: Protocols Over Abstract Base Classes

## Status
Accepted

## Context

PlanProof's layered architecture requires interface contracts between
components: the pipeline orchestrator depends on `PipelineStep`, the reasoning
layer depends on `Reconciler`, `ConfidenceGate`, `AssessabilityEvaluator`, and
`RuleEvaluator`, and the ingestion layer depends on `DocumentClassifier`,
`OCRExtractor`, `EntityExtractor`, and `VLMExtractor`.

Python offers two mechanisms for defining interface contracts:

1. **Abstract Base Classes (ABCs)** — nominal subtyping. A class must
   explicitly inherit from the ABC to satisfy the contract. Checked at
   instantiation time via `__init_subclass__` or at call time via
   `isinstance`.

2. **`typing.Protocol`** — structural subtyping (PEP 544). A class satisfies a
   Protocol by having the right methods with compatible signatures, without
   inheriting from anything. Checked statically by mypy.

The choice affects three concrete scenarios in PlanProof:

- **Ablation swaps**: The `FlatEvidenceProvider` ablation replaces the full
  SNKG-backed evidence layer with a flat lookup. With ABCs, it would need to
  inherit from a base class it has no logical relationship to. With Protocols,
  it just needs to expose the same method signatures.
- **Test doubles**: Unit tests create lightweight stubs and fakes. With ABCs,
  every test double must inherit from the production interface, coupling test
  code to the production class hierarchy. With Protocols, a stub is a plain
  class with the right methods.
- **Composition root stubs**: `bootstrap.py` defines `_Stub*` placeholder
  classes for phases not yet implemented. These are simple objects with
  methods that raise `NotImplementedError`. Protocols allow these to satisfy
  interface contracts without any inheritance.

## Decision

Use `typing.Protocol` (structural subtyping) for all interface contracts.
Protocols are defined in `src/planproof/interfaces/` and grouped by
architectural layer:

| Module | Protocols |
|---|---|
| `interfaces/extraction.py` | `DocumentClassifier`, `OCRExtractor`, `EntityExtractor`, `VLMExtractor` |
| `interfaces/reasoning.py` | `Reconciler`, `ConfidenceGate`, `AssessabilityEvaluator`, `RuleEvaluator` |
| `interfaces/pipeline.py` | `PipelineStep` |
| `interfaces/graph.py` | `GraphRepository` |
| `interfaces/output.py` | `ReportRenderer` |
| `interfaces/cache.py` | `LLMCache` |
| `interfaces/llm.py` | `LLMClient` |

No class in the codebase inherits from these Protocols. Compliance is enforced
by mypy in strict mode, which verifies that concrete types passed where a
Protocol is expected are structurally compatible.

## Consequences

**What becomes easier:**

- Ablation variants and test doubles are plain classes with no inheritance
  ceremony. A three-line stub satisfies the contract if its methods match.
- Adding a new interface does not force changes on existing implementations.
- The `interfaces/` package is a pure declaration of boundaries — no
  implementation logic, no runtime cost.

**What becomes harder:**

- There are no runtime `isinstance` checks. If a mis-typed object is passed
  where a Protocol is expected, the error is caught by mypy, not at runtime.
  This means mypy must be run in CI (enforced via GitHub Actions) for the
  safety guarantee to hold.
- IDE auto-complete and "go to implementation" support for Protocols is less
  reliable than for ABCs in some editors, since there is no explicit
  inheritance link to follow.
- Developers unfamiliar with structural subtyping may not immediately
  recognise that a class implements a Protocol, since the relationship is
  implicit. This is mitigated by docstrings on each Protocol and by the
  `interfaces/` package serving as a single reference point for all
  contracts.
