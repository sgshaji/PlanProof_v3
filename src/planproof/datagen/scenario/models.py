"""Scenario models — the central data contract for the synthetic data generator.

Each Scenario fully describes one synthetic planning application set: which
values appear in which documents, how those documents should be degraded, and
what the rule engine is expected to conclude.  Downstream generators read this
spec and produce PDFs, images, and ground-truth labels without any further
shared state.

# DESIGN: All models are frozen dataclasses rather than Pydantic models because
# these objects are pure data carriers that never need serialisation validation
# at construction time.  Frozen dataclasses give us structural immutability (no
# accidental mutation across pipeline stages) and are hashable by default,
# which lets us use them as dict keys or set members if needed.  We use `tuple`
# instead of `list` for collections so the immutability guarantee is deep, not
# just at the top level.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Value:
    """A single ground-truth value to be embedded in one or more documents.

    # WHY: Separating *what* a value is (attribute + unit) from *how* it is
    # displayed (display_text) lets the document renderer choose formatting
    # freely while the evaluation layer always compares against the canonical
    # numeric `value`.  This prevents the common mistake of evaluating against
    # a rounded or locale-formatted string instead of the true float.
    """

    # The canonical attribute name, matching keys in the rule catalogue.
    attribute: str
    # The authoritative numeric quantity used for rule evaluation.
    value: float
    # SI or domain unit string (e.g. "metres", "m²", "degrees").
    unit: str
    # Human-readable text as it should appear in the generated document
    # (e.g. "7.5m", "750 sq m").  May differ from str(value) + unit.
    display_text: str


@dataclass(frozen=True)
class Verdict:
    """The expected rule outcome for one rule applied to one scenario.

    # WHY: Storing expected verdicts alongside the scenario means evaluation
    # is a simple equality check between the rule engine's output and this
    # ground-truth record.  It also makes failure analysis self-contained —
    # you can inspect `evaluated_value` vs `threshold` without re-running
    # the scenario.
    """

    # Matches the rule identifier in the rule catalogue (e.g. "R001").
    rule_id: str
    # Expected outcome string: "PASS", "FAIL", or "NOT_APPLICABLE".
    outcome: str
    # The numeric value the rule engine should extract and evaluate.
    evaluated_value: float
    # The rule's pass/fail threshold for reference and diff diagnostics.
    threshold: float


@dataclass(frozen=True)
class DocumentSpec:
    """Specification for a single document to be synthesised.

    # WHY: Keeping document specs separate from the overall Scenario lets the
    # document renderer iterate over `documents` without needing to know
    # anything about rules or verdicts.  The `values_to_place` tuple names
    # which `Value.attribute` keys from the parent Scenario should appear in
    # this document, enabling the renderer to look them up by name rather than
    # by position — a much safer coupling.
    """

    # Document category matching DocumentType strings (e.g. "FORM", "DRAWING").
    doc_type: str
    # Output file format the renderer should produce (e.g. "pdf", "png").
    file_format: str
    # Ordered list of `Value.attribute` keys to embed in this document.
    # Using tuple (not list) preserves immutability of the frozen dataclass.
    values_to_place: tuple[str, ...]
    # Drawing subtype for DRAWING docs (e.g. "site_plan", "floor_plan",
    # "elevation"). None for FORM documents.
    # WHY: The runner uses this to dispatch to the correct generator plugin.
    # Without it, all drawings would go to the same generator.
    subtype: str | None = None


@dataclass(frozen=True)
class Scenario:
    """Complete specification for one synthetic planning application set.

    # WHY: A single Scenario captures everything a downstream generator needs
    # to produce a deterministic, reproducible evaluation sample — the random
    # seed, the ground-truth values, the expected verdicts, and the per-document
    # rendering instructions.  Keeping it as one immutable object means it can
    # be logged, cached, or replayed without risk of partial mutation corrupting
    # the dataset.

    # DESIGN: `edge_case_strategy` is `str | None` rather than an enum so that
    # new strategies can be added to configuration without touching this model.
    # None signals "no special handling" and is the default for the majority of
    # compliant scenarios.
    """

    # Unique identifier for this application set (e.g. "SET_C001").
    set_id: str
    # High-level category: "compliant", "non_compliant", or "edge_case".
    category: str
    # Random seed that makes the entire scenario reproducible end-to-end.
    seed: int
    # Identifier for the document-set profile (drives how many docs are made).
    profile_id: str
    # Difficulty label that influences degradation intensity ("low", "medium", "high").
    difficulty: str
    # Named degradation preset applied to all documents (e.g. "moderate_scan").
    degradation_preset: str
    # All ground-truth values available across documents in this set.
    values: tuple[Value, ...]
    # Expected rule verdicts for this scenario.
    verdicts: tuple[Verdict, ...]
    # Per-document rendering instructions.
    documents: tuple[DocumentSpec, ...]
    # Optional tag for special edge-case handling (e.g. "conflicting_values").
    # None means this is a standard scenario with no edge-case logic.
    edge_case_strategy: str | None
