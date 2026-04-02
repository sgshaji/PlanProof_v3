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


def _generate_numeric(
    rule: DatagenRuleConfig,
    rng: random.Random,
    is_violation: bool,
) -> list[Value]:
    """Generate a single numeric Value for a standard numeric rule.

    # WHY: Extracted from generate_values so that the dispatch logic in the
    # parent function stays readable.  Returns a list (always length 1) for
    # API uniformity with other _generate_* helpers.
    """
    if is_violation:
        violation = rng.choice(rule.violation_types)
        numeric = _sample_in_range(rng, violation.range.min, violation.range.max)
    else:
        numeric = _sample_in_range(
            rng, rule.compliant_range.min, rule.compliant_range.max
        )
    return [
        Value(
            attribute=rule.attribute,
            value=numeric,
            unit=rule.unit,
            display_text=_format_display_text(numeric, rule.unit),
        )
    ]


def _generate_categorical(
    rule: DatagenRuleConfig,
    rng: random.Random,
    is_violation: bool,
) -> list[Value]:
    """Generate one categorical Value by picking from valid or invalid vocabulary.

    # WHY: Categorical rules carry their vocabulary in valid_values /
    # invalid_values rather than numeric ranges.  The primary Value stores
    # str_value for evaluation and value=0.0 as a sentinel (there is no
    # meaningful float for a certificate type).  display_text is just the
    # string value itself so renderers can embed it verbatim.
    """
    pool = rule.invalid_values if is_violation else rule.valid_values
    chosen = rng.choice(pool) if pool else ""
    return [
        Value(
            attribute=rule.attribute,
            value=0.0,
            unit=rule.unit,
            display_text=chosen,
            str_value=chosen,
        )
    ]


def _generate_string_pair(
    rule: DatagenRuleConfig,
    rng: random.Random,
    is_violation: bool,
) -> list[Value]:
    """Generate one Value per key in a compliant or noncompliant string pair.

    # WHY: String-pair rules (e.g. C002 address consistency) hold their
    # fixture data as a list of dicts, each containing all attribute keys for
    # one pair.  Picking one dict and emitting a Value per key keeps the
    # scenario's value tuple flat — every attribute is its own Value — which
    # means the rest of the pipeline (document placement, evaluation) can
    # treat all attributes uniformly.
    """
    pairs = rule.noncompliant_pairs if is_violation else rule.compliant_pairs
    chosen_pair = rng.choice(pairs) if pairs else {}
    values: list[Value] = []
    for attr, raw_val in chosen_pair.items():
        str_val = str(raw_val)
        values.append(
            Value(
                attribute=attr,
                value=0.0,
                unit=rule.unit,
                display_text=str_val,
                str_value=str_val,
            )
        )
    return values


def _generate_numeric_pair(
    rule: DatagenRuleConfig,
    rng: random.Random,
    is_violation: bool,
) -> list[Value]:
    """Generate one Value per key in a compliant or noncompliant numeric pair.

    # WHY: Same structural pattern as _generate_string_pair but casts values
    # to float so Value.value carries the authoritative numeric quantity.
    # The primary attribute drives the compliant_range check; companion
    # attributes are stored for downstream extraction but not range-evaluated
    # by default (the verdict compares the pair as a whole, not individual
    # companions).
    """
    pairs = rule.noncompliant_pairs if is_violation else rule.compliant_pairs
    chosen_pair = rng.choice(pairs) if pairs else {}
    values: list[Value] = []
    for attr, raw_val in chosen_pair.items():
        numeric = float(raw_val)
        values.append(
            Value(
                attribute=attr,
                value=numeric,
                unit=rule.unit,
                display_text=_format_display_text(numeric, rule.unit),
            )
        )
    return values


def _generate_extra_attributes(
    rule: DatagenRuleConfig,
    rng: random.Random,
    is_violation: bool,
) -> list[Value]:
    """Generate companion Values for rule.extra_attributes.

    # WHY: Extra attributes (e.g. building_footprint_area for R003,
    # ownership_declaration for C001) are defined alongside the primary rule
    # but are secondary to the verdict.  Each extra attribute descriptor
    # specifies its own unit and optional compliant_range / valid_values so
    # this helper can generate realistic values without hard-coding anything
    # in Python.  The is_violation flag is intentionally ignored for extras —
    # they always receive compliant/valid values because the violation is
    # expressed through the primary attribute.
    """
    values: list[Value] = []
    for extra in rule.extra_attributes:
        attr = extra.get("attribute", "unknown")
        unit = extra.get("unit", "")
        unit_lower = unit.lower()

        if unit_lower == "categorical":
            # Pick from valid_values for the extra attribute.
            valid = extra.get("valid_values", [])
            chosen = rng.choice(valid) if valid else ""
            values.append(
                Value(
                    attribute=attr,
                    value=0.0,
                    unit=unit,
                    display_text=chosen,
                    str_value=chosen,
                )
            )
        elif "compliant_range" in extra:
            cr = extra["compliant_range"]
            numeric = _sample_in_range(rng, float(cr["min"]), float(cr["max"]))
            values.append(
                Value(
                    attribute=attr,
                    value=numeric,
                    unit=unit,
                    display_text=_format_display_text(numeric, unit),
                )
            )
        else:
            # Numeric extra without a range — emit a zero-value placeholder.
            # WHY: Rather than silently dropping the attribute (which would
            # cause document placement to fail if the attribute is referenced
            # in evidence_locations) we emit a zero so the renderer always
            # finds the attribute in the value map.
            values.append(
                Value(
                    attribute=attr,
                    value=0.0,
                    unit=unit,
                    display_text=_format_display_text(0.0, unit),
                )
            )
    return values


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def generate_values(
    rule_configs: list[DatagenRuleConfig],
    category: str,
    seed: int,
) -> tuple[Value, ...]:
    """Generate ground-truth Values for every rule in the given scenario category.

    For numeric rules exactly one Value is produced per rule.  For pair rules
    (string_pair, numeric_pair) one Value is produced per key in the chosen
    pair dict.  Extra attributes produce one additional Value each.  The
    result therefore contains ≥ len(rule_configs) Values.

    Args:
        rule_configs: Ordered list of rules driving value generation.
        category: One of ``"compliant"``, ``"noncompliant"``, or
            ``"edgecase"``.  Controls which pool is sampled.
        seed: Integer seed for the local RNG.  The same seed always produces
            the same tuple.

    Returns:
        Immutable tuple of Value objects.  All attributes across all rules
        and their companions are included.

    # DESIGN: For "noncompliant" scenarios, exactly one rule is chosen at
    # random to be violated (the "anchor violation").  All other rules receive
    # compliant values.  This guarantees the dataset contains at least one
    # FAIL verdict without artificially inflating the violation rate.  The
    # chosen rule index is drawn from the seeded RNG *before* iterating over
    # rules so the same seed always selects the same anchor, even if the rule
    # list changes length.
    #
    # WHY: "edgecase" returns compliant base values because edge-case
    # strategies (in edge_cases.py) are applied as post-processing steps.
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
        is_violation = category == "noncompliant" and idx == anchor_idx

        vtype = rule.value_type
        if vtype == "categorical":
            primary_vals = _generate_categorical(rule, rng, is_violation)
        elif vtype == "string_pair":
            primary_vals = _generate_string_pair(rule, rng, is_violation)
        elif vtype == "numeric_pair":
            primary_vals = _generate_numeric_pair(rule, rng, is_violation)
        else:
            # Default: "numeric" — original behaviour.
            primary_vals = _generate_numeric(rule, rng, is_violation)

        values.extend(primary_vals)

        # Generate companion / extra attribute values.
        # WHY: Extra attributes are always generated in compliant form; the
        # violation signal comes from the primary attribute only.
        values.extend(_generate_extra_attributes(rule, rng, is_violation))

    return tuple(values)


def compute_verdicts(
    values: tuple[Value, ...],
    rule_configs: list[DatagenRuleConfig],
) -> tuple[Verdict, ...]:
    """Evaluate each rule against the generated values and return verdicts.

    Uses a value lookup by attribute name rather than positional zip so that
    multi-value rules (pairs, extras) do not misalign the rule→value mapping.

    Args:
        values: Ground-truth values produced by ``generate_values``.
        rule_configs: Rules whose ranges / vocabularies define pass/fail.

    Returns:
        Immutable tuple of Verdict objects, one per rule.

    # DESIGN: The threshold stored on each Verdict is the *maximum* of the
    # compliant range.  For all planning rules in scope every rule is an
    # upper-bound constraint.  For categorical and pair rules the max (0.0) is
    # a placeholder — the actual verdict logic differs by value_type.
    #
    # WHY: Using a value_map keyed on attribute name decouples verdict
    # computation from the order in which generate_values emits Values.
    # Positional zip broke silently when extra attributes were prepended or
    # reordered; name-based lookup fails loudly if the attribute is missing.
    """
    value_map: dict[str, Value] = {v.attribute: v for v in values}
    verdicts: list[Verdict] = []

    for rule in rule_configs:
        primary = value_map.get(rule.attribute)

        if primary is None:
            # Attribute was not generated (should not happen in normal usage).
            verdicts.append(
                Verdict(
                    rule_id=rule.rule_id,
                    outcome="NOT_APPLICABLE",
                    evaluated_value=0.0,
                    threshold=rule.compliant_range.max,
                )
            )
            continue

        vtype = rule.value_type

        if vtype == "categorical":
            in_range = primary.str_value in rule.valid_values
        elif vtype == "string_pair":
            # Check whether all pair keys in compliant_pairs match the chosen values.
            # WHY: A pair is compliant iff its combination matches a known good fixture.
            # Comparing against each compliant pair dict avoids implementing a full
            # semantic equivalence check in datagen.
            in_range = any(
                all(value_map.get(k) is not None and value_map[k].str_value == str(v)
                    for k, v in pair.items())
                for pair in rule.compliant_pairs
            )
        elif vtype == "numeric_pair":
            # A numeric pair is compliant if primary attribute is within range.
            # WHY: For now the primary attribute acts as the canonical check;
            # the full cross-pair comparison belongs in the rule engine, not datagen.
            in_range = (
                rule.compliant_range.min
                <= primary.value
                <= rule.compliant_range.max
            )
        else:
            # numeric — original range check
            in_range = (
                rule.compliant_range.min
                <= primary.value
                <= rule.compliant_range.max
            )

        outcome = "PASS" if in_range else "FAIL"
        verdicts.append(
            Verdict(
                rule_id=rule.rule_id,
                outcome=outcome,
                evaluated_value=primary.value,
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
    rule's ``evidence_locations`` and extra attribute locations.

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
    # counter or UUID so that it is deterministic given the same inputs.
    #
    # WHY: values_to_place now also includes extra_attribute names that share
    # the same doc_type as the rule's primary evidence location, so renderers
    # can embed companion values (footprint area, ownership declaration) in
    # the correct document without needing to know about extra_attributes.
    """
    values = generate_values(rule_configs, category, seed)
    verdicts = compute_verdicts(values, rule_configs)

    # Build a lookup: doc_type → set of attribute names that belong there.
    # WHY: Pre-computing this mapping once (rather than searching evidence_locations
    # inside the inner loop) keeps the per-document logic O(1) per attribute.
    doc_type_to_attributes: dict[str, list[str]] = {}
    for rule in rule_configs:
        for loc in rule.evidence_locations:
            # Primary attribute from evidence location field or annotation.
            attr_name = loc.field or loc.annotation or rule.attribute
            doc_type_to_attributes.setdefault(loc.doc_type, []).append(attr_name)

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
