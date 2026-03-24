# ADR-001: Pipeline Step Registry Pattern

## Status
Accepted

## Context

PlanProof orchestrates 11+ processing steps across four layers (Ingestion,
Representation, Reasoning, Output). The ablation study — a first-class research
concern — requires the ability to toggle individual components on and off to
measure their marginal contribution to system accuracy. This creates two
competing design forces:

1. Steps must be independently composable so that any subset can run in
   isolation without code changes to other steps.
2. Ablation toggles must not leak into step implementations. A step should not
   contain `if config.ablation.use_X` guards; it either runs or it does not.

A naive approach (hard-coded step sequence with conditionals scattered through
the orchestrator) would couple every step to the ablation configuration and make
the addition of new steps a multi-site change.

## Decision

Use a **step registry pattern**. Each processing step implements the
`PipelineStep` Protocol (defined in `interfaces/pipeline.py`) and is registered
with the `Pipeline` orchestrator during bootstrap. Ablation toggles are
implemented as **conditional registration** in `bootstrap.py` — the composition
root — rather than as if-checks inside step implementations.

Concretely:

- `PipelineStep` is a `typing.Protocol` with two members: a `name` property
  and an `execute(context: PipelineContext) -> StepResult` method.
- `Pipeline.register(step)` appends a step to an ordered list.
- `Pipeline.run(input_dir)` iterates the list in registration order, threading
  a `PipelineContext` (a `TypedDict`) through each step.
- `bootstrap.build_pipeline(config)` conditionally registers steps based on
  `AblationConfig` flags (e.g. `if config.ablation.use_vlm`).

Step implementations never import `AblationConfig` and are unaware that
ablations exist.

## Consequences

**What becomes easier:**

- Adding a new step requires one class (implementing `PipelineStep`) and one
  registration line in `bootstrap.py`. No existing step is modified.
- Ablation configurations are expressed declaratively via `AblationConfig`
  flags. Running an ablation variant is a configuration change, not a code
  change.
- Steps are independently testable — instantiate the step, call `execute()`
  with a synthetic `PipelineContext`, assert on the result.

**What becomes harder:**

- Step ordering is implicit (registration order in `bootstrap.py`), not an
  explicit dependency graph. If a step is registered before a step it depends
  on, the error manifests at runtime as a missing key in `PipelineContext`.
  This is mitigated by the layered registration structure in `bootstrap.py`
  (Layer 1 registered before Layer 2, etc.) and by integration tests that run
  the full pipeline.
- The `PipelineContext` TypedDict grows as steps are added. There is no
  compile-time guarantee that a step's required context keys have been
  populated by an earlier step.
