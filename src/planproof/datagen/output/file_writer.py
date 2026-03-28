"""File writer — orchestrates writing a complete application set to disk.

This module is the outermost I/O layer of the data-generation pipeline.  Given
a Scenario, its rendered documents (pre-degradation), and its degraded documents
(post-degradation), it:

  1. Creates the output directory.
  2. Writes each document file with the BCC naming convention:
         {docID}-{category}-{type}.{ext}
     where docID is the scenario's set_id.
  3. For PDF documents, also rasterises and writes a ``_scan.png`` degraded
     version using the degraded bytes.
  4. Writes reference files (parcel.geojson, zone.json) via reference_writer.
  5. Writes ground_truth.json via sidecar_writer.

# DESIGN: write_application_set is intentionally the only public function.
# All sub-steps (naming, PNG conversion, reference writing) are private helpers
# that can be tested independently if needed.  This keeps the public API minimal
# and the integration path easy to trace.
#
# WHY a dedicated file_writer module rather than embedding I/O in the runner:
# the runner is responsible for orchestrating scenario generation; the writer is
# responsible for the corpus file layout.  Keeping them separate means the runner
# can be tested with a mock writer, and the writer can be tested with a mock
# scenario without needing the full pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from planproof.datagen.output.reference_writer import write_reference_files
from planproof.datagen.output.sidecar_writer import write_ground_truth
from planproof.datagen.rendering.models import GeneratedDocument
from planproof.datagen.scenario.models import Scenario

# ---------------------------------------------------------------------------
# BCC filename construction
# ---------------------------------------------------------------------------


def _bcc_filename(set_id: str, category: str, doc_type: str, ext: str) -> str:
    """Construct a BCC-compliant filename.

    BCC pattern: ``{docID}-{category}-{type}.{ext}``

    Examples:
        _bcc_filename("SET_COMPLIANT_42", "compliant", "FORM", "pdf")
        → "SET_COMPLIANT_42-compliant-FORM.pdf"

    # WHY: Centralising filename construction in one function prevents typos
    # and inconsistent separators across different call sites.  Every output
    # file that goes through this function is guaranteed to conform to the BCC
    # naming pattern that the evaluation harness parses.

    Args:
        set_id:   The scenario set_id (e.g. "SET_COMPLIANT_42").
        category: Lowercase category string (e.g. "compliant").
        doc_type: Uppercase document type string (e.g. "FORM").
        ext:      File extension without leading dot (e.g. "pdf").

    Returns:
        The BCC-compliant filename string.
    """
    # WHY: doc_type is uppercased defensively so that StrEnum values such as
    # DocumentType.FORM (which str-ifies as "FORM") and plain strings (which
    # might arrive as "form") both produce the same canonical filename.
    return f"{set_id}-{category.lower()}-{doc_type.upper()}.{ext}"


def _scan_png_filename(pdf_filename: str) -> str:
    """Derive the _scan.png filename from a PDF filename.

    The scan filename is the PDF stem with ``_scan`` appended, then ``.png``.

    Example:
        "...-FORM.pdf" → "...-FORM_scan.png"

    # WHY: Keeping the scan filename clearly related to its source PDF makes
    # it easy for evaluation tools to discover the scan without a manifest.
    # The _scan suffix distinguishes degraded raster scans from clean renders.
    """
    stem = pdf_filename.rsplit(".", 1)[0]
    return f"{stem}_scan.png"


# ---------------------------------------------------------------------------
# PNG conversion (rasterise + encode)
# ---------------------------------------------------------------------------


def _pdf_to_scan_png(pdf_bytes: bytes) -> bytes:
    """Rasterise the first page of a PDF and return it as PNG bytes.

    # DESIGN: We rasterise only the first page for the scan PNG.  Planning
    # documents rarely span more than one page, and multi-page PDFs produce
    # multiple scan images whose index-based naming quickly becomes complex.
    # A single representative page is sufficient for OCR/VLM evaluation.
    #
    # WHY PNG: PNG is lossless, so the scan retains the full quality of the
    # rasterised image.  The degradation pipeline has already applied JPEG-like
    # compression if the preset calls for it; writing as PNG avoids re-compressing.

    Args:
        pdf_bytes: Raw PDF bytes (content_bytes from a GeneratedDocument).

    Returns:
        PNG-encoded bytes of the first rasterised page.
    """
    from io import BytesIO

    import numpy as np
    from PIL import Image

    from planproof.datagen.degradation.rasterise import rasterise_pdf

    # WHY 150 DPI for the scan: 300 DPI is canonical for measurement-grade
    # documents, but the scan PNG is used for visual OCR/VLM evaluation where
    # 150 DPI is sufficient and halves the file size.
    pages = rasterise_pdf(pdf_bytes, dpi=150)
    first_page: np.ndarray = pages[0]

    pil_image = Image.fromarray(first_page, mode="RGB")
    buf = BytesIO()
    pil_image.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_application_set(
    scenario: Scenario,
    generated_docs: list[GeneratedDocument],
    degraded_docs: list[GeneratedDocument],
    output_dir: Path,
) -> None:
    """Write a complete application set to disk.

    Creates the output directory and all required sub-directories, then writes:
      - One document file per GeneratedDocument (BCC-named, from degraded_docs bytes)
      - One ``_scan.png`` per PDF document (rasterised from degraded bytes)
      - ``reference/parcel.geojson`` and ``reference/zone.json``
      - ``ground_truth.json`` with full extraction and verdict records

    Args:
        scenario:       The Scenario whose documents are being written.
        generated_docs: Original (pre-degradation) GeneratedDocument list.
                        PlacedValues from these are used in ground_truth.json
                        as the canonical extractions.
        degraded_docs:  Post-degradation GeneratedDocument list whose
                        content_bytes are written to disk.  Positional
                        correspondence with generated_docs is assumed.
        output_dir:     Destination directory for this application set.
                        Created (with parents) if it does not exist.

    # WHY: Accepting both generated_docs and degraded_docs separately lets the
    # caller supply pre-degradation PlacedValues (canonical bboxes) for the
    # sidecar while writing the visually degraded bytes as the actual files.
    # This mirrors how an OCR pipeline would see the files: the bytes contain
    # degradation but the ground truth records the original clean bboxes.
    """
    # Step 1: create output directory.
    # WHY exist_ok=True: the runner may call write_application_set in a retry
    # scenario or after a partial run; we should not fail if the directory
    # already exists.
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: write document files.
    # WHY degraded_docs for content_bytes: these are the files that will be
    # presented to the extraction pipeline.  The degradation has already been
    # applied by the caller.
    for idx, (orig_doc, deg_doc, doc_spec) in enumerate(
        zip(generated_docs, degraded_docs, scenario.documents)
    ):
        # WHY: Use subtype (e.g. "site_plan") for distinct filenames.
        # Without this, multiple DRAWING docs would overwrite each other.
        label = doc_spec.subtype or str(deg_doc.doc_type)
        # Add index suffix if multiple docs share the same label.
        doc_label = f"{label}_{idx}" if idx > 0 else label
        filename = _bcc_filename(
            set_id=scenario.set_id,
            category=scenario.category,
            doc_type=doc_label.upper(),
            ext=deg_doc.file_format,
        )
        file_path = output_dir / filename
        file_path.write_bytes(deg_doc.content_bytes)

        # Step 3: for PDF documents, write the scan PNG.
        # WHY: Two formats enable two evaluation paths — text-layer extraction
        # (from the PDF) and OCR/VLM extraction (from the PNG scan).
        if deg_doc.file_format.lower() == "pdf":
            scan_png_bytes = _pdf_to_scan_png(deg_doc.content_bytes)
            scan_filename = _scan_png_filename(filename)
            scan_path = output_dir / scan_filename
            scan_path.write_bytes(scan_png_bytes)

    # Step 4: write reference files.
    write_reference_files(scenario, output_dir)

    # Step 5: write ground truth sidecar.
    # WHY: We pass generated_docs (not degraded_docs) so the sidecar records
    # the clean pre-degradation bboxes as the canonical ground truth.
    # Downstream tools can then measure how much degradation displaced the
    # extracted bboxes relative to these clean positions.
    degradation_params: dict[str, Any] = {
        "preset": scenario.degradation_preset,
        "seed": scenario.seed,
    }
    write_ground_truth(scenario, generated_docs, degradation_params, output_dir)
