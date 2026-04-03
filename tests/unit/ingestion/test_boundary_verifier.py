"""Tests for the three-tier boundary verification pipeline.

Tests cover:
  - Tier 1: VisualAlignmentVerifier (VLM-based visual alignment check)
  - Tier 2: ScaleBarVerifier (VLM-based scale bar measurement)
  - Tier 3: InspireVerifier (INSPIRE polygon area comparison)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from planproof.ingestion.boundary_verifier import (
    InspireVerifier,
    ScaleBarVerifier,
    VisualAlignmentVerifier,
)
from planproof.ingestion.inspire_parser import CadastralParcel, InspireIndex
from planproof.schemas.boundary import InspireResult, ScaleBarResult, VisualAlignmentResult


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_image(tmp_path: Path) -> Path:
    """Create a minimal PNG for VLM tests."""
    img = Image.new("RGB", (400, 300), color="white")
    path = tmp_path / "location_plan.png"
    img.save(path)
    return path


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Create the two boundary prompt YAML files under a temp prompts dir."""
    d = tmp_path / "prompts"
    d.mkdir()

    (d / "boundary_visual.yaml").write_text(
        "system_message: 'You are a visual alignment assistant.'\n"
        "user_message_template: 'Check the image boundary alignment.'\n",
        encoding="utf-8",
    )
    (d / "boundary_scalebar.yaml").write_text(
        "system_message: 'You are a measurement assistant.'\n"
        "user_message_template: 'Read the scale bar and estimate dimensions.'\n",
        encoding="utf-8",
    )
    return d


def _make_vlm_client(content: str) -> MagicMock:
    """Build a mock OpenAI client that returns *content* as the chat response."""
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    client.chat.completions.create.return_value = response
    return client


def _make_parcel(
    inspire_id: str = "TEST_001",
    area_m2: float = 300.0,
    centroid_e: float = 530_000.0,
    centroid_n: float = 180_000.0,
) -> CadastralParcel:
    coords = [
        (centroid_e - 10, centroid_n - 10),
        (centroid_e + 10, centroid_n - 10),
        (centroid_e + 10, centroid_n + 10),
        (centroid_e - 10, centroid_n + 10),
    ]
    return CadastralParcel(
        inspire_id=inspire_id,
        coordinates=coords,
        area_m2=area_m2,
        centroid_e=centroid_e,
        centroid_n=centroid_n,
    )


# ---------------------------------------------------------------------------
# Tier 1: VisualAlignmentVerifier
# ---------------------------------------------------------------------------


class TestVisualAlignmentVerifier:
    def test_aligned_response(self, prompts_dir: Path, test_image: Path) -> None:
        """VLM returns ALIGNED JSON → result has status ALIGNED and confidence > 0."""
        payload = json.dumps({"status": "ALIGNED", "issues": [], "confidence": 0.9})
        client = _make_vlm_client(payload)
        verifier = VisualAlignmentVerifier(client, prompts_dir)

        result: VisualAlignmentResult = verifier.verify(test_image)

        assert result.status == "ALIGNED"
        assert result.issues == []
        assert result.confidence == pytest.approx(0.9)

    def test_misaligned_response(self, prompts_dir: Path, test_image: Path) -> None:
        """VLM returns MISALIGNED JSON with issues list → result captures all issues."""
        payload = json.dumps(
            {
                "status": "MISALIGNED",
                "issues": ["Red line extends into highway", "Overlaps neighbouring parcel"],
                "confidence": 0.85,
            }
        )
        client = _make_vlm_client(payload)
        verifier = VisualAlignmentVerifier(client, prompts_dir)

        result: VisualAlignmentResult = verifier.verify(test_image)

        assert result.status == "MISALIGNED"
        assert len(result.issues) == 2
        assert result.confidence == pytest.approx(0.85)

    def test_vlm_failure_returns_unclear(self, prompts_dir: Path, test_image: Path) -> None:
        """When the VLM call raises, verifier returns UNCLEAR with confidence 0."""
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("API timeout")
        verifier = VisualAlignmentVerifier(client, prompts_dir)

        result: VisualAlignmentResult = verifier.verify(test_image)

        assert result.status == "UNCLEAR"
        assert result.confidence == pytest.approx(0.0)

    def test_markdown_fenced_json_is_parsed(self, prompts_dir: Path, test_image: Path) -> None:
        """VLM wraps JSON in markdown fences → still parsed correctly."""
        payload = "```json\n" + json.dumps({"status": "UNCLEAR", "issues": ["Ambiguous"], "confidence": 0.4}) + "\n```"
        client = _make_vlm_client(payload)
        verifier = VisualAlignmentVerifier(client, prompts_dir)

        result: VisualAlignmentResult = verifier.verify(test_image)

        assert result.status == "UNCLEAR"
        assert result.confidence == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Tier 2: ScaleBarVerifier
# ---------------------------------------------------------------------------


class TestScaleBarVerifier:
    def test_no_discrepancy(self, prompts_dir: Path, test_image: Path) -> None:
        """Estimated 500 m², declared 480 m² → 4 % difference → no flag."""
        payload = json.dumps(
            {"scale_ratio": "1:1250", "frontage_m": 20.0, "depth_m": 25.0, "area_m2": 500.0}
        )
        client = _make_vlm_client(payload)
        verifier = ScaleBarVerifier(client, prompts_dir)

        result: ScaleBarResult = verifier.verify(test_image, declared_area_m2=480.0)

        assert result.discrepancy_flag is False
        assert result.estimated_area_m2 == pytest.approx(500.0)
        assert result.declared_area_m2 == pytest.approx(480.0)
        assert result.discrepancy_pct is not None
        assert result.confidence > 0.0

    def test_discrepancy_over_15_pct(self, prompts_dir: Path, test_image: Path) -> None:
        """Estimated 500 m², declared 350 m² → 43 % difference → flag raised."""
        payload = json.dumps(
            {"scale_ratio": "1:1250", "frontage_m": 20.0, "depth_m": 25.0, "area_m2": 500.0}
        )
        client = _make_vlm_client(payload)
        verifier = ScaleBarVerifier(client, prompts_dir)

        result: ScaleBarResult = verifier.verify(test_image, declared_area_m2=350.0)

        assert result.discrepancy_flag is True
        assert result.discrepancy_pct is not None
        assert abs(result.discrepancy_pct) > 15.0

    def test_vlm_returns_null_no_flag(self, prompts_dir: Path, test_image: Path) -> None:
        """VLM returns null area → discrepancy_flag False, confidence 0."""
        payload = json.dumps(
            {"scale_ratio": None, "frontage_m": None, "depth_m": None, "area_m2": None}
        )
        client = _make_vlm_client(payload)
        verifier = ScaleBarVerifier(client, prompts_dir)

        result: ScaleBarResult = verifier.verify(test_image, declared_area_m2=480.0)

        assert result.discrepancy_flag is False
        assert result.confidence == pytest.approx(0.0)
        assert result.estimated_area_m2 is None
        assert result.discrepancy_pct is None

    def test_vlm_api_failure_safe_defaults(self, prompts_dir: Path, test_image: Path) -> None:
        """VLM call raises → safe defaults returned, no exception propagated."""
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("connection reset")
        verifier = ScaleBarVerifier(client, prompts_dir)

        result: ScaleBarResult = verifier.verify(test_image, declared_area_m2=200.0)

        assert result.discrepancy_flag is False
        assert result.confidence == pytest.approx(0.0)
        assert result.estimated_area_m2 is None


# ---------------------------------------------------------------------------
# Tier 3: InspireVerifier
# ---------------------------------------------------------------------------


class TestInspireVerifier:
    def _make_index(self, parcel: CadastralParcel | None = None) -> InspireIndex:
        parcels = [parcel] if parcel is not None else []
        return InspireIndex(parcels)

    def test_not_over_claiming(self) -> None:
        """Declared 288 m², polygon 300 m² → ratio 0.96 → no flag."""
        parcel = _make_parcel(area_m2=300.0, centroid_e=530_000.0, centroid_n=180_000.0)
        index = self._make_index(parcel)
        verifier = InspireVerifier(index)

        with patch(
            "planproof.ingestion.boundary_verifier._geocode_postcode",
            return_value=(530_000.0, 180_000.0),
        ):
            result: InspireResult = verifier.verify("SW1A 1AA", declared_area_m2=288.0)

        assert result.over_claiming_flag is False
        assert result.area_ratio == pytest.approx(288.0 / 300.0, rel=1e-3)
        assert result.confidence > 0.0

    def test_over_claiming(self) -> None:
        """Declared 500 m², polygon 300 m² → ratio 1.67 → flag raised."""
        parcel = _make_parcel(area_m2=300.0, centroid_e=530_000.0, centroid_n=180_000.0)
        index = self._make_index(parcel)
        verifier = InspireVerifier(index)

        with patch(
            "planproof.ingestion.boundary_verifier._geocode_postcode",
            return_value=(530_000.0, 180_000.0),
        ):
            result: InspireResult = verifier.verify("SW1A 1AA", declared_area_m2=500.0)

        assert result.over_claiming_flag is True
        assert result.area_ratio == pytest.approx(500.0 / 300.0, rel=1e-3)

    def test_geocode_fails(self) -> None:
        """Geocode returns None → confidence 0, no flag, inspire_id None."""
        index = self._make_index(_make_parcel())
        verifier = InspireVerifier(index)

        with patch(
            "planproof.ingestion.boundary_verifier._geocode_postcode",
            return_value=None,
        ):
            result: InspireResult = verifier.verify("ZZ9 9ZZ", declared_area_m2=300.0)

        assert result.confidence == pytest.approx(0.0)
        assert result.over_claiming_flag is False
        assert result.inspire_id is None

    def test_no_nearby_parcel(self) -> None:
        """Geocode resolves to coordinates far from any parcel → confidence 0."""
        parcel = _make_parcel(centroid_e=530_000.0, centroid_n=180_000.0)
        index = self._make_index(parcel)
        verifier = InspireVerifier(index)

        # Place the geocoded point far away (500 km north)
        with patch(
            "planproof.ingestion.boundary_verifier._geocode_postcode",
            return_value=(530_000.0, 680_000.0),
        ):
            result: InspireResult = verifier.verify("AB12 3CD", declared_area_m2=300.0)

        assert result.confidence == pytest.approx(0.0)
        assert result.over_claiming_flag is False
        assert result.inspire_id is None
