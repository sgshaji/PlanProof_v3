"""
test_anonymise.py — Unit tests for scripts/anonymise_bcc_data.py

WHY: The anonymisation script is the PII gatekeeper for the dataset.
     Even small bugs in classification logic could silently mark a form as
     "safe" and allow personal data to be copied into the anonymised folder.
     These tests verify classification behaviour and manifest structure
     without touching the filesystem (except for a tmp-dir fixture).

DESIGN: Tests are grouped into three concerns:
    1. Classification logic — pure function, no I/O.
    2. Manifest structure — valid JSON, required keys, correct summary counts.
    3. Copy behaviour — only safe files end up in the destination directory.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: import the script as a module without executing main()
# ---------------------------------------------------------------------------

# WHY: The script lives in scripts/ (not a package), so we use importlib to
#      load it by path.  This avoids adding scripts/ to sys.path globally and
#      keeps the test suite isolated.
_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "anonymise_bcc_data.py"

import sys

spec = importlib.util.spec_from_file_location("anonymise_bcc_data", _SCRIPT_PATH)
assert spec is not None and spec.loader is not None, f"Cannot load script from {_SCRIPT_PATH}"
_mod = importlib.util.module_from_spec(spec)
# WHY: Register the module in sys.modules before exec_module so that @dataclass
#      can resolve the module's namespace via sys.modules[cls.__module__].
#      Without this, Python 3.13's dataclass machinery finds None and raises
#      AttributeError: 'NoneType' object has no attribute '__dict__'.
sys.modules["anonymise_bcc_data"] = _mod
spec.loader.exec_module(_mod)  # type: ignore[attr-defined]

classify_file = _mod.classify_file
FileClass = _mod.FileClass
PIIStatus = _mod.PIIStatus
pii_status_for = _mod.pii_status_for
disposition_for = _mod.disposition_for
parse_application_folder = _mod.parse_application_folder
build_manifest = _mod.build_manifest
write_manifest = _mod.write_manifest
copy_safe_files = _mod.copy_safe_files
FORM_PII_FIELDS = _mod.FORM_PII_FIELDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def synthetic_raw_dir(tmp_path: Path) -> Path:
    """
    Build a minimal synthetic raw-data directory that mirrors the BCC structure.

    WHY: Using real data files in unit tests would (a) make tests slow due to
         SHA-256 computation on large PDFs, (b) tie tests to the presence of data
         files that may not exist in CI, and (c) risk accidentally leaking PII
         paths in test output.  A synthetic dir with zero-byte stub files is
         sufficient to test classification and copy logic.
    """
    raw = tmp_path / "raw"

    # Application 1: form + drawing (PDF)
    app1 = raw / "2025 00532 PA Held"
    app1.mkdir(parents=True)
    (app1 / "6125163-Forms-Planning Application Form.pdf").write_bytes(b"")
    (app1 / "6125167-Plans & Drawings-Application Plans.pdf").write_bytes(b"")
    (app1 / "6125169-Plans & Drawings-Application Plans.jpg").write_bytes(b"")

    # Application 2: form + drawings with varied types
    app2 = raw / "2025 00841 PA Held"
    app2.mkdir(parents=True)
    (app2 / "6132015-Householder Planning App_136 Rectory Rd.pdf").write_bytes(b"")
    (app2 / "6132017-2100-200-A-Existing Elevations.pdf").write_bytes(b"")
    (app2 / "6132021-2100-10-C-Location and Block Plan.pdf").write_bytes(b"")

    return raw


# ---------------------------------------------------------------------------
# 1. Classification logic
# ---------------------------------------------------------------------------


class TestClassifyFile:
    """Pure classification logic — no filesystem I/O needed beyond Path construction."""

    def test_standard_form_filename_is_classified_as_form(self) -> None:
        p = Path("6125163-Forms-Planning Application Form.pdf")
        assert classify_file(p) == FileClass.FORM

    def test_householder_app_filename_is_classified_as_form(self) -> None:
        # WHY: Some BCC exports omit the standard "Forms-" prefix token.
        p = Path("6132015-Householder Planning App_136 Rectory Rd.pdf")
        assert classify_file(p) == FileClass.FORM

    def test_private_correspondence_is_classified_as_form(self) -> None:
        # WHY: Private supporting information may contain personal letters.
        p = Path("6130708-Correspondence-Private Supporting Information.pdf")
        assert classify_file(p) == FileClass.FORM

    def test_drawings_pdf_is_classified_as_drawing(self) -> None:
        p = Path("6125167-Plans & Drawings-Application Plans.pdf")
        assert classify_file(p) == FileClass.DRAWING

    def test_elevations_pdf_is_classified_as_drawing(self) -> None:
        p = Path("6132017-2100-200-A-Existing Elevations.pdf")
        assert classify_file(p) == FileClass.DRAWING

    def test_block_plan_pdf_is_classified_as_drawing(self) -> None:
        p = Path("6132021-2100-10-C-Location and Block Plan.pdf")
        assert classify_file(p) == FileClass.DRAWING

    def test_jpg_image_is_classified_as_drawing(self) -> None:
        # WHY: Image exports are always drawings; no PII expected in raster exports.
        p = Path("6125169-Plans & Drawings-Application Plans.jpg")
        assert classify_file(p) == FileClass.DRAWING

    def test_png_image_is_classified_as_drawing(self) -> None:
        p = Path("6132920-Plans & Drawings-Application Plans.png")
        assert classify_file(p) == FileClass.DRAWING

    def test_unknown_file_returns_other(self) -> None:
        p = Path("some_mystery_document.pdf")
        assert classify_file(p) == FileClass.OTHER

    def test_classification_is_case_insensitive(self) -> None:
        # WHY: Guard against BCC changing capitalisation in future portal exports.
        p = Path("6125163-forms-PLANNING APPLICATION FORM.pdf")
        assert classify_file(p) == FileClass.FORM


# ---------------------------------------------------------------------------
# 2. PII status and disposition mapping
# ---------------------------------------------------------------------------


class TestPIIStatusMapping:
    def test_form_maps_to_contains_pii(self) -> None:
        assert pii_status_for(FileClass.FORM) == PIIStatus.CONTAINS_PII

    def test_drawing_maps_to_safe(self) -> None:
        assert pii_status_for(FileClass.DRAWING) == PIIStatus.SAFE

    def test_other_maps_to_unknown(self) -> None:
        assert pii_status_for(FileClass.OTHER) == PIIStatus.UNKNOWN

    def test_contains_pii_disposition_requires_redaction(self) -> None:
        assert disposition_for(PIIStatus.CONTAINS_PII) == "manual_redaction_required"

    def test_safe_disposition_is_copied(self) -> None:
        assert disposition_for(PIIStatus.SAFE) == "copied_to_anonymised"

    def test_unknown_disposition_requires_review(self) -> None:
        assert disposition_for(PIIStatus.UNKNOWN) == "review_required"


# ---------------------------------------------------------------------------
# 3. Application folder name parsing
# ---------------------------------------------------------------------------


class TestParseApplicationFolder:
    def test_standard_held_folder(self) -> None:
        app_id, status = parse_application_folder("2025 00532 PA Held")
        assert app_id == "2025 00532"
        assert status == "PA Held"

    def test_validated_folder(self) -> None:
        app_id, status = parse_application_folder("2026 00085 PA Validated")
        assert app_id == "2026 00085"
        assert status == "PA Validated"


# ---------------------------------------------------------------------------
# 4. Manifest structure (integration with synthetic filesystem)
# ---------------------------------------------------------------------------


class TestManifestStructure:
    def test_manifest_is_valid_json(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        """The manifest file must parse as valid JSON."""
        records = build_manifest(synthetic_raw_dir)
        manifest_path = tmp_path / "pii_manifest.json"
        write_manifest(records, manifest_path)

        raw_text = manifest_path.read_text(encoding="utf-8")
        parsed = json.loads(raw_text)  # raises if invalid JSON

        assert isinstance(parsed, dict)

    def test_manifest_has_required_top_level_keys(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        records = build_manifest(synthetic_raw_dir)
        manifest_path = tmp_path / "pii_manifest.json"
        write_manifest(records, manifest_path)

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("schema_version", "generated_by", "summary", "files"):
            assert key in data, f"Missing top-level key: {key}"

    def test_manifest_summary_counts_are_consistent(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        """Summary counts must equal what we can derive from the files list."""
        records = build_manifest(synthetic_raw_dir)
        manifest_path = tmp_path / "pii_manifest.json"
        write_manifest(records, manifest_path)

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = data["summary"]
        files = data["files"]

        assert summary["total_files"] == len(files)
        assert summary["forms_with_pii"] == sum(
            1 for f in files if f["pii_status"] == PIIStatus.CONTAINS_PII.value
        )
        assert summary["safe_drawings"] == sum(
            1 for f in files if f["pii_status"] == PIIStatus.SAFE.value
        )

    def test_form_files_have_pii_fields_populated(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        """Every file classified as FORM must list the known PII field categories."""
        records = build_manifest(synthetic_raw_dir)
        manifest_path = tmp_path / "pii_manifest.json"
        write_manifest(records, manifest_path)

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        form_records = [f for f in data["files"] if f["file_class"] == FileClass.FORM.value]

        assert len(form_records) > 0, "Expected at least one form in synthetic data"
        for fr in form_records:
            assert len(fr["pii_fields"]) > 0, f"Form record missing pii_fields: {fr['filename']}"
            assert "applicant_full_name" in fr["pii_fields"]

    def test_drawing_files_have_no_pii_fields(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        records = build_manifest(synthetic_raw_dir)
        manifest_path = tmp_path / "pii_manifest.json"
        write_manifest(records, manifest_path)

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        drawing_records = [f for f in data["files"] if f["file_class"] == FileClass.DRAWING.value]

        assert len(drawing_records) > 0, "Expected at least one drawing in synthetic data"
        for dr in drawing_records:
            assert dr["pii_fields"] == [], f"Drawing should have no PII fields: {dr['filename']}"

    def test_forms_have_manual_redaction_disposition(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        records = build_manifest(synthetic_raw_dir)
        form_records = [r for r in records if r.file_class == FileClass.FORM]
        assert all(r.disposition == "manual_redaction_required" for r in form_records)

    def test_drawings_have_copy_disposition(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        records = build_manifest(synthetic_raw_dir)
        drawing_records = [r for r in records if r.file_class == FileClass.DRAWING]
        assert all(r.disposition == "copied_to_anonymised" for r in drawing_records)


# ---------------------------------------------------------------------------
# 5. Copy behaviour
# ---------------------------------------------------------------------------


class TestCopyBehaviour:
    def test_only_safe_files_are_copied(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        """Files with PII must NOT appear in the anonymised directory."""
        dest = tmp_path / "anonymised"
        records = build_manifest(synthetic_raw_dir)
        copy_safe_files(records, synthetic_raw_dir, dest)

        copied_files = list(dest.rglob("*"))
        copied_names = {f.name for f in copied_files if f.is_file()}

        # Drawings should be present
        assert "6125167-Plans & Drawings-Application Plans.pdf" in copied_names
        assert "6125169-Plans & Drawings-Application Plans.jpg" in copied_names
        assert "6132017-2100-200-A-Existing Elevations.pdf" in copied_names

        # Forms must NOT be present
        assert "6125163-Forms-Planning Application Form.pdf" not in copied_names
        assert "6132015-Householder Planning App_136 Rectory Rd.pdf" not in copied_names

    def test_copy_preserves_application_subfolder_structure(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        """
        WHY: Preserving the folder structure makes it easy to pair anonymised drawings
             with their corresponding (non-shared) form by application ID.
        """
        dest = tmp_path / "anonymised"
        records = build_manifest(synthetic_raw_dir)
        copy_safe_files(records, synthetic_raw_dir, dest)

        expected_folder = dest / "2025 00532 PA Held"
        assert expected_folder.is_dir(), "Application subfolder not created in anonymised dir"

    def test_copy_count_equals_safe_file_count(self, synthetic_raw_dir: Path, tmp_path: Path) -> None:
        dest = tmp_path / "anonymised"
        records = build_manifest(synthetic_raw_dir)
        expected_safe = sum(1 for r in records if r.disposition == "copied_to_anonymised")
        copied = copy_safe_files(records, synthetic_raw_dir, dest)
        assert copied == expected_safe
