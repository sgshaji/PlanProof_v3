# ADR-003: Three-State Assessability Model

## Status
Accepted

## Context

Traditional compliance-checking systems produce binary outcomes: PASS or FAIL.
When the evidence needed to evaluate a rule is missing, conflicting, or
extracted with low confidence, these systems either silently skip the rule
(producing a false sense of completeness) or force an unreliable FAIL verdict
(generating false negatives that erode trust).

Planning officers reviewing compliance reports need to know not just whether a
rule passed, but whether it *could* be meaningfully evaluated at all. The
distinction between "this rule failed" and "we could not check this rule
because the site boundary was not found on the submitted drawings" is
operationally critical — the former requires a redesign, the latter requires a
resubmission of evidence.

This is the core research contribution of PlanProof: shifting compliance from a
binary classification to a three-valued logic that explicitly surfaces evidence
gaps.

## Decision

Introduce a three-state assessability model as a pre-filter before rule
evaluation:

```
                    ┌─────────────────────┐
                    │  Assessability Gate  │
                    └─────┬───────┬───────┘
                          │       │
                  ASSESSABLE   NOT_ASSESSABLE
                          │       │
                          v       v
                    ┌──────┐  ┌──────────────────────┐
                    │ Rule │  │ Evidence Request (M11)│
                    │Engine│  │ + blocking reason     │
                    └──┬───┘  └──────────────────────┘
                       │
                  PASS / FAIL
```

The `AssessabilityResult` schema carries:

- `status`: `"ASSESSABLE"` or `"NOT_ASSESSABLE"`
- `blocking_reason`: one of `NONE`, `MISSING_EVIDENCE`,
  `CONFLICTING_EVIDENCE`, or `LOW_CONFIDENCE`
- `missing_evidence`: a list of `EvidenceRequirement` objects specifying
  exactly what is needed (attribute, acceptable sources, minimum confidence,
  spatial grounding)
- `conflicts`: a list of `ConflictDetail` objects recording which sources
  disagree and on what values

The rule engine is only invoked for rules whose assessability status is
`ASSESSABLE`. Rules that are `NOT_ASSESSABLE` bypass the rule engine entirely
and flow to the Evidence Request Generator (M11), which produces structured
requests telling the applicant what evidence to provide.

The three blocking reasons are deliberately distinct:

- **MISSING_EVIDENCE**: The required attribute was not found in any submitted
  document. Actionable: submit the document containing this information.
- **CONFLICTING_EVIDENCE**: Multiple sources provide different values for the
  same attribute and reconciliation could not resolve the conflict. Actionable:
  clarify which value is authoritative.
- **LOW_CONFIDENCE**: The evidence exists but was extracted with confidence
  below the gating threshold. Actionable: provide a clearer document or
  confirm the extracted value.

## Consequences

**What becomes easier:**

- Rule evaluation logic is simpler. Evaluators only handle cases where
  sufficient, trusted evidence exists — they never need to handle missing data
  or low-confidence edge cases.
- Compliance reports carry structured, actionable feedback. A
  `NOT_ASSESSABLE` verdict with `MISSING_EVIDENCE` and a list of
  `EvidenceRequirement` objects tells the applicant exactly what to submit,
  rather than issuing a generic "insufficient information" message.
- The ablation study can measure the contribution of assessability gating
  (Ablation D) by disabling the assessability engine and forcing all rules
  through evaluation regardless of evidence quality. This directly quantifies
  the false-negative reduction.

**What becomes harder:**

- Schema complexity increases. The `AssessabilityResult`, `BlockingReason`,
  `EvidenceRequirement`, and `ConflictDetail` types add surface area to the
  data model. Every consumer of compliance results must handle the
  three-valued outcome rather than a simple boolean.
- The output layer (dashboard, reports) must present three states rather than
  two, requiring more nuanced UI/UX design.
- Each rule definition (YAML) must declare its `required_evidence` — the list
  of attributes, acceptable sources, and minimum confidence levels needed for
  assessment. This front-loads effort into rule authoring but pays back in
  precision.
