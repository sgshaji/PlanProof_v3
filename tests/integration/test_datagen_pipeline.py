"""Integration test: generate a complete application set and validate output.

# DESIGN: These tests exercise the full generation pipeline end-to-end:
#   runner.generate_sets → scenario building → document rendering →
#   degradation → file_writer → disk artefacts.
#
# WHY integration tests rather than purely unit tests here: the pipeline
# composes many layers (config loading, rendering, degradation, I/O), and
# the only way to verify they wire together correctly is to actually run them
# and inspect the produced files.  Each unit test layer verifies a single
# layer; these tests verify the seams between layers.
#
# WHY tmp_path fixture: pytest's tmp_path gives an isolated, OS-managed
# temporary directory that is cleaned up automatically.  This prevents
# integration tests from polluting the project's data/ directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Shared fixture — generate once, reuse across all TestDatagenPipeline tests
# ---------------------------------------------------------------------------


@pytest.fixture
def generated_set(tmp_path: Path) -> Path:
    """Generate a single compliant set to a temp directory.

    # WHY seed=42 and count=1: a fixed seed makes the fixture deterministic
    # so failures are reproducible; count=1 keeps the fixture fast (< 5 s)
    # while still exercising the full pipeline for one set.
    """
    from planproof.datagen.runner import generate_sets

    generate_sets(
        output_dir=tmp_path,
        category="compliant",
        count=1,
        seed=42,
    )
    # WHY: The runner always writes into <output_dir>/<category>/<set_id>/,
    # so we descend into the compliant sub-directory to find the set.
    compliant_dir = tmp_path / "compliant"
    sets = list(compliant_dir.iterdir())
    assert len(sets) == 1
    return sets[0]


# ---------------------------------------------------------------------------
# Pipeline correctness tests
# ---------------------------------------------------------------------------


class TestDatagenPipeline:
    """Verify that a generated application set has the expected file layout."""

    def test_output_directory_exists(self, generated_set: Path) -> None:
        # WHY: Basic sanity — if the directory doesn't exist, every other test
        # will fail with a less informative error.
        assert generated_set.is_dir()

    def test_ground_truth_valid_json(self, generated_set: Path) -> None:
        """ground_truth.json must exist and contain mandatory top-level keys."""
        gt_path = generated_set / "ground_truth.json"
        assert gt_path.exists()
        gt = json.loads(gt_path.read_text())
        assert "set_id" in gt
        assert gt["category"] == "compliant"
        assert "values" in gt
        assert "documents" in gt
        assert "rule_verdicts" in gt

    def test_form_pdf_exists(self, generated_set: Path) -> None:
        """At least one BCC-named FORM PDF must be present in the set directory."""
        # WHY: The FORM document is the primary structured-data carrier and is
        # required in every profile.  Its absence means the form generator or
        # file writer has failed silently.
        pdfs = [
            f
            for f in generated_set.iterdir()
            if f.name.endswith(".pdf") and "FORM" in f.name
        ]
        assert len(pdfs) >= 1

    def test_form_scan_png_exists(self, generated_set: Path) -> None:
        """A *_scan.png must be produced alongside every FORM PDF."""
        # WHY: The scan PNG is the rasterised, degraded view of the PDF.
        # Its presence verifies that _pdf_to_scan_png ran successfully.
        scans = [
            f
            for f in generated_set.iterdir()
            if "_scan.png" in f.name and "FORM" in f.name
        ]
        assert len(scans) >= 1

    def test_drawing_files_exist(self, generated_set: Path) -> None:
        """At least one DRAWING-type document must be present."""
        # WHY: Profiles always include at least one site plan drawing.
        # Missing drawings indicate a rendering or registry failure.
        drawings = [
            f for f in generated_set.iterdir() if "DRAWING" in f.name
        ]
        assert len(drawings) >= 1

    def test_reference_files_exist(self, generated_set: Path) -> None:
        """reference/parcel.geojson and reference/zone.json must be written."""
        # WHY: Reference files are consumed by the rule engine to evaluate
        # spatial compliance.  Their absence breaks downstream evaluation.
        assert (generated_set / "reference" / "parcel.geojson").exists()
        assert (generated_set / "reference" / "zone.json").exists()

    def test_bounding_boxes_within_bounds(self, generated_set: Path) -> None:
        """Every bounding box in ground_truth.json must have positive dimensions."""
        # WHY: Negative or zero bounding boxes indicate a coordinate-system bug
        # in the generator or the bbox-adjustment pipeline.  This catches
        # regressions where affine transforms produce nonsensical geometry.
        gt = json.loads((generated_set / "ground_truth.json").read_text())
        for doc in gt["documents"]:
            for ext in doc.get("extractions", []):
                bb = ext["bounding_box"]
                assert bb["x"] >= 0
                assert bb["y"] >= 0
                assert bb["width"] > 0
                assert bb["height"] > 0

    def test_seed_determinism(self, tmp_path: Path) -> None:
        """Two runs with the same seed must produce identical ground_truth.json."""
        # WHY: Determinism is a hard requirement for the corpus — evaluation
        # results must be reproducible across machines and over time.  If this
        # test fails it means some generator is using non-seeded randomness.
        from planproof.datagen.runner import generate_sets

        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        generate_sets(output_dir=dir1, category="compliant", count=1, seed=42)
        generate_sets(output_dir=dir2, category="compliant", count=1, seed=42)
        gt1 = (
            list((dir1 / "compliant").iterdir())[0] / "ground_truth.json"
        )
        gt2 = (
            list((dir2 / "compliant").iterdir())[0] / "ground_truth.json"
        )
        assert gt1.read_text() == gt2.read_text()
