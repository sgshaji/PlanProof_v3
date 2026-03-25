"""MD5 integrity manifest for the PlanProof synthetic corpus.

# WHY: A dataset used for benchmarking must be immutable after sealing.  Any
# accidental regeneration, file truncation, or bit-rot would silently change
# experimental outcomes.  The integrity manifest records the MD5 digest of
# every file at seal time so verify_dataset.py can detect any subsequent
# modification, addition, or deletion.

# DESIGN: MD5 is chosen over SHA-256 because (a) we are protecting against
# accidental corruption rather than adversarial tampering, (b) MD5 is ~3×
# faster than SHA-256 on large binary files (PDFs, PNGs), and (c) the Python
# standard library ships hashlib with MD5 on all platforms.  If cryptographic
# strength is ever required, swapping the algorithm is a one-line change.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# WHY: 64 KiB chunks balance memory use against syscall overhead.  For a
# typical 500 KB PDF this means ~8 read calls — negligible overhead.
_CHUNK_SIZE = 65_536


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _md5_of_file(path: Path) -> str:
    """Return the MD5 hex digest of a single file.

    # WHY: Reads in chunks so large files (multi-page PDFs, high-res PNGs) do
    # not need to be loaded entirely into memory at once.

    Args:
        path: Absolute path to the file to hash.

    Returns:
        Lowercase hex string of the MD5 digest (32 characters).
    """
    h = hashlib.md5()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def compute_file_hashes(synthetic_dir: Path) -> dict[str, str]:
    """Compute MD5 hash for every file in synthetic_dir (recursive).

    # WHY: Returns a flat dict rather than a nested structure so callers can
    # perform O(1) lookups by relative path without navigating a tree.

    Keys are relative paths with forward slashes so the manifest is
    platform-independent and produces identical JSON on Windows, macOS, and
    Linux.

    Args:
        synthetic_dir: Root directory to walk.  May contain any nesting depth.

    Returns:
        Dict mapping relative_path_str -> MD5 hex digest, sorted by key.
        Empty dict if the directory contains no files.

    Raises:
        FileNotFoundError: If synthetic_dir does not exist on disk.
    """
    if not synthetic_dir.exists():
        raise FileNotFoundError(
            f"Directory not found: {synthetic_dir}\n"
            "Run 'make generate-data' to create the synthetic dataset first."
        )

    hashes: dict[str, str] = {}

    # WHY: rglob("*") visits every node; we skip directories because they have
    # no bytes to hash.  Using sorted() on the generator gives a consistent
    # traversal order across OSes so the manifest diff is clean in git.
    for file_path in sorted(synthetic_dir.rglob("*")):
        if not file_path.is_file():
            continue

        # DESIGN: Compute the path relative to synthetic_dir, then convert all
        # backslashes to forward slashes.  This is a no-op on POSIX and ensures
        # portability on Windows where Path uses backslashes by default.
        rel = file_path.relative_to(synthetic_dir)
        rel_str = rel.as_posix()  # always uses "/"

        hashes[rel_str] = _md5_of_file(file_path)

    return hashes


def write_integrity_manifest(
    synthetic_dir: Path,
    output_path: Path,
) -> None:
    """Compute MD5 hashes for all files and write integrity_manifest.json.

    # WHY: Sealing the manifest at a known point in time (iso8601 timestamp)
    # gives auditors a clear marker for "when was this data frozen?".  Combined
    # with git history on the manifest file itself, this provides a full audit
    # trail.

    The output JSON has the shape:
    {
      "generated_at": "2026-03-25T12:00:00+00:00",
      "total_files": 350,
      "hashes": {
        "compliant/SET_COMPLIANT_42000/ground_truth.json": "a1b2c3...",
        ...
      }
    }

    Args:
        synthetic_dir: Root directory of the synthetic dataset to hash.
        output_path:   Destination path for integrity_manifest.json.

    Raises:
        FileNotFoundError: If synthetic_dir does not exist.
    """
    hashes = compute_file_hashes(synthetic_dir)

    manifest = {
        # WHY: UTC timestamp with timezone offset so the value is unambiguous
        # regardless of where the sealing process runs.
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "total_files": len(hashes),
        "hashes": hashes,
    }

    # WHY: Create parent directories automatically so the caller does not need
    # to pre-create data/splits/ before running the script.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(
        f"Integrity manifest written -> {output_path}\n"
        f"  total files hashed : {manifest['total_files']}\n"
        f"  generated_at       : {manifest['generated_at']}"
    )


# ---------------------------------------------------------------------------
# CLI entry-point  (python -m planproof.datagen.integrity)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # DESIGN: Default paths follow the project convention:
    #   data/synthetic/  — corpus root (gitignored)
    #   data/splits/     — manifest outputs (can be committed to git)
    _repo_root = Path(__file__).resolve().parents[4]
    _synthetic_dir = _repo_root / "data" / "synthetic"
    _output_path = _repo_root / "data" / "splits" / "integrity_manifest.json"

    write_integrity_manifest(_synthetic_dir, _output_path)
