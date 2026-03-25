"""
anonymise_bcc_data.py — Phase 1.1: PII Anonymisation of Real BCC Planning Data

WHY: Real BCC planning application PDFs contain personal information (applicant names,
     addresses, phone numbers, email addresses, agent details) on the form pages.
     Before any file can be used in shared or published contexts, PII must be identified,
     documented, and segregated.  This script implements a manifest-based approach because
     pymupdf (which would allow programmatic PDF redaction) is not available on ARM64 Windows.

DESIGN: Three-phase approach:
    1. CLASSIFY — scan data/raw/ and label every file as FORM, DRAWING, or OTHER.
       Classification is driven by filename tokens that BCC uses in its own portal exports
       (e.g., "Forms-Planning Application Form" vs. "Plans & Drawings").
    2. MANIFEST — write data/raw/pii_manifest.json recording the PII status, file type,
       known PII field categories, and disposition for every file.
    3. COPY — copy files classified as SAFE (drawings / images / supporting info that is not
       a form) to data/anonymised/, preserving the application-folder structure.
       Form files are NOT copied; they need manual redaction before sharing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# WHY: Anchor paths relative to the project root, not the CWD of the caller,
#      so the script is safe to invoke from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ANONYMISED_DIR = PROJECT_ROOT / "data" / "anonymised"
MANIFEST_PATH = RAW_DIR / "pii_manifest.json"

# WHY: These tokens appear verbatim in BCC portal export filenames.
#      Matching on substrings is intentionally case-insensitive to be resilient
#      to any portal capitalisation changes.
FORM_FILENAME_TOKENS: tuple[str, ...] = (
    "forms-planning application form",
    "householder planning app",  # some BCC exports omit the standard token
    "correspondence-private supporting information",  # may contain personal letters
)

DRAWING_FILENAME_TOKENS: tuple[str, ...] = (
    "plans & drawings",
    "plans and drawings",
    "application plans",
    "elevations",
    "floor plan",
    "location and block plan",
    "site plan",
    "block plan",
    "correspondence-supporting information",  # non-private supporting docs (e.g., photos)
)

# WHY: These are the known PII field categories on BCC householder planning forms (pages 1-2).
#      Documenting them explicitly satisfies a dissertation audit-trail requirement and helps
#      a human reviewer know what to look for when manually redacting.
FORM_PII_FIELDS: list[str] = [
    "applicant_full_name",
    "applicant_address",
    "applicant_phone",
    "applicant_email",
    "agent_full_name",
    "agent_company",
    "agent_address",
    "agent_phone",
    "agent_email",
    "site_address",          # also in drawings title block but most specifically in form
    "certificate_signatory", # planning certificate signed by applicant or agent
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class FileClass(StrEnum):
    """
    DESIGN: Three mutually exclusive classes covering all BCC portal export files.
    FORM     — application form pages, always contains PII.
    DRAWING  — architectural plans, site plans, elevations; no PII expected.
    OTHER    — anything that did not match a known token; treat conservatively as PII.
    """

    FORM = "FORM"
    DRAWING = "DRAWING"
    OTHER = "OTHER"


class PIIStatus(StrEnum):
    CONTAINS_PII = "contains_pii"
    SAFE = "safe"
    UNKNOWN = "unknown"  # conservative fallback for OTHER files


@dataclass
class FileRecord:
    """Manifest record for a single file."""

    application_id: str          # e.g. "2025 00532"
    application_status: str      # e.g. "PA Held"
    filename: str
    relative_path: str           # relative to RAW_DIR, using forward slashes
    file_class: FileClass
    pii_status: PIIStatus
    pii_fields: list[str]        # non-empty only for FORM files
    disposition: str             # "copied_to_anonymised" | "manual_redaction_required" | "review_required"
    sha256: str = field(default="")
    size_bytes: int = field(default=0)


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------


def classify_file(path: Path) -> FileClass:
    """
    Determine whether a file is a planning form, a drawing, or unclassified.

    WHY: Classification is purely name-based because we cannot parse PDF content
         without pymupdf.  BCC uses consistent naming conventions in its portal
         exports so this is reliable in practice.
    """
    # DESIGN: Compare against lowercased filename including the parent folder segment
    #         (the folder name encodes the application ID and status, not the file type).
    lower_name = path.name.lower()

    for token in FORM_FILENAME_TOKENS:
        if token in lower_name:
            return FileClass.FORM

    for token in DRAWING_FILENAME_TOKENS:
        if token in lower_name:
            return FileClass.DRAWING

    # Image files that aren't matched above are likely drawing exports — mark as drawing.
    if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        return FileClass.DRAWING

    return FileClass.OTHER


def pii_status_for(file_class: FileClass) -> PIIStatus:
    """Map file class to a PII status value."""
    # DESIGN: Explicit mapping keeps the relationship visible rather than implicitly
    #         coupling FileClass ordinal positions.
    return {
        FileClass.FORM: PIIStatus.CONTAINS_PII,
        FileClass.DRAWING: PIIStatus.SAFE,
        FileClass.OTHER: PIIStatus.UNKNOWN,
    }[file_class]


def disposition_for(pii_status: PIIStatus) -> str:
    return {
        PIIStatus.CONTAINS_PII: "manual_redaction_required",
        PIIStatus.SAFE: "copied_to_anonymised",
        PIIStatus.UNKNOWN: "review_required",
    }[pii_status]


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    """Compute SHA-256 hex digest in streaming 64 KB chunks to limit memory use."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_application_folder(folder_name: str) -> tuple[str, str]:
    """
    Split a BCC folder name like "2025 00532 PA Held" into (app_id, status).

    WHY: BCC portal exports use a consistent three-part name: year, ref number, status.
         Parsing it once here keeps all records self-describing.
    """
    # DESIGN: The status segment is everything after the 12-character "YYYY NNNNN" prefix.
    #         We split on spaces with maxsplit=2 and rejoin the remainder.
    parts = folder_name.split(" ", 2)
    if len(parts) == 3:
        app_id = f"{parts[0]} {parts[1]}"
        status = parts[2]
    else:
        # Fallback: treat entire folder name as app_id, status unknown.
        app_id = folder_name
        status = "unknown"
    return app_id, status


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def build_manifest(raw_dir: Path) -> list[FileRecord]:
    """
    Walk raw_dir and produce a FileRecord for every file found.

    WHY: Building the full manifest before doing any file I/O allows the copy
         phase to be driven purely from the manifest, making a dry-run mode trivial
         to add later.
    """
    records: list[FileRecord] = []

    for app_folder in sorted(raw_dir.iterdir()):
        if not app_folder.is_dir():
            # Skip top-level files (e.g., PROVENANCE.md, pii_manifest.json itself).
            continue

        app_id, app_status = parse_application_folder(app_folder.name)

        for file_path in sorted(app_folder.iterdir()):
            if not file_path.is_file():
                continue

            file_class = classify_file(file_path)
            pii = pii_status_for(file_class)
            disp = disposition_for(pii)

            record = FileRecord(
                application_id=app_id,
                application_status=app_status,
                filename=file_path.name,
                relative_path=str(file_path.relative_to(raw_dir)).replace("\\", "/"),
                file_class=file_class,
                pii_status=pii,
                pii_fields=FORM_PII_FIELDS if file_class == FileClass.FORM else [],
                disposition=disp,
                sha256=sha256_of(file_path),
                size_bytes=file_path.stat().st_size,
            )
            records.append(record)

    return records


def write_manifest(records: list[FileRecord], manifest_path: Path) -> None:
    """
    Serialise the manifest to JSON.

    DESIGN: We include a top-level summary block so a human can understand the
            dataset at a glance without parsing individual records.
    """
    summary = {
        "total_files": len(records),
        "forms_with_pii": sum(1 for r in records if r.pii_status == PIIStatus.CONTAINS_PII),
        "safe_drawings": sum(1 for r in records if r.pii_status == PIIStatus.SAFE),
        "unknown_review_required": sum(1 for r in records if r.pii_status == PIIStatus.UNKNOWN),
        "applications": len({r.application_id for r in records}),
    }

    payload = {
        "schema_version": "1.0",
        "generated_by": "scripts/anonymise_bcc_data.py",
        "generated_date": "2026-03-26",
        "description": (
            "Per-file PII classification for BCC real planning data. "
            "Files marked 'manual_redaction_required' must NOT be shared before redaction."
        ),
        "summary": summary,
        "files": [asdict(r) for r in records],
    }

    # WHY: indent=2 keeps the file human-readable in a text editor and in git diffs.
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def copy_safe_files(records: list[FileRecord], raw_dir: Path, dest_dir: Path) -> int:
    """
    Copy files with disposition 'copied_to_anonymised' to dest_dir, preserving structure.

    Returns the count of files copied.
    """
    copied = 0
    for record in records:
        if record.disposition != "copied_to_anonymised":
            continue

        src = raw_dir / record.relative_path
        dst = dest_dir / record.relative_path

        # WHY: Create the full parent path so we mirror the application folder structure.
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    return copied


def print_summary(records: list[FileRecord], copied: int) -> None:
    """Print a human-readable summary to stdout."""
    total = len(records)
    pii_count = sum(1 for r in records if r.pii_status == PIIStatus.CONTAINS_PII)
    safe_count = sum(1 for r in records if r.pii_status == PIIStatus.SAFE)
    unknown_count = sum(1 for r in records if r.pii_status == PIIStatus.UNKNOWN)

    print("\n=== BCC Data PII Anonymisation Summary ===")
    print(f"  Total files scanned   : {total}")
    print(f"  Forms (contain PII)   : {pii_count}  -> manual redaction required before sharing")
    print(f"  Drawings (safe)       : {safe_count}  -> copied to data/anonymised/")
    print(f"  Unknown / other       : {unknown_count}  -> manual review required")
    print(f"  Files copied          : {copied}")
    print(f"  Manifest written to   : {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    print()

    # Per-application breakdown
    apps: dict[str, dict[str, int]] = {}
    for r in records:
        entry = apps.setdefault(r.application_id, {"total": 0, "pii": 0, "safe": 0})
        entry["total"] += 1
        if r.pii_status == PIIStatus.CONTAINS_PII:
            entry["pii"] += 1
        elif r.pii_status == PIIStatus.SAFE:
            entry["safe"] += 1

    print("  Per-application breakdown:")
    for app_id in sorted(apps):
        e = apps[app_id]
        print(f"    {app_id}: {e['total']} files  ({e['pii']} form/PII, {e['safe']} safe)")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """
    Orchestrate the three phases: classify -> manifest -> copy.

    DESIGN: Returns an integer exit code so the function is testable without
            actually calling sys.exit() inside it.
    """
    if not RAW_DIR.exists():
        print(f"ERROR: raw data directory not found: {RAW_DIR}", file=sys.stderr)
        return 1

    ANONYMISED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Scanning {RAW_DIR} ...")
    records = build_manifest(RAW_DIR)

    if not records:
        print("WARNING: no files found in raw directory.", file=sys.stderr)
        return 1

    print(f"Writing manifest to {MANIFEST_PATH} ...")
    write_manifest(records, MANIFEST_PATH)

    print(f"Copying safe files to {ANONYMISED_DIR} ...")
    copied = copy_safe_files(records, RAW_DIR, ANONYMISED_DIR)

    print_summary(records, copied)
    return 0


if __name__ == "__main__":
    sys.exit(main())
