"""verify_dataset.py — Dataset integrity and completeness verification script.

# WHY: After generating and sealing the synthetic dataset, we need a single
# authoritative check that confirms:
#   (a) the directory structure is what we expect,
#   (b) the split manifest exists and has the correct 30/10/10 distribution,
#   (c) no file has been modified, added, or deleted since sealing.
#
# This script is designed to be run in CI (exits 0 on pass, 1 on fail) and
# by developers checking their local corpus before training.

# DESIGN: The script deliberately avoids importing heavy ML dependencies so it
# can run in any environment that has Python 3.11+.  All output goes to stdout
# so it can be captured by CI logs.  Checks are independent and all run even
# if earlier checks fail, giving a complete picture of what needs fixing.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project-relative paths
# ---------------------------------------------------------------------------

# WHY: Resolve the repo root from this script's location so the script can be
# run from any working directory (e.g. `python scripts/verify_dataset.py`
# from the repo root, or from a CI step with a different cwd).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SYNTHETIC_DIR = _REPO_ROOT / "data" / "synthetic"
_SPLITS_DIR = _REPO_ROOT / "data" / "splits"
_SPLIT_MANIFEST = _SPLITS_DIR / "split_manifest.json"
_INTEGRITY_MANIFEST = _SPLITS_DIR / "integrity_manifest.json"

# DESIGN: Expected category sub-directories and per-category set counts.
# These match the generation spec: 20 compliant + 20 non_compliant + 10 edge_case.
_EXPECTED_CATEGORIES: dict[str, int] = {
    "compliant": 20,
    "non_compliant": 20,
    "edge_case": 10,
}

# WHY: The split spec requires a 60/20/20 distribution over 50 total sets.
_EXPECTED_COUNTS = {"train": 30, "val": 10, "test": 10}

# WHY: 64 KiB chunks — same as integrity.py — so hashing is consistent.
_CHUNK_SIZE = 65_536


# ---------------------------------------------------------------------------
# Colour helpers (graceful fallback when not in a TTY)
# ---------------------------------------------------------------------------

def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if sys.stdout.isatty() else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if sys.stdout.isatty() else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if sys.stdout.isatty() else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if sys.stdout.isatty() else s


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_directory_structure() -> list[str]:
    """Verify that synthetic_dir exists with the expected category layout.

    # WHY: An absent or mis-structured directory is the first thing to detect;
    # subsequent checks would produce misleading errors if we skipped this.

    Returns:
        List of failure messages (empty list means all checks passed).
    """
    failures: list[str] = []

    if not _SYNTHETIC_DIR.exists():
        failures.append(
            f"synthetic_dir not found: {_SYNTHETIC_DIR}\n"
            "  -> Run 'make generate-data' to create the dataset."
        )
        # Cannot check sub-structure without the root
        return failures

    for category, expected_count in _EXPECTED_CATEGORIES.items():
        cat_dir = _SYNTHETIC_DIR / category
        if not cat_dir.exists():
            failures.append(f"Missing category directory: {cat_dir}")
            continue

        actual_dirs = [d for d in cat_dir.iterdir() if d.is_dir()]
        if len(actual_dirs) != expected_count:
            failures.append(
                f"{category}: expected {expected_count} set folders, "
                f"found {len(actual_dirs)}"
            )

    return failures


def check_split_manifest() -> list[str]:
    """Verify split_manifest.json exists and has correct split counts.

    # WHY: The split manifest is the contract between data generation and model
    # training.  Wrong counts (e.g. 25/15/10 instead of 30/10/10) would bias
    # training and invalidate comparison with published results.

    Returns:
        List of failure messages.
    """
    failures: list[str] = []

    if not _SPLIT_MANIFEST.exists():
        failures.append(
            f"split_manifest.json not found: {_SPLIT_MANIFEST}\n"
            "  -> Run 'make seal-data' to generate the manifests."
        )
        return failures

    try:
        manifest = json.loads(_SPLIT_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"split_manifest.json is not valid JSON: {exc}")
        return failures

    # Validate required top-level keys
    for key in ("seed", "ratios", "splits", "counts"):
        if key not in manifest:
            failures.append(f"split_manifest.json missing required key: {key!r}")

    if "counts" in manifest:
        for split_name, expected in _EXPECTED_COUNTS.items():
            actual = manifest["counts"].get(split_name, "MISSING")
            if actual != expected:
                failures.append(
                    f"split counts[{split_name!r}]: expected {expected}, got {actual}"
                )

    # Cross-check: counts must match actual list lengths
    if "splits" in manifest and "counts" in manifest:
        for split_name in ("train", "val", "test"):
            listed = len(manifest["splits"].get(split_name, []))
            declared = manifest["counts"].get(split_name, 0)
            if listed != declared:
                failures.append(
                    f"split manifest inconsistency: splits[{split_name!r}] "
                    f"has {listed} items but counts[{split_name!r}] = {declared}"
                )

    return failures


def _md5_of_file(path: Path) -> str:
    """Compute MD5 hex digest of a file in chunks.

    # WHY: Copied here (rather than imported from integrity.py) so the
    # verification script has zero runtime dependencies on internal modules —
    # it must work even if the planproof package is not installed.
    """
    h = hashlib.md5()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def check_integrity_manifest() -> list[str]:
    """Re-compute MD5 for every file listed in integrity_manifest.json.

    # WHY: This is the core tamper-evidence check.  Any mismatch means a file
    # was modified after sealing — whether by accident or intentional update
    # that was not followed by re-sealing.

    Returns:
        List of failure messages.
    """
    failures: list[str] = []

    if not _INTEGRITY_MANIFEST.exists():
        failures.append(
            f"integrity_manifest.json not found: {_INTEGRITY_MANIFEST}\n"
            "  -> Run 'make seal-data' to generate the manifests."
        )
        return failures

    if not _SYNTHETIC_DIR.exists():
        failures.append(
            "Cannot verify integrity: synthetic_dir does not exist.\n"
            "  -> Run 'make generate-data' first."
        )
        return failures

    try:
        manifest = json.loads(_INTEGRITY_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"integrity_manifest.json is not valid JSON: {exc}")
        return failures

    recorded_hashes: dict[str, str] = manifest.get("hashes", {})
    if not recorded_hashes:
        failures.append("integrity_manifest.json contains no file hashes.")
        return failures

    # --- Check 1: every recorded file still exists and matches its hash ---
    mismatches: list[str] = []
    missing: list[str] = []

    for rel_path_str, expected_digest in recorded_hashes.items():
        # WHY: Use Path(rel_path_str) to handle the forward-slash keys on all
        # platforms; Python's Path constructor normalises separators.
        abs_path = _SYNTHETIC_DIR / Path(rel_path_str)
        if not abs_path.exists():
            missing.append(rel_path_str)
            continue

        actual_digest = _md5_of_file(abs_path)
        if actual_digest != expected_digest:
            mismatches.append(
                f"  MISMATCH: {rel_path_str}\n"
                f"    expected : {expected_digest}\n"
                f"    actual   : {actual_digest}"
            )

    if missing:
        failures.append(
            f"{len(missing)} file(s) in integrity manifest no longer exist:\n"
            + "\n".join(f"  MISSING: {p}" for p in missing[:10])
            + ("\n  ... (truncated)" if len(missing) > 10 else "")
        )

    if mismatches:
        failures.append(
            f"{len(mismatches)} file(s) have changed since sealing:\n"
            + "\n".join(mismatches[:10])
            + ("\n  ... (truncated)" if len(mismatches) > 10 else "")
        )

    # --- Check 2: no new files have appeared since sealing ---
    # WHY: A file added after sealing could be a regenerated (different-seed)
    # set sneaking into the corpus, silently inflating or biasing the dataset.
    current_files: set[str] = set()
    for file_path in _SYNTHETIC_DIR.rglob("*"):
        if file_path.is_file():
            current_files.add(file_path.relative_to(_SYNTHETIC_DIR).as_posix())

    new_files = current_files - set(recorded_hashes.keys())
    if new_files:
        failures.append(
            f"{len(new_files)} new file(s) present on disk but not in manifest "
            "(re-run 'make seal-data' if this is intentional):\n"
            + "\n".join(f"  NEW: {p}" for p in sorted(new_files)[:10])
            + ("\n  ... (truncated)" if len(new_files) > 10 else "")
        )

    return failures


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all dataset verification checks and print a PASS/FAIL summary.

    Returns:
        0 if all checks pass, 1 if any check fails.
    """
    print(_bold("\n=== PlanProof Dataset Verification ===\n"))

    check_results: list[tuple[str, list[str]]] = [
        ("Directory structure", check_directory_structure()),
        ("Split manifest",      check_split_manifest()),
        ("Integrity manifest",  check_integrity_manifest()),
    ]

    any_failure = False
    for check_name, failures in check_results:
        if failures:
            any_failure = True
            print(_red(f"[FAIL] {check_name}"))
            for msg in failures:
                # Indent each line of the failure message for readability
                for line in msg.splitlines():
                    print(f"       {line}")
        else:
            print(_green(f"[PASS] {check_name}"))

    print()
    if any_failure:
        print(_red(_bold("RESULT: FAIL — one or more checks did not pass.")))
        print(
            _yellow(
                "       See failure details above.  Run 'make generate-data' "
                "and/or 'make seal-data' as appropriate."
            )
        )
        return 1
    else:
        print(_green(_bold("RESULT: PASS — all dataset checks OK.")))
        return 0


if __name__ == "__main__":
    sys.exit(main())
