"""Tests for the MD5 integrity manifest utilities.

# WHY: The integrity manifest is the tamper-evidence layer for the dataset.
# If any file is accidentally re-generated or corrupted between pipeline runs,
# verify_dataset.py must catch it.  These tests verify the hash logic against
# known-good inputs so we can trust the manifest is authoritative.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from planproof.datagen.integrity import compute_file_hashes

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeFileHashes:
    """Hash function returns correct MD5 digests for known content."""

    def test_known_file_matches_expected_hash(self, tmp_path: Path) -> None:
        # WHY: We derive the expected hash independently using hashlib so the
        # test does not depend on any implementation detail of our function —
        # only on the MD5 specification itself.
        content = b"Hello, PlanProof!\n"
        f = tmp_path / "test.txt"
        f.write_bytes(content)

        expected = hashlib.md5(content).hexdigest()
        hashes = compute_file_hashes(tmp_path)

        assert "test.txt" in hashes
        assert hashes["test.txt"] == expected

    def test_nested_files_use_relative_paths(self, tmp_path: Path) -> None:
        # WHY: Manifest keys must be relative to synthetic_dir so the manifest
        # is portable — absolute paths would break on any other machine.
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "a.json").write_bytes(b"{}")

        hashes = compute_file_hashes(tmp_path)
        keys = list(hashes.keys())
        # All keys must be relative (no drive letter, no leading separator)
        assert all(not Path(k).is_absolute() for k in keys)
        assert any("subdir" in k for k in keys)

    def test_path_separators_are_forward_slashes(self, tmp_path: Path) -> None:
        # WHY: On Windows, Path() uses backslashes.  The manifest must use
        # forward slashes so it is platform-independent and can be read on
        # Linux/macOS without modification.
        sub = tmp_path / "folder"
        sub.mkdir()
        (sub / "file.txt").write_bytes(b"data")

        hashes = compute_file_hashes(tmp_path)
        for key in hashes:
            assert "\\" not in key, f"backslash found in key: {key!r}"

    def test_hash_changes_with_content(self, tmp_path: Path) -> None:
        # WHY: If the hash function is broken (e.g. always returns a constant),
        # the integrity check would accept corrupted files.
        f = tmp_path / "file.txt"
        f.write_bytes(b"original")
        hash_v1 = compute_file_hashes(tmp_path)["file.txt"]

        f.write_bytes(b"tampered")
        hash_v2 = compute_file_hashes(tmp_path)["file.txt"]

        assert hash_v1 != hash_v2

    def test_multiple_files_all_hashed(self, tmp_path: Path) -> None:
        # WHY: Ensure the function walks the entire tree, not just the top level.
        (tmp_path / "a.txt").write_bytes(b"a")
        (tmp_path / "b.txt").write_bytes(b"b")
        sub = tmp_path / "nested"
        sub.mkdir()
        (sub / "c.txt").write_bytes(b"c")

        hashes = compute_file_hashes(tmp_path)
        assert len(hashes) == 3

    def test_deterministic_across_calls(self, tmp_path: Path) -> None:
        # WHY: MD5 is deterministic; two calls on the same unchanged tree must
        # return identical results (no timestamps or random salts involved).
        (tmp_path / "x.json").write_bytes(b'{"key": "value"}')
        assert compute_file_hashes(tmp_path) == compute_file_hashes(tmp_path)

    def test_json_content_correctly_hashed(self, tmp_path: Path) -> None:
        # WHY: JSON files are the most critical artefact (ground_truth.json).
        # Verify we hash raw bytes, not a parsed/re-serialised version which
        # could silently normalise whitespace or key order.
        payload = b'{"verdict": "COMPLIANT", "score": 0.95}\n'
        (tmp_path / "ground_truth.json").write_bytes(payload)
        expected = hashlib.md5(payload).hexdigest()
        hashes = compute_file_hashes(tmp_path)
        assert hashes["ground_truth.json"] == expected


class TestEmptyDirReturnsEmpty:
    """compute_file_hashes returns {} for a directory with no files."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        # WHY: An empty directory is a valid state (data not yet generated).
        # The function must not crash; it must silently return an empty dict
        # so callers can distinguish "no data" from "corrupted data".
        result = compute_file_hashes(tmp_path)
        assert result == {}

    def test_directory_with_only_subdirs(self, tmp_path: Path) -> None:
        # WHY: Subdirectories are not files; they must be skipped without
        # raising an error.
        (tmp_path / "empty_sub").mkdir()
        result = compute_file_hashes(tmp_path)
        assert result == {}

    def test_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        # WHY: Silently returning an empty dict for a missing directory could
        # mask a misconfigured path.  A clear FileNotFoundError is preferable.
        import pytest

        with pytest.raises(FileNotFoundError):
            compute_file_hashes(tmp_path / "does_not_exist")
