"""Seeded train/val/test split utilities for the PlanProof synthetic corpus.

# WHY: Reproducible splits are essential for fair benchmarking.  If the split
# changes between runs, metrics become incomparable across experiments.  We
# achieve reproducibility by (a) sorting set_ids before shuffling so filesystem
# discovery order does not matter, and (b) seeding Python's random module with
# a caller-supplied value so the shuffle is fully deterministic.

# DESIGN: All public functions are pure (or side-effect-isolated in the write
# helpers).  compute_split() takes only plain Python values and returns a plain
# dict — no I/O, no global state.  This makes it trivially testable and safe to
# call from any context (CLI, notebook, pytest).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_split(
    set_ids: list[str],
    seed: int = 42,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
) -> dict[str, str]:
    """Assign each set_id to 'train', 'val', or 'test'.

    Returns a dict mapping set_id -> split name.
    Deterministic: same inputs always produce the same assignment.

    Args:
        set_ids:     All dataset set identifiers to split.
        seed:        RNG seed for reproducibility.
        train_ratio: Fraction of sets for training (default 0.6).
        val_ratio:   Fraction of sets for validation (default 0.2).
        test_ratio:  Fraction of sets for testing  (default 0.2).

    Returns:
        Mapping of {set_id: "train" | "val" | "test"}.

    Raises:
        ValueError: If the three ratios do not sum to approximately 1.0.
    """
    # WHY: Validate ratios early so callers get a helpful error instead of a
    # silent data-loss bug where some sets are never assigned a bucket.
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-6:
        raise ValueError(
            f"ratios must sum to 1.0, got "
            f"train={train_ratio} + val={val_ratio} + test={test_ratio} "
            f"= {train_ratio + val_ratio + test_ratio:.6f}"
        )

    if not set_ids:
        return {}

    # WHY: Sort before shuffling so the result is independent of the order in
    # which the caller discovered the set directories (filesystem traversal
    # order is OS-dependent and non-deterministic across platforms).
    sorted_ids = sorted(set_ids)

    # WHY: Use a local Random instance rather than the global random.shuffle()
    # to avoid contaminating the global RNG state, which could affect other
    # code running in the same process (e.g. test fixtures).
    rng = random.Random(seed)
    shuffled = list(sorted_ids)
    rng.shuffle(shuffled)

    n = len(shuffled)
    # DESIGN: We compute integer cut-points using round() rather than int()
    # (which always floors) so that e.g. 0.2 * 50 = 10.0 → 10 rather than
    # occasionally 9 due to floating-point representation errors.
    n_train = round(n * train_ratio)
    n_val = round(n * val_ratio)
    # Test gets everything that remains so the three buckets exactly partition
    # the full set with no overlap and no remainder.

    train_ids = shuffled[:n_train]
    val_ids = shuffled[n_train : n_train + n_val]
    test_ids = shuffled[n_train + n_val :]

    assignment: dict[str, str] = {}
    for sid in train_ids:
        assignment[sid] = "train"
    for sid in val_ids:
        assignment[sid] = "val"
    for sid in test_ids:
        assignment[sid] = "test"

    return assignment


def scan_set_ids(synthetic_dir: Path) -> list[str]:
    """Discover all set IDs by scanning synthetic_dir subdirectories.

    # WHY: The directory layout is the authoritative record of which sets
    # exist.  Scanning at split-time means we don't need a separate registry
    # file to be kept in sync with the filesystem.

    Returns a sorted list of set IDs (names of leaf directories), or raises
    FileNotFoundError if synthetic_dir does not exist.

    Args:
        synthetic_dir: Root of the synthetic dataset (contains compliant/,
                       non_compliant/, edge_case/ etc.).

    Returns:
        Sorted list of set IDs found across all category subdirectories.

    Raises:
        FileNotFoundError: If synthetic_dir does not exist on disk.
    """
    if not synthetic_dir.exists():
        raise FileNotFoundError(
            f"Synthetic data directory not found: {synthetic_dir}\n"
            "Run 'make generate-data' to create the synthetic dataset first."
        )

    set_ids: list[str] = []
    # DESIGN: We iterate over direct children of synthetic_dir (e.g. compliant/,
    # non_compliant/) and then over their children (the actual set folders).
    # This two-level walk matches the documented directory layout without
    # requiring a hardcoded list of category names.
    for category_dir in sorted(synthetic_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        for set_dir in sorted(category_dir.iterdir()):
            if set_dir.is_dir():
                set_ids.append(set_dir.name)

    return set_ids


def write_split_manifest(
    synthetic_dir: Path,
    output_path: Path,
    seed: int = 42,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
) -> None:
    """Scan synthetic_dir, compute split, and write split_manifest.json.

    # WHY: The manifest serialises the split so downstream code (dataloader,
    # evaluation harness) can read it without re-running the split logic —
    # preventing accidental desynchronisation if the seed or ratios change.

    The output JSON has the shape:
    {
      "seed": 42,
      "ratios": {"train": 0.6, "val": 0.2, "test": 0.2},
      "splits": {
        "train": ["SET_COMPLIANT_42000", ...],
        "val":   [...],
        "test":  [...]
      },
      "counts": {"train": 30, "val": 10, "test": 10}
    }

    Args:
        synthetic_dir: Root directory of the synthetic dataset.
        output_path:   Destination path for split_manifest.json.
        seed:          RNG seed (default 42, matching the generation seed).
        train_ratio:   Fraction for training split.
        val_ratio:     Fraction for validation split.
        test_ratio:    Fraction for test split.

    Raises:
        FileNotFoundError: If synthetic_dir does not exist.
    """
    set_ids = scan_set_ids(synthetic_dir)
    assignment = compute_split(
        set_ids,
        seed=seed,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
    )

    # Invert the flat assignment map into the grouped splits structure.
    splits: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for sid, bucket in assignment.items():
        splits[bucket].append(sid)

    # WHY: Sort each bucket so the manifest file is stable and human-readable.
    # Without sorting, two runs with the same seed could produce JSON with
    # different key orders, generating noisy diffs in version control.
    for bucket in splits:
        splits[bucket].sort()

    counts: dict[str, int] = {k: len(v) for k, v in splits.items()}
    manifest = {
        "seed": seed,
        "ratios": {"train": train_ratio, "val": val_ratio, "test": test_ratio},
        "splits": splits,
        "counts": counts,
    }

    # WHY: Create parent directories automatically so the caller does not need
    # to pre-create data/splits/ before running the script.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    total = sum(counts.values())
    print(
        f"Split manifest written -> {output_path}\n"
        f"  total sets : {total}\n"
        f"  train      : {counts['train']}\n"
        f"  val        : {counts['val']}\n"
        f"  test       : {counts['test']}"
    )


# ---------------------------------------------------------------------------
# CLI entry-point  (python -m planproof.datagen.split)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # DESIGN: Default paths follow the project convention:
    #   data/synthetic/  — corpus root (gitignored)
    #   data/splits/     — manifest outputs (committed to git)
    _repo_root = Path(__file__).resolve().parents[4]
    _synthetic_dir = _repo_root / "data" / "synthetic"
    _output_path = _repo_root / "data" / "splits" / "split_manifest.json"

    write_split_manifest(_synthetic_dir, _output_path)
