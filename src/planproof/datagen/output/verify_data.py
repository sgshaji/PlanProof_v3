"""Verify the structure and integrity of a generated synthetic dataset.

Usage::

    python -m planproof.datagen.output.verify_data
    python -m planproof.datagen.output.verify_data --data-dir path/to/synthetic

Exit codes:
    0 — All checks passed.
    1 — One or more checks failed; details printed to stdout.

# DESIGN: This module is intentionally a standalone script with no imports
# from the rest of the planproof package (beyond stdlib).  That means it can
# be run even if the package is only partially installed, and it doesn't
# accidentally trigger side-effects (reportlab font init, neo4j connections)
# that live in the broader package.
#
# WHY a separate verify_data module rather than a pytest test: verification of
# the *generated corpus* is an operational concern (run after corpus generation)
# rather than a unit/integration test concern (run during development).
# Making it a standalone script lets it be invoked from the Makefile target
# `verify-data` or from a CI step without requiring pytest to be installed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# WHY: These are the three canonical category directories.  Any other top-level
# directory under data/synthetic is unexpected and triggers a warning.
_EXPECTED_CATEGORIES = {"compliant", "non_compliant", "edgecase"}

# WHY: Every application set directory must contain these two reference files.
# Their absence means the reference_writer failed or the set is corrupted.
_REQUIRED_REFERENCE_FILES = [
    Path("reference") / "parcel.geojson",
    Path("reference") / "zone.json",
]

# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_category_directories(data_dir: Path) -> list[str]:
    """Verify that expected category sub-directories exist.

    # WHY: Checking directory existence before descending into sets gives an
    # early, clear error message rather than a confusing "no sets found" message
    # when a category directory is missing.

    Returns:
        List of error strings (empty = all OK).
    """
    errors: list[str] = []
    for cat in _EXPECTED_CATEGORIES:
        cat_dir = data_dir / cat
        if not cat_dir.is_dir():
            # WHY: We report all missing categories at once rather than stopping
            # at the first, so the user gets a complete picture.
            errors.append(f"Missing category directory: {cat_dir}")
    return errors


def _check_ground_truth_exists(set_dir: Path) -> list[str]:
    """Verify that ground_truth.json is present and parseable as JSON.

    # WHY: ground_truth.json is the primary evaluation artefact.  A missing or
    # malformed file renders the entire set unusable for downstream evaluation.

    Returns:
        List of error strings (empty = all OK).
    """
    errors: list[str] = []
    gt_path = set_dir / "ground_truth.json"
    if not gt_path.exists():
        errors.append(f"Missing ground_truth.json in {set_dir}")
        return errors
    try:
        json.loads(gt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in {gt_path}: {exc}")
    return errors


def _check_referenced_files_exist(set_dir: Path) -> list[str]:
    """Verify that every filename referenced in ground_truth.json exists on disk.

    # DESIGN: We read the 'documents' list from ground_truth.json and verify
    # that each document's filename is present in set_dir.  This catches cases
    # where the writer logged a filename to the sidecar but failed to write the
    # actual bytes.
    #
    # WHY: A ground_truth.json that references a non-existent file will cause
    # silent failures in the evaluation pipeline that are hard to diagnose.

    Returns:
        List of error strings (empty = all OK).
    """
    errors: list[str] = []
    gt_path = set_dir / "ground_truth.json"
    if not gt_path.exists():
        # Already caught by _check_ground_truth_exists — skip to avoid
        # duplicate errors.
        return errors
    try:
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return errors  # Already caught by _check_ground_truth_exists.

    for doc in gt.get("documents", []):
        filename = doc.get("filename")
        if not filename:
            errors.append(
                f"Document record missing 'filename' key in {gt_path}"
            )
            continue
        file_path = set_dir / filename
        if not file_path.exists():
            errors.append(
                f"Referenced file not found: {file_path}"
            )
    return errors


def _check_reference_files_exist(set_dir: Path) -> list[str]:
    """Verify that parcel.geojson and zone.json are present.

    # WHY: The rule engine reads these files to evaluate spatial rules (e.g.
    # R001 setback checks).  Missing reference files break rule evaluation.

    Returns:
        List of error strings (empty = all OK).
    """
    errors: list[str] = []
    for rel_path in _REQUIRED_REFERENCE_FILES:
        full_path = set_dir / rel_path
        if not full_path.exists():
            errors.append(f"Missing reference file: {full_path}")
    return errors


def _check_bounding_boxes(set_dir: Path) -> list[str]:
    """Verify that all bounding boxes in ground_truth.json have positive dimensions.

    # WHY: Negative or zero bounding boxes indicate a coordinate-system bug in
    # the generator or the bbox-adjustment pipeline.  Finding them at corpus-
    # generation time (rather than evaluation time) gives earlier feedback.

    Returns:
        List of error strings (empty = all OK).
    """
    errors: list[str] = []
    gt_path = set_dir / "ground_truth.json"
    if not gt_path.exists():
        return errors  # Already caught elsewhere.
    try:
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return errors

    for doc in gt.get("documents", []):
        filename = doc.get("filename", "<unknown>")
        for ext in doc.get("extractions", []):
            bb = ext.get("bounding_box", {})
            attr = ext.get("attribute", "<unknown>")
            # WHY: x and y may be zero (top-left corner), so >= 0 is the
            # correct lower bound.  Negative coordinates are always a bug.
            if bb.get("x", 0) < 0 or bb.get("y", 0) < 0:
                errors.append(
                    f"Negative bbox origin for '{attr}' in {filename} "
                    f"({set_dir.name}): x={bb.get('x')}, y={bb.get('y')}"
                )
            # WHY: Width and height must be strictly positive — zero-size boxes
            # indicate an unrendered field that was still added to placed_values.
            if bb.get("width", 0) <= 0 or bb.get("height", 0) <= 0:
                errors.append(
                    f"Non-positive bbox size for '{attr}' in {filename} "
                    f"({set_dir.name}): "
                    f"w={bb.get('width')}, h={bb.get('height')}"
                )
    return errors


# ---------------------------------------------------------------------------
# Main verification logic
# ---------------------------------------------------------------------------


def verify_dataset(data_dir: Path) -> tuple[int, int, list[str]]:
    """Verify the synthetic dataset at data_dir.

    Runs all checks and accumulates errors without short-circuiting.

    Args:
        data_dir: Root directory of the synthetic dataset (e.g. data/synthetic).

    Returns:
        (n_sets_checked, n_errors, error_messages) tuple.
        n_errors == 0 means all checks passed.
    """
    all_errors: list[str] = []
    n_sets = 0

    if not data_dir.exists():
        return 0, 1, [f"Dataset directory not found: {data_dir}"]
    if not data_dir.is_dir():
        return 0, 1, [f"Not a directory: {data_dir}"]

    # Check 1: expected category directories.
    all_errors.extend(_check_category_directories(data_dir))

    # Check 2–5: per-set checks over all categories present on disk.
    # WHY: We iterate over whatever categories exist rather than only the
    # expected ones — this way, a malformed category that *does* exist is
    # still checked even if it is not one of the three expected ones.
    for cat_dir in sorted(data_dir.iterdir()):
        if not cat_dir.is_dir():
            continue
        for set_dir in sorted(cat_dir.iterdir()):
            if not set_dir.is_dir():
                continue
            n_sets += 1
            all_errors.extend(_check_ground_truth_exists(set_dir))
            all_errors.extend(_check_referenced_files_exist(set_dir))
            all_errors.extend(_check_reference_files_exist(set_dir))
            all_errors.extend(_check_bounding_boxes(set_dir))

    return n_sets, len(all_errors), all_errors


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the verify_data CLI.

    # WHY: Separating parser construction lets it be unit-tested without
    # invoking sys.argv.
    """
    parser = argparse.ArgumentParser(
        prog="planproof.datagen.output.verify_data",
        description="Verify the structure and integrity of a synthetic dataset.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/synthetic"),
        help="Root directory of the synthetic dataset (default: data/synthetic).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI main function.  Prints a summary and returns an exit code.

    # WHY: Returning an int (rather than calling sys.exit directly) makes the
    # function testable without the test process exiting.

    Returns:
        0 if all checks pass, 1 if any check fails.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    data_dir: Path = args.data_dir

    print(f"Verifying dataset at: {data_dir.resolve()}")
    print()

    n_sets, n_errors, error_messages = verify_dataset(data_dir)

    print(f"Sets checked : {n_sets}")
    print(f"Errors found : {n_errors}")

    if error_messages:
        print()
        print("ERRORS:")
        for msg in error_messages:
            print(f"  - {msg}")
        print()
        print("RESULT: FAIL")
        return 1

    print()
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
