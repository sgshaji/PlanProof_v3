"""Scenario generator — pure functions for building synthetic planning scenarios.

Three public functions form a composable pipeline:

  generate_values  →  compute_verdicts  →  build_scenario

Each function is pure: given the same inputs it always produces the same output,
with no side effects and no dependency on global state.  Randomness is controlled
entirely via a seeded ``random.Random`` instance that is constructed inside each
function and never stored externally.

# DESIGN: Using ``random.Random`` (not the module-level ``random`` functions)
# ensures the seeded state is strictly local to one call.  Module-level random
# functions share a single implicit RNG that any concurrent or imported code
# could advance unpredictably, breaking reproducibility.
#
# WHY: The separation into three functions lets callers substitute any layer.
# For example, a test can call ``compute_verdicts`` with hand-crafted Values
# without needing to invoke the random-number machinery at all.
"""

from __future__ import annotations

import random

from planproof.datagen.scenario.config_loader import DatagenRuleConfig, ProfileConfig
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_display_text(value: float, unit: str) -> str:
    """Produce a human-readable string for *value* given its *unit*.

    # WHY: Display formatting is unit-specific.  Metres and metres-squared use
    # a compact suffix appended immediately to the number (e.g. "7.5m",
    # "450m²").  Percent uses a trailing "%" with a space.  Everything else
    # falls back to "<value> <unit>" with a space separator.  This mirrors
    # how values commonly appear in planning documents and gives the renderer
    # a realistic string without further transformation.
    #
    # DESIGN: Rounding to one decimal place keeps display_text consistent and
    # avoids floating-point noise like "7.500000000000001m".  The canonical
    # ``value`` field on Value is stored at full float precision; only the
    # display representation is rounded.
    """
    rounded = round(value, 1)
    unit_lower = unit.lower()

    if unit_lower in ("metres", "m"):
        return f"{rounded}m"
    if unit_lower in ("percent", "%"):
        return f"{rounded}%"
    if unit_lower in ("m²", "sq m", "square metres"):
        return f"{rounded}m²"
    if unit_lower in ("degrees", "°"):
        return f"{rounded}°"

    # WHY: Generic fallback keeps the function total — no unit causes a crash.
    return f"{rounded} {unit}"


def _sample_in_range(rng: random.Random, min_val: float, max_val: float) -> float:
    """Sample a float uniformly from [*min_val*, *max_val*] rounded to 2 dp.

    # WHY: Rounding to two decimal places produces values that look like real
    # measurements (e.g. 6.73 m rather than 6.731842…) while retaining enough
    # precision that range comparisons never suffer from boundary ambiguity.
    """
    raw = rng.uniform(min_val, max_val)
    return round(raw, 2)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def generate_values(
    rule_configs: list[DatagenRuleConfig],
    category: str,
    seed: int,
) -> tuple[Value, ...]:
    """Generate one ground-truth Value per rule for the given scenario category.

    Args:
        rule_configs: Ordered list of rules driving value generation.  One
            Value is produced per rule, in the same order.
        category: One of ``"compliant"``, ``"noncompliant"``, or
            ``"edgecase"``.  Controls which numeric range is sampled.
        seed: Integer seed for the local RNG.  The same seed always produces
            the same tuple.

    Returns:
        Immutable tuple of Value objects, one per entry in *rule_configs*.

    # DESIGN: For "noncompliant" scenarios, exactly one rule is chosen at
    # random to be violated (the "anchor violation").  All other rules receive
    # compliant values.  This guarantees the dataset contains at least one
    # FAIL verdict without artificially inflating the violation rate.  The
    # chosen rule index is drawn from the seeded RNG *before* iterating over
    # rules so the same seed always selects the same anchor, even if the rule
    # list changes length (because the selection draw happens at a fixed point
    # in the RNG sequence).
    #
    # WHY: "edgecase" returns compliant base values because edge-case
    # strategies (in edge_cases.py) are applied as post-processing steps.
    # Generating compliant values first, then transforming them, keeps the
    # two concerns separate and makes each step independently testable.
    """
    # WHY: Construct a fresh Random instance from the caller-supplied seed so
    # this function has no dependency on any external RNG state.
    rng = random.Random(seed)

    # For noncompliant scenarios, choose the anchor rule index before the loop
    # so RNG draws happen in a deterministic order regardless of loop body.
    if category == "noncompliant":
        # WHY: randrange guarantees an integer in [0, len-1]; using it before
        # the loop reserves the first RNG draw for rule selection so subsequent
        # draws (the actual value samples) land at the same sequence positions
        # regardless of which rule was selected.
        anchor_idx = rng.randrange(len(rule_configs))
    else:
        anchor_idx = -1  # sentinel: not used for compliant / edgecase

    values: list[Value] = []

    for idx, rule in enumerate(rule_configs):
        if category == "noncompliant" and idx == anchor_idx:
            # WHY: Picking a random violation type from the rule's named bands
            # means the generated value is drawn from the correct non-compliant
            # region without the generator hard-coding any numeric bounds.
            violation = rng.choice(rule.violation_types)
            numeric = _sample_in_range(
                rng, violation.range.min, violation.range.max
            )
        else:
            # Compliant path — used for "compliant", "edgecase", and all
            # non-anchor rules in "noncompliant" scenarios.
            numeric = _sample_in_range(
                rng, rule.compliant_range.min, rule.compliant_range.max
            )

        values.append(
            Value(
                attribute=rule.attribute,
                value=numeric,
                unit=rule.unit,
                display_text=_format_display_text(numeric, rule.unit),
            )
        )

    return tuple(values)


def compute_verdicts(
    values: tuple[Value, ...],
    rule_configs: list[DatagenRuleConfig],
) -> tuple[Verdict, ...]:
    """Evaluate each Value against its rule's compliant_range and return verdicts.

    Args:
        values: Ground-truth values produced by ``generate_values``.  Must be
            in the same order as *rule_configs*.
        rule_configs: Rules whose ranges define the pass/fail boundary.

    Returns:
        Immutable tuple of Verdict objects, one per (value, rule) pair.

    # DESIGN: The threshold stored on each Verdict is the *maximum* of the
    # compliant range.  For the planning rules in scope every rule is an
    # upper-bound constraint (e.g. "must not exceed 8 m"), so the max is the
    # decision boundary that the rule engine will compare against.  If the
    # domain later introduces lower-bound-only rules this convention will need
    # revisiting, but for now it keeps Verdict diagnostics unambiguous.
    #
    # WHY: Storing evaluated_value as the exact float from the Value (not a
    # rounded copy) ensures that downstream diagnostics always reflect the
    # actual value that drove the verdict, not a display artifact.
    """
    verdicts: list[Verdict] = []

    for value, rule in zip(values, rule_configs):
        in_range = rule.compliant_range.min <= value.value <= rule.compliant_range.max
        outcome = "PASS" if in_range else "FAIL"

        verdicts.append(
            Verdict(
                rule_id=rule.rule_id,
                outcome=outcome,
                evaluated_value=value.value,
                # WHY: threshold = max of compliant range as the primary
                # decision boundary for all upper-bound planning constraints.
                threshold=rule.compliant_range.max,
            )
        )

    return tuple(verdicts)


def build_scenario(
    profile: ProfileConfig,
    rule_configs: list[DatagenRuleConfig],
    category: str,
    seed: int,
) -> Scenario:
    """Assemble a complete Scenario from a profile, rule configs, category, and seed.

    This is the top-level factory function that orchestrates the generator
    pipeline: it calls ``generate_values`` and ``compute_verdicts``, then
    constructs a ``DocumentSpec`` for each entry in the profile's
    ``document_composition``, assigning ``values_to_place`` based on each
    rule's ``evidence_locations``.

    Args:
        profile: Document-set profile specifying which document types to create
            and the difficulty / degradation context.
        rule_configs: Full list of rules whose values and verdicts will be
            embedded in the scenario.
        category: Scenario category — ``"compliant"``, ``"noncompliant"``, or
            ``"edgecase"``.
        seed: Reproducibility seed passed through to ``generate_values``.

    Returns:
        A fully populated, immutable ``Scenario`` object.

    # DESIGN: ``set_id`` is constructed from category and seed rather than a
    # counter or UUID so that it is deterministic given the same inputs.  The
    # format ``SET_<CATEGORY_UPPER>_<SEED>`` is both human-readable in file
    # names and guaranteed unique within a single category × seed space
    # (collisions across different profiles with the same seed are acceptable
    # because profiles are always run in separate output directories).
    #
    # WHY: values_to_place contains only the attribute names whose rules have
    # an evidence location matching the current document's doc_type.  This
    # prevents the renderer from trying to embed a drawing-annotation value
    # into a form or vice versa, which would produce invalid ground-truth
    # labels.
    """
    values = generate_values(rule_configs, category, seed)
    verdicts = compute_verdicts(values, rule_configs)

    # Build a lookup: doc_type → set of attribute names that belong there.
    # WHY: Pre-computing this mapping once (rather than searching evidence_locations
    # inside the inner loop) keeps the per-document logic O(1) per attribute.
    doc_type_to_attributes: dict[str, list[str]] = {}
    for rule in rule_configs:
        for loc in rule.evidence_locations:
            doc_type_to_attributes.setdefault(loc.doc_type, []).append(rule.attribute)

    # Construct one DocumentSpec per composition entry, expanding subtypes.
    # WHY: Each subtype gets its own DocumentSpec so the runner can dispatch
    # to the correct generator (SitePlan vs FloorPlan vs Elevation).
    documents: list[DocumentSpec] = []
    for comp in profile.document_composition:
        attrs_for_type = tuple(
            doc_type_to_attributes.get(comp.type, [])
        )
        # If subtypes are defined, create one doc per subtype.
        # Otherwise create `count` docs with no subtype (e.g. FORM).
        subtypes: list[str | None] = (
            list(comp.subtypes) if comp.subtypes else [None] * comp.count
        )
        for subtype in subtypes:
            # WHY: Elevations are raster (PNG) for realistic VLM testing.
            # All other document types default to PDF.
            fmt = "png" if subtype == "elevation" else "pdf"
            documents.append(
                DocumentSpec(
                    doc_type=comp.type,
                    subtype=subtype,
                    file_format=fmt,
                    values_to_place=attrs_for_type,
                )
            )

    # WHY: category is normalised to uppercase for the set_id prefix so that
    # "compliant" and "COMPLIANT" inputs produce the same identifier pattern,
    # avoiding accidental duplicates from case inconsistencies in callers.
    set_id = f"SET_{category.upper()}_{seed}"

    return Scenario(
        set_id=set_id,
        category=category,
        seed=seed,
        profile_id=profile.profile_id,
        difficulty=profile.difficulty,
        degradation_preset=profile.degradation_preset,
        values=values,
        verdicts=verdicts,
        documents=tuple(documents),
        # WHY: edge_case_strategy is None here because build_scenario produces
        # a base scenario.  Edge-case decoration is applied separately by the
        # functions in edge_cases.py, keeping the two concerns composable.
        edge_case_strategy=None,
    )
