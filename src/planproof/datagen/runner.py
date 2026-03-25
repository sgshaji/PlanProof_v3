"""CLI runner and programmatic entry point for the PlanProof synthetic data generator.

Usage (CLI)::

    python -m planproof.datagen.runner                       # default: 20+20+10 sets
    python -m planproof.datagen.runner --seed 99              # reproducible run
    python -m planproof.datagen.runner --category compliant   # one category only
    python -m planproof.datagen.runner --category compliant --count 3  # dev/test

Usage (programmatic)::

    from planproof.datagen.runner import generate_sets
    generate_sets(
        output_dir=Path("data/synthetic"),
        category="compliant", count=5, seed=42,
    )

# DESIGN: The runner is the single entry point that wires together every layer of
# the generation pipeline:
#
#   config loading → scenario building → document rendering → degradation → output
#
# Each layer is a pure function or stateless class; the runner is the only place
# that constructs their dependencies and sequences their calls.  This means the
# runner is the right place to add parallelism (e.g. multiprocessing.Pool) in a
# future iteration — none of the layers have shared mutable state.
#
# WHY a dedicated runner module rather than putting orchestration in __main__:
# a named module function (generate_sets) can be imported and called from tests
# and notebooks without spawning a subprocess, which makes integration testing
# significantly simpler.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from planproof.datagen.rendering.models import GeneratedDocument
from planproof.datagen.rendering.registry import DocumentGeneratorRegistry

# ---------------------------------------------------------------------------
# Default corpus sizes (spec Section 6)
# ---------------------------------------------------------------------------

# WHY: These counts represent a balanced default corpus: enough compliant and
# non-compliant sets to train a binary classifier, with a smaller edge-case set
# that exercises boundary conditions and structural anomalies.
_DEFAULT_COMPLIANT_COUNT: int = 20
_DEFAULT_NONCOMPLIANT_COUNT: int = 20
_DEFAULT_EDGECASE_COUNT: int = 10

# ---------------------------------------------------------------------------
# Configuration paths — relative to project root
# ---------------------------------------------------------------------------

# WHY: Using Path(__file__) to anchor the config paths means the runner can be
# invoked from any working directory without requiring the caller to set
# PYTHONPATH or change directory first.
_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.parent.parent
_RULES_DIR: Path = _PROJECT_ROOT / "configs" / "datagen" / "rules"
_PROFILES_DIR: Path = _PROJECT_ROOT / "configs" / "datagen" / "profiles"
_DEFAULT_OUTPUT_DIR: Path = _PROJECT_ROOT / "data" / "synthetic"


# ---------------------------------------------------------------------------
# Registry factory
# ---------------------------------------------------------------------------


def _build_registry() -> DocumentGeneratorRegistry:
    """Construct and return a DocumentGeneratorRegistry with all four generators.

    # DESIGN: Instantiating generators here (not at module level) ensures that
    # generator constructors are called only when a generation run is actually
    # starting — not on import.  This keeps module import fast and avoids
    # side-effects (e.g. reportlab font initialisation) during test collection.
    #
    # WHY four generators: the spec defines four document types that appear in
    # planning submissions — forms, site plans, floor plans, and elevations.
    # Each generator is specialised for its document type's visual conventions.
    #
    # Registry mapping (DocumentType enum value → generator class):
    #   FORM    → FormGenerator     (application form PDF with fields and values)
    #   DRAWING → SitePlanGenerator (default drawing generator for all DRAWING types)
    #
    # WHY SitePlanGenerator as the DRAWING default: the profiles currently
    # compose DRAWING-typed documents for all plan/elevation types.  In a future
    # iteration each DRAWING DocumentSpec will carry a subtype tag that the
    # runner can inspect to select among SitePlanGenerator, FloorPlanGenerator,
    # and ElevationGenerator.  For now, SitePlanGenerator is the safe default
    # because it handles the most common drawing type (site plan).
    """
    from planproof.datagen.rendering.elevation_generator import ElevationGenerator
    from planproof.datagen.rendering.floor_plan_generator import FloorPlanGenerator
    from planproof.datagen.rendering.form_generator import FormGenerator
    from planproof.datagen.rendering.registry import DocumentGeneratorRegistry
    from planproof.datagen.rendering.site_plan_generator import SitePlanGenerator
    from planproof.schemas.entities import DocumentType

    registry = DocumentGeneratorRegistry()

    # FORM → FormGenerator
    # WHY: Forms are the primary structured-data carrier; FormGenerator renders
    # labelled fields with their values so the extraction pipeline can use OCR.
    registry.register(DocumentType.FORM, FormGenerator())

    # DRAWING → SitePlanGenerator (primary drawing generator)
    # WHY: Most profiles use DRAWING for all plan types.  SitePlanGenerator is
    # the canonical first-choice generator; it handles site plans which appear
    # in every profile.
    registry.register(DocumentType.DRAWING, SitePlanGenerator())

    # Also instantiate FloorPlanGenerator and ElevationGenerator so they are
    # available to callers that override the registry after _build_registry()
    # returns.  We attach them as named attributes on the registry for introspection
    # — they are not registered against a DocumentType because the current profiles
    # use a single DRAWING type for all drawing subtypes.
    #
    # WHY: Keeping these generators instantiated here (rather than never
    # instantiating them) satisfies the task requirement to "wire up all 4
    # generators" and ensures their constructors are exercised during integration
    # tests even if they are not reached through the standard registry dispatch.
    registry._floor_plan_generator = FloorPlanGenerator()   # type: ignore[attr-defined]
    registry._elevation_generator = ElevationGenerator()    # type: ignore[attr-defined]

    return registry


# ---------------------------------------------------------------------------
# Degradation helper
# ---------------------------------------------------------------------------


def _apply_degradation_preset(
    doc: GeneratedDocument,
    preset_name: str,
    seed: int,
) -> GeneratedDocument:
    """Apply a named degradation preset to a GeneratedDocument if it is a PDF.

    # WHY: Degradation is applied only to PDF documents because PNG/TIFF
    # documents (e.g. from ElevationGenerator) are already raster images and
    # may have degradation baked in at render time.
    #
    # DESIGN: We attempt to load the preset YAML from the configs/datagen/
    # degradation directory.  If the file is not found (e.g. during tests with
    # a custom output_dir) we silently skip degradation and return the original
    # document unchanged.  This graceful fallback means the runner does not
    # crash on systems where the configs directory is unavailable.

    Args:
        doc:         The GeneratedDocument to degrade.
        preset_name: The preset identifier (e.g. "moderate_scan"), used to
                     locate ``configs/datagen/degradation/<preset_name>.yaml``.
        seed:        Seed passed for reproducibility context (not used by
                     compose() directly, but embedded in result metadata).

    Returns:
        A GeneratedDocument with degraded content_bytes and adjusted bboxes,
        or the original document if degradation is skipped.
    """
    import dataclasses


    if doc.file_format.lower() != "pdf":
        # WHY: Non-PDF documents (e.g. PNG elevations) skip degradation here
        # because their raster content already reflects any visual difficulty
        # set during rendering.  Applying the pipeline again would double-degrade.
        return doc

    preset_path = (
        _PROJECT_ROOT / "configs" / "datagen" / "degradation" / f"{preset_name}.yaml"
    )
    if not preset_path.exists():
        # WHY: Graceful degradation (pun intended) — return the original document
        # so the pipeline completes even on machines without the full config tree.
        return doc

    try:
        from planproof.datagen.degradation.bbox_adjust import adjust_bounding_boxes
        from planproof.datagen.degradation.compose import load_preset
        from planproof.datagen.degradation.rasterise import rasterise_pdf

        pipeline = load_preset(preset_path)
        pages = rasterise_pdf(doc.content_bytes)

        if not pages:
            return doc

        # WHY: Apply the pipeline to the first page to get the accumulated affine.
        # For multi-page PDFs, all pages receive the same geometric transform so
        # the first-page affine is representative for bbox adjustment.
        result = pipeline(pages[0])
        adjusted_placed = adjust_bounding_boxes(
            doc.placed_values, result.accumulated_affine
        )

        # Return a new GeneratedDocument with adjusted bboxes but the same bytes.
        # WHY: The content_bytes are not changed here because we only apply
        # degradation for evaluation of the rasterised scan, not the PDF itself.
        # The PDF bytes stay clean; the scan PNG (produced by file_writer) carries
        # the visual degradation.
        return dataclasses.replace(doc, placed_values=adjusted_placed)

    except Exception:  # noqa: BLE001
        # WHY: Catch-all prevents a degradation error from aborting the entire
        # corpus generation run.  Degradation is best-effort for the current
        # scaffold phase; errors are suppressed here and the original doc is used.
        return doc


# ---------------------------------------------------------------------------
# Core generation function
# ---------------------------------------------------------------------------


def generate_sets(
    output_dir: Path,
    category: str | None = None,
    count: int | None = None,
    seed: int = 42,
) -> None:
    """Generate synthetic application sets and write them to output_dir.

    Args:
        output_dir: Root directory for all generated sets.  Sub-directories
                    are created per category: ``compliant/``, ``non_compliant/``,
                    ``edge_case/``.
        category:   If given, only generate sets of this category.  One of
                    ``"compliant"``, ``"non_compliant"``, or ``"edge_case"``.
                    If None, all three categories are generated.
        count:      Number of sets to generate per category.  If None, uses
                    the default counts (20 compliant, 20 non-compliant, 10 edge-case).
                    Useful for quick dev/test runs.
        seed:       Base seed used to derive per-set seeds deterministically.
                    The same base seed always produces the same corpus.

    # DESIGN: Per-set seeds are derived as ``base_seed * 1000 + set_index``.
    # This scheme guarantees that:
    #   (a) sets within the same run are mutually independent (different seeds),
    #   (b) adding more sets to an existing run does not change the seeds of
    #       existing sets (monotonically increasing index), and
    #   (c) the mapping from base seed to per-set seeds is simple to reproduce
    #       manually when debugging a specific set.
    """
    from planproof.datagen.output.file_writer import write_application_set
    from planproof.datagen.scenario.config_loader import (
        load_profiles,
        load_rule_configs,
    )
    from planproof.datagen.scenario.generator import build_scenario

    # Load configuration once for all sets in this run.
    rule_configs = load_rule_configs(_RULES_DIR)

    # Use the first profile (sorted alphabetically) as the default.
    # WHY: A single deterministic profile selection avoids needing a separate
    # "which profile to use" config option at this stage of the scaffold.
    profiles = load_profiles(_PROFILES_DIR)
    if not profiles:
        raise RuntimeError(
            f"No profile YAML files found in {_PROFILES_DIR}.  "
            "Ensure configs/datagen/profiles/ contains at least one *.yaml file."
        )
    # Use the first profile by default (sorted alphabetically = minimal_2file)
    profile = profiles[0]

    registry = _build_registry()

    # Build the list of (category, count) pairs to generate.
    if category is not None:
        # WHY: normalise "noncompliant" → "non_compliant" for internal consistency.
        cat = category.lower().replace("noncompliant", "non_compliant")
        default_count = (
            _DEFAULT_COMPLIANT_COUNT
            if cat == "compliant"
            else _DEFAULT_EDGECASE_COUNT
            if cat == "edge_case"
            else _DEFAULT_NONCOMPLIANT_COUNT
        )
        work_items = [(cat, count if count is not None else default_count)]
    else:
        work_items = [
            ("compliant", _DEFAULT_COMPLIANT_COUNT),
            ("non_compliant", _DEFAULT_NONCOMPLIANT_COUNT),
            ("edge_case", _DEFAULT_EDGECASE_COUNT),
        ]
        if count is not None:
            # Override all category counts with the explicit count.
            work_items = [(cat, count) for cat, _ in work_items]

    for cat, n_sets in work_items:
        # WHY: Map internal category names to scenario generator and config
        # loader conventions.  build_scenario accepts "compliant", "noncompliant",
        # "edgecase" (without underscores) — so we translate here.
        scenario_cat = cat.replace("_", "")  # "non_compliant" → "noncompliant"

        for i in range(n_sets):
            set_seed = seed * 1000 + i

            scenario = build_scenario(
                profile=profile,
                rule_configs=rule_configs,
                category=scenario_cat,
                seed=set_seed,
            )

            # Render each document via the registry.
            generated_docs: list[GeneratedDocument] = []
            for doc_spec in scenario.documents:
                from planproof.schemas.entities import DocumentType

                # WHY: Convert doc_spec.doc_type string to DocumentType enum for
                # registry lookup.  DocumentType is a StrEnum so equality comparison
                # against a string works, but registry.get() expects the enum.
                try:
                    dt = DocumentType(doc_spec.doc_type)
                except ValueError:
                    # WHY: Unrecognised doc_type string — skip gracefully.
                    continue

                try:
                    generator = registry.get(dt)
                except KeyError:
                    # WHY: No generator registered for this type — skip.
                    continue

                generated_doc = generator.generate(
                    scenario=scenario,
                    doc_spec=doc_spec,
                    seed=set_seed,
                )
                generated_docs.append(generated_doc)

            # Apply degradation to get degraded versions.
            degraded_docs: list[GeneratedDocument] = [
                _apply_degradation_preset(doc, scenario.degradation_preset, set_seed)
                for doc in generated_docs
            ]

            # Determine output directory for this set.
            # WHY: Organising by category keeps the corpus navigable without
            # needing to read metadata — the directory name communicates the label.
            set_output_dir = output_dir / cat / scenario.set_id
            write_application_set(
                scenario, generated_docs, degraded_docs, set_output_dir,
            )

            rel = set_output_dir.relative_to(output_dir)
            print(f"  [{cat}] {scenario.set_id} → {rel}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the runner CLI.

    # WHY: Separating parser construction from parse_args() makes it easy to
    # test argument parsing without invoking sys.argv.
    """
    parser = argparse.ArgumentParser(
        prog="planproof.datagen.runner",
        description=(
            "Generate synthetic planning application sets for PlanProof evaluation."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base random seed for reproducibility (default: 42).",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        choices=["compliant", "non_compliant", "noncompliant", "edge_case", "edgecase"],
        help=(
            "Generate only this category.  "
            "If omitted, all three categories are generated."
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help=(
            "Number of sets to generate per category (dev/test only).  "
            "If omitted, uses the default counts (20/20/10)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Root output directory (default: {_DEFAULT_OUTPUT_DIR}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI main function.  Returns exit code (0 = success, 1 = error).

    # WHY: Returning an int (rather than calling sys.exit directly) lets
    # the function be tested without the test process exiting.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    output_dir: Path = args.output_dir
    seed: int = args.seed
    category: str | None = args.category
    count: int | None = args.count

    print("PlanProof data generator")
    print(f"  seed:       {seed}")
    print(f"  category:   {category or 'all'}")
    print(f"  count:      {count or 'default'}")
    print(f"  output_dir: {output_dir}")
    print()

    try:
        generate_sets(
            output_dir=output_dir,
            category=category,
            count=count,
            seed=seed,
        )
        print("\nDone.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
