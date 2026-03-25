"""Edge-case strategy functions for scenario post-processing.

Each public function takes a ``Scenario`` (and optionally a seed) and returns a
*new* ``Scenario`` with one specific structural anomaly applied.  Together they
simulate the kinds of imperfect or ambiguous submissions that a real planning
rule engine must handle gracefully.

All functions are pure:
  - They never mutate the input Scenario (frozen dataclasses enforce this).
  - They use ``dataclasses.replace`` to produce modified copies.
  - Randomness, where needed, comes from a seeded ``random.Random`` constructed
    inside the function — never from module-level state.

# DESIGN: The five strategy functions plus the ``apply_edge_case`` dispatcher
# form a closed algebra: any scenario can be decorated with exactly one strategy
# by calling ``apply_edge_case(scenario, strategy_name, seed)``.  The dispatcher
# pattern means new strategies can be added by extending the registry dict
# without modifying the dispatcher's control flow.

# WHY: Keeping edge-case logic separate from ``generator.py`` preserves the
# single-responsibility principle: the generator focuses on producing correct
# base values, while this module focuses on introducing controlled defects.
# A test suite can therefore exercise the two layers independently.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import replace

from planproof.datagen.scenario.models import Scenario, Value

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _replace_scenario(scenario: Scenario, **changes: object) -> Scenario:
    """Return a new Scenario with *changes* applied via dataclasses.replace.

    # WHY: A thin wrapper centralises the import of ``replace`` and makes
    # call sites read more naturally (``_replace_scenario(s, seed=42)`` vs
    # ``replace(s, seed=42)``).  More importantly, it lets us add invariant
    # checks here in the future without touching every call site.
    """
    return replace(scenario, **changes)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Strategy 1: apply_missing_evidence
# ---------------------------------------------------------------------------


def apply_missing_evidence(scenario: Scenario, seed: int) -> Scenario:
    """Remove one value placement from one document's values_to_place.

    Simulates a submission where one piece of evidence (e.g. a dimension on a
    drawing) is absent, forcing the extraction layer to flag a gap.

    Args:
        scenario: The base scenario to transform.
        seed: RNG seed controlling which document and which attribute are
            removed.  The same seed always removes the same item.

    Returns:
        A new Scenario where exactly one value placement has been removed.
        ``edge_case_strategy`` is set to ``"missing_evidence"``.

    # DESIGN: We only remove a placement from documents that have at least one
    # attribute already.  Documents with zero attributes are skipped because
    # removing from an empty tuple is a no-op that would silently leave the
    # scenario unchanged — a confusing non-transformation.
    #
    # WHY: Removing exactly one placement keeps the scenario viable.  Removing
    # all placements would produce a degenerate scenario with no ground truth.
    """
    rng = random.Random(seed)

    # Filter to documents that actually have placements to remove.
    # WHY: Index-based selection (rather than object identity) is used so the
    # RNG draw is always made in the same sequence position regardless of
    # whether eligible_indices is a subset of all indices.
    eligible_indices = [
        i for i, doc in enumerate(scenario.documents) if len(doc.values_to_place) > 0
    ]

    if not eligible_indices:
        # WHY: If no document has any placements there is nothing to remove;
        # return the scenario as-is (with the strategy tag set) rather than
        # raising, because this is a degenerate but not erroneous input.
        return _replace_scenario(scenario, edge_case_strategy="missing_evidence")

    # Choose which document to modify.
    doc_idx = rng.choice(eligible_indices)
    target_doc = scenario.documents[doc_idx]

    # Choose which attribute placement to remove from that document.
    removal_idx = rng.randrange(len(target_doc.values_to_place))
    new_values_to_place = (
        target_doc.values_to_place[:removal_idx]
        + target_doc.values_to_place[removal_idx + 1 :]
    )

    # WHY: Build a new documents tuple with the modified DocumentSpec at
    # doc_idx.  All other documents are unchanged (same frozen objects reused).
    modified_doc = replace(target_doc, values_to_place=new_values_to_place)
    new_documents = (
        scenario.documents[:doc_idx]
        + (modified_doc,)
        + scenario.documents[doc_idx + 1 :]
    )

    return _replace_scenario(
        scenario,
        documents=new_documents,
        edge_case_strategy="missing_evidence",
    )


# ---------------------------------------------------------------------------
# Strategy 2: apply_conflicting_values
# ---------------------------------------------------------------------------


def apply_conflicting_values(scenario: Scenario, seed: int) -> Scenario:
    """Add a conflicting copy of one value with a different numeric quantity.

    Simulates a submission where the same measurement appears in two documents
    with different numbers (e.g. a form says 6.0 m but a drawing says 9.5 m),
    testing the rule engine's ability to detect and flag inconsistencies.

    Args:
        scenario: The base scenario to transform.
        seed: RNG seed controlling which value is duplicated and what the
            conflicting quantity is.

    Returns:
        A new Scenario where ``values`` contains an extra Value for the chosen
        attribute with a numeric quantity ±10–20 % different from the original.
        ``edge_case_strategy`` is set to ``"conflicting_values"``.

    # DESIGN: The conflicting value is generated by adding a random ±10–20 %
    # perturbation to the original quantity.  This range is large enough to
    # be detectable but small enough to remain physically plausible.  The
    # sign of the perturbation is chosen randomly so the conflict can be an
    # over- *or* under-estimate.
    #
    # WHY: We append the conflict to ``scenario.values`` rather than replacing
    # the original.  The downstream extraction layer must see *two* distinct
    # numeric values for the same attribute — only then does it have a genuine
    # conflict to resolve.
    """
    rng = random.Random(seed)

    # Pick the value to conflict.
    original: Value = rng.choice(scenario.values)

    # Generate a perturbation of 10–20 % in a random direction.
    # WHY: Using uniform(0.10, 0.20) and a random sign keeps the conflicting
    # value within a plausible physical range while guaranteeing it differs
    # from the original by at least 10 %.
    magnitude = rng.uniform(0.10, 0.20)
    sign = rng.choice([-1, 1])
    delta = original.value * magnitude * sign
    conflicting_numeric = round(original.value + delta, 2)

    # WHY: We reuse the same attribute and unit so the downstream layer knows
    # these two values compete for the same rule slot.  display_text is
    # constructed to reflect the conflicting numeric rather than the original,
    # so the rendered document shows the wrong value.
    unit_lower = original.unit.lower()
    if unit_lower in ("metres", "m"):
        conflicting_display = f"{round(conflicting_numeric, 1)}m"
    elif unit_lower in ("percent", "%"):
        conflicting_display = f"{round(conflicting_numeric, 1)}%"
    else:
        conflicting_display = f"{round(conflicting_numeric, 1)} {original.unit}"

    conflicting_value = Value(
        attribute=original.attribute,
        value=conflicting_numeric,
        unit=original.unit,
        display_text=conflicting_display,
    )

    new_values = scenario.values + (conflicting_value,)

    return _replace_scenario(
        scenario,
        values=new_values,
        edge_case_strategy="conflicting_values",
    )


# ---------------------------------------------------------------------------
# Strategy 3: apply_low_confidence_scan
# ---------------------------------------------------------------------------


def apply_low_confidence_scan(scenario: Scenario) -> Scenario:
    """Upgrade the degradation preset to ``"heavy_scan"``.

    Simulates a poorly scanned submission where OCR confidence is inherently
    low due to image quality.  The heavy scan preset applies more aggressive
    degradation transforms (blur, noise, skew) than the default moderate_scan.

    Args:
        scenario: The base scenario to transform.

    Returns:
        A new Scenario with ``degradation_preset`` set to ``"heavy_scan"``
        and ``edge_case_strategy`` set to ``"low_confidence_scan"``.

    # WHY: This strategy requires no randomness — "heavy_scan" is the only
    # target preset and the change is deterministic.  The ``seed`` parameter
    # is omitted from the signature deliberately so callers are not tempted
    # to think the output varies with seed.
    #
    # DESIGN: Only ``degradation_preset`` and ``edge_case_strategy`` change.
    # All values, verdicts, and documents remain identical so the ground-truth
    # labels stay valid — the degradation just makes the documents harder to
    # read.
    """
    return _replace_scenario(
        scenario,
        degradation_preset="heavy_scan",
        edge_case_strategy="low_confidence_scan",
    )


# ---------------------------------------------------------------------------
# Strategy 4: apply_partial_documents
# ---------------------------------------------------------------------------


def apply_partial_documents(scenario: Scenario, seed: int) -> Scenario:
    """Remove one DocumentSpec from the scenario's documents tuple.

    Simulates an incomplete submission where an applicant forgot to include
    one of the required documents.

    Args:
        scenario: The base scenario to transform.  Must contain at least two
            documents.
        seed: RNG seed controlling which document is removed.

    Returns:
        A new Scenario with one fewer document in ``documents``.
        ``edge_case_strategy`` is set to ``"partial_documents"``.

    Raises:
        ValueError: If the scenario has fewer than 2 documents.

    # WHY: Removing the only document from a single-document scenario would
    # produce an empty documents tuple, which is a degenerate state that no
    # downstream component is designed to handle.  Raising ValueError here
    # keeps the error surface explicit rather than silently producing an
    # unusable scenario.
    """
    if len(scenario.documents) < 2:
        raise ValueError(
            f"apply_partial_documents requires at least 2 documents, "
            f"but scenario {scenario.set_id!r} has {len(scenario.documents)}."
        )

    rng = random.Random(seed)
    removal_idx = rng.randrange(len(scenario.documents))

    new_documents = (
        scenario.documents[:removal_idx] + scenario.documents[removal_idx + 1 :]
    )

    return _replace_scenario(
        scenario,
        documents=new_documents,
        edge_case_strategy="partial_documents",
    )


# ---------------------------------------------------------------------------
# Strategy 5: apply_ambiguous_units
# ---------------------------------------------------------------------------


def apply_ambiguous_units(scenario: Scenario, seed: int) -> Scenario:
    """Remove the unit suffix from one Value's display_text.

    Simulates a document where a measurement is written without its unit
    (e.g. "7.5" instead of "7.5m"), requiring the extraction layer to infer
    the unit from context.

    Args:
        scenario: The base scenario to transform.
        seed: RNG seed controlling which value's display_text is stripped.

    Returns:
        A new Scenario where exactly one Value has a unit-free display_text.
        ``edge_case_strategy`` is set to ``"ambiguous_units"``.

    # DESIGN: The stripped display_text must be a valid float string so that
    # test assertions can call ``float(v.display_text)`` to confirm the unit
    # is gone.  We achieve this by removing any trailing non-numeric characters
    # after the last digit.
    #
    # WHY: Only the display_text changes; the canonical ``value`` float and
    # ``unit`` string are preserved so the ground-truth rule evaluation is
    # unaffected.  The ambiguity is purely in the rendered document.
    """
    rng = random.Random(seed)

    target_idx = rng.randrange(len(scenario.values))
    target_value = scenario.values[target_idx]

    # Strip trailing non-numeric characters from display_text.
    # WHY: Using rstrip with a broad character class rather than a hard-coded
    # unit suffix keeps the function correct even if an unusual unit appears
    # in display_text (e.g. "°" for degrees).
    strip_chars = "abcdefghijklmnopqrstuvwxyz%²°"
    strip_chars += strip_chars.upper() + " "
    numeric_text = target_value.display_text.rstrip(strip_chars).rstrip()

    # WHY: Build a new Value with only display_text changed; all other fields
    # remain identical so the ground-truth value is not corrupted.
    stripped_value = Value(
        attribute=target_value.attribute,
        value=target_value.value,
        unit=target_value.unit,
        display_text=numeric_text,
    )

    new_values = (
        scenario.values[:target_idx]
        + (stripped_value,)
        + scenario.values[target_idx + 1 :]
    )

    return _replace_scenario(
        scenario,
        values=new_values,
        edge_case_strategy="ambiguous_units",
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

# WHY: The registry maps strategy name strings to callables rather than using
# a long if/elif chain.  Adding a new strategy is a one-line dict entry, and
# the error message for unknown strategies is always up-to-date because it
# lists the actual registry keys.
#
# DESIGN: Strategies that do not use a seed (apply_low_confidence_scan) are
# wrapped in a lambda that accepts and ignores the seed argument so every
# entry in the registry has the same signature: (Scenario, int) → Scenario.
_STRATEGY_REGISTRY: dict[str, Callable[[Scenario, int], Scenario]] = {
    "missing_evidence": apply_missing_evidence,
    "conflicting_values": apply_conflicting_values,
    "low_confidence_scan": lambda scenario, seed: apply_low_confidence_scan(scenario),
    "partial_documents": apply_partial_documents,
    "ambiguous_units": apply_ambiguous_units,
}


def apply_edge_case(scenario: Scenario, strategy: str, seed: int) -> Scenario:
    """Apply the named edge-case strategy to *scenario* and return the result.

    Args:
        scenario: The base scenario to transform.
        strategy: Name of the edge-case strategy to apply.  Must be one of:
            ``"missing_evidence"``, ``"conflicting_values"``,
            ``"low_confidence_scan"``, ``"partial_documents"``,
            ``"ambiguous_units"``.
        seed: RNG seed passed through to the chosen strategy function.
            Ignored by ``"low_confidence_scan"`` (which is deterministic).

    Returns:
        A new, modified Scenario with ``edge_case_strategy`` set to
        *strategy*.

    Raises:
        ValueError: If *strategy* is not a recognised strategy name.

    # WHY: Centralising strategy dispatch here means callers (the CLI, the
    # dataset builder, tests) only ever call one function regardless of which
    # strategy is requested.  The clean error message names all known strategies
    # so a config typo surfaces immediately with an actionable message.
    """
    if strategy not in _STRATEGY_REGISTRY:
        known = ", ".join(sorted(_STRATEGY_REGISTRY))
        raise ValueError(
            f"Unknown edge-case strategy {strategy!r}.  "
            f"Known strategies: {known}."
        )

    return _STRATEGY_REGISTRY[strategy](scenario, seed)
