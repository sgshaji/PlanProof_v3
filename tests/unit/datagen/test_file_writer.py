"""Tests for file_writer — directory creation, BCC naming, and PDF+scan output.

# WHY: The file writer is the final integration point between the in-memory
# pipeline and the on-disk corpus.  Errors here (wrong naming, missing files)
# would corrupt the dataset silently.  Tests are deliberately I/O-focused
# because the writer's job is exactly file system interaction.
"""

from __future__ import annotations

import re
from pathlib import Path

from planproof.datagen.output.file_writer import write_application_set
from planproof.datagen.rendering.models import GeneratedDocument, PlacedValue
from planproof.datagen.scenario.models import DocumentSpec, Scenario, Value, Verdict
from planproof.schemas.entities import BoundingBox, DocumentType, EntityType

# ---------------------------------------------------------------------------
# BCC naming pattern: {docID}-{category}-{type}.{ext}
# docID format used: SET_<CATEGORY>_<SEED> → e.g. SET_COMPLIANT_42
# ---------------------------------------------------------------------------

BCC_PATTERN = re.compile(
    r"^[A-Z0-9_]+-[a-z_]+-[A-Z_]+\.(pdf|png|tiff)$"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_pdf_bytes() -> bytes:
    """Return valid-enough PDF bytes for the rasterisation fallback to handle."""
    # WHY: We need bytes that look like a PDF so rasterise_pdf() does not raise.
    # The fallback back-end only reads the MediaBox, so a bare-minimum header
    # with a MediaBox and a /Type /Page token is sufficient for tests.
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
        b"2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n"
        b"3 0 obj\n<</Type /Page /MediaBox [0 0 595 842]>>\nendobj\n"
        b"%%EOF"
    )


def _make_scenario() -> Scenario:
    return Scenario(
        set_id="SET_COMPLIANT_42",
        category="compliant",
        seed=42,
        profile_id="standard",
        difficulty="low",
        degradation_preset="clean",
        values=(
            Value(
                attribute="front_setback",
                value=7.5,
                unit="metres",
                display_text="7.5m",
            ),
        ),
        verdicts=(
            Verdict(
                rule_id="R001",
                outcome="PASS",
                evaluated_value=7.5,
                threshold=8.0,
            ),
        ),
        documents=(
            DocumentSpec(
                doc_type="FORM",
                file_format="pdf",
                values_to_place=("front_setback",),
            ),
        ),
        edge_case_strategy=None,
    )


def _make_generated_docs() -> list[GeneratedDocument]:
    """One PDF document with a PlacedValue."""
    placed = PlacedValue(
        attribute="front_setback",
        value=7.5,
        text_rendered="7.5m",
        page=1,
        bounding_box=BoundingBox(x=100.0, y=200.0, width=80.0, height=20.0, page=1),
        entity_type=EntityType.MEASUREMENT,
    )
    return [
        GeneratedDocument(
            filename="SET_COMPLIANT_42-compliant-FORM.pdf",
            doc_type=DocumentType.FORM,
            content_bytes=_minimal_pdf_bytes(),
            file_format="pdf",
            placed_values=(placed,),
        )
    ]


def _make_degraded_docs() -> list[GeneratedDocument]:
    """Same doc but treated as the degraded version (content unchanged for test)."""
    # WHY: In the real pipeline the degraded version has degradation applied;
    # for the file writer tests we only care about what files are written, not
    # the visual content of those files.
    return _make_generated_docs()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteApplicationSet:
    """Tests for write_application_set()."""

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        """The output directory and reference/ sub-directory must be created.

        # WHY: Downstream ingestion tools expect a well-defined directory
        # structure.  Missing sub-directories cause FileNotFoundError at read
        # time, which is confusing because the set appears to exist.
        """
        scenario = _make_scenario()
        generated = _make_generated_docs()
        degraded = _make_degraded_docs()

        write_application_set(scenario, generated, degraded, tmp_path)

        # reference/ sub-directory must exist
        assert (tmp_path / "reference").is_dir(), "'reference' sub-directory missing"

        # ground_truth.json must exist
        assert (tmp_path / "ground_truth.json").is_file(), (
            "ground_truth.json missing from output directory"
        )

    def test_bcc_naming_convention(self, tmp_path: Path) -> None:
        """Every document file must match the BCC naming pattern.

        BCC pattern: {docID}-{category}-{type}.{ext}
        Example: SET_COMPLIANT_42-compliant-FORM.pdf

        # WHY: The evaluation harness identifies document types by parsing
        # the filename.  A file that deviates from the naming pattern will be
        # classified as DocumentType.OTHER and excluded from rule evaluation.
        """
        scenario = _make_scenario()
        generated = _make_generated_docs()
        degraded = _make_degraded_docs()

        write_application_set(scenario, generated, degraded, tmp_path)

        # Collect primary document files (PDF, non-scan PNG, TIFF) in output root.
        # WHY: Scan PNGs (_scan.png) are a secondary output with a defined naming
        # suffix and are excluded from the BCC pattern check — their stem is the
        # same as the source PDF's BCC name, making them implicitly compliant.
        doc_files = [
            f
            for f in tmp_path.iterdir()
            if f.is_file()
            and f.suffix in {".pdf", ".png", ".tiff"}
            and not f.name.endswith("_scan.png")
        ]
        assert len(doc_files) > 0, "No document files were written"

        for f in doc_files:
            assert BCC_PATTERN.match(f.name), (
                f"File '{f.name}' does not match BCC naming pattern "
                f"{BCC_PATTERN.pattern!r}"
            )

    def test_writes_pdf_and_scan_png(self, tmp_path: Path) -> None:
        """For each PDF document, both a text-layer PDF and a _scan.png must be written.

        # WHY: The evaluation pipeline has two paths — a text-extraction path
        # (reads the PDF directly) and an OCR/VLM path (reads the scan PNG).
        # Writing only the PDF would silently disable all OCR-based evaluations.
        """
        scenario = _make_scenario()
        generated = _make_generated_docs()
        degraded = _make_degraded_docs()

        write_application_set(scenario, generated, degraded, tmp_path)

        pdf_files = list(tmp_path.glob("*.pdf"))
        png_files = list(tmp_path.glob("*_scan.png"))

        assert len(pdf_files) > 0, "No PDF files written"
        assert len(png_files) > 0, "No _scan.png files written"

        # For each PDF there should be a matching _scan.png
        # (stem before .pdf → stem + "_scan.png")
        for pdf in pdf_files:
            expected_scan = tmp_path / f"{pdf.stem}_scan.png"
            assert expected_scan.exists(), (
                f"Missing scan PNG for '{pdf.name}': expected '{expected_scan.name}'"
            )

    def test_reference_files_written(self, tmp_path: Path) -> None:
        """reference/parcel.geojson and reference/zone.json must be present.

        # WHY: Reference files are required inputs to the rule engine.  Missing
        # them causes a FileNotFoundError at evaluation time — well after the
        # corpus is committed and the generator has moved on.
        """
        scenario = _make_scenario()
        generated = _make_generated_docs()
        degraded = _make_degraded_docs()

        write_application_set(scenario, generated, degraded, tmp_path)

        assert (tmp_path / "reference" / "parcel.geojson").is_file(), (
            "reference/parcel.geojson missing"
        )
        assert (tmp_path / "reference" / "zone.json").is_file(), (
            "reference/zone.json missing"
        )
