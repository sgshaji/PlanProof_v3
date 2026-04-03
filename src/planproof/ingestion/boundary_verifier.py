"""Three-tier boundary verification pipeline for PlanProof.

Implements three independent verifiers that each examine a different evidence
source and produce a typed result schema:

  Tier 1 — VisualAlignmentVerifier
      Sends the location plan image to GPT-4o and asks whether the red-line
      boundary is visually aligned with OS base-map property boundaries.

  Tier 2 — ScaleBarVerifier
      Sends the location plan image to GPT-4o to read the scale bar and
      estimate site dimensions, then compares the estimated area against the
      declared area to detect significant discrepancies (> 15 %).

  Tier 3 — InspireVerifier
      Geocodes the site postcode via postcodes.io, finds the nearest cadastral
      parcel in an in-memory INSPIRE index, and checks whether the declared
      area substantially exceeds the polygon area (ratio > 1.5).

All three classes share the ``_MIME_MAP`` dict and the module-level
``_geocode_postcode`` helper so that tests can patch a single symbol.
"""
from __future__ import annotations

import base64
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.inspire_parser import InspireIndex
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.schemas.boundary import InspireResult, ScaleBarResult, VisualAlignmentResult

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_MIME_MAP: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "webp": "image/webp",
}

_OVER_CLAIMING_RATIO_THRESHOLD = 1.5
_DISCREPANCY_PCT_THRESHOLD = 0.15
_GEOCODE_TIMEOUT_S = 10


def _geocode_postcode(postcode: str) -> tuple[float, float] | None:
    """Return ``(easting, northing)`` for *postcode* via postcodes.io.

    Uses only the standard-library ``urllib.request`` so no additional
    dependency is introduced.  Returns ``None`` on any network or parse
    error.

    Parameters
    ----------
    postcode:
        UK postcode string, e.g. ``"SW1A 1AA"``.

    Returns
    -------
    tuple[float, float] | None
        ``(easting, northing)`` in EPSG:27700, or ``None`` if the geocode
        fails or the postcode is not found.
    """
    safe_postcode = urllib.request.quote(postcode.strip())
    url = f"https://api.postcodes.io/postcodes/{safe_postcode}"
    try:
        with urllib.request.urlopen(url, timeout=_GEOCODE_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = data.get("result") or {}
        easting = result.get("eastings")
        northing = result.get("northings")
        if easting is None or northing is None:
            log.warning("boundary_verifier.geocode_missing_coords", postcode=postcode)
            return None
        return float(easting), float(northing)
    except (urllib.error.URLError, KeyError, ValueError, TypeError) as exc:
        log.warning("boundary_verifier.geocode_failed", postcode=postcode, reason=str(exc))
        return None


def _b64_encode_image(image_path: Path) -> tuple[str, str]:
    """Return ``(base64_string, mime_type)`` for the image at *image_path*."""
    suffix = image_path.suffix.lower().lstrip(".")
    mime_type = _MIME_MAP.get(suffix, "image/png")
    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return b64, mime_type


def _strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from *text*."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Drop first line (```json or ```) and last line (```)
        stripped = "\n".join(lines[1:-1])
    return stripped


# ---------------------------------------------------------------------------
# Tier 1: VisualAlignmentVerifier
# ---------------------------------------------------------------------------


class VisualAlignmentVerifier:
    """Tier 1 boundary verifier: VLM-based visual alignment check.

    Sends the location plan image to GPT-4o with a structured prompt asking
    whether the red-line boundary aligns with OS base-map property boundaries.
    Returns :class:`~planproof.schemas.boundary.VisualAlignmentResult`.

    Parameters
    ----------
    vision_client:
        An OpenAI-compatible client instance (``openai.OpenAI``).
    prompts_dir:
        Directory containing ``boundary_visual.yaml``.
    """

    _TEMPLATE_NAME = "boundary_visual"
    _MODEL = "gpt-4o"

    def __init__(self, vision_client: Any, prompts_dir: Path) -> None:
        self._client = vision_client
        self._loader = PromptLoader(prompts_dir)

    def verify(self, image_path: Path) -> VisualAlignmentResult:
        """Verify that the red-line boundary in *image_path* is visually aligned.

        Parameters
        ----------
        image_path:
            Path to the location plan image (PNG, JPEG, or TIFF).

        Returns
        -------
        VisualAlignmentResult
            Parsed verification result.  On any failure returns
            ``status="UNCLEAR"`` with ``confidence=0.0``.
        """
        try:
            template = self._loader.load(self._TEMPLATE_NAME)
            b64, mime_type = _b64_encode_image(image_path)

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": template.system_message},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": template.user_message_template},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                        },
                    ],
                },
            ]

            response = self._client.chat.completions.create(
                model=self._MODEL,
                messages=messages,
                temperature=0,
                max_tokens=500,
            )
            content: str = response.choices[0].message.content or ""
            return self._parse(content)

        except Exception as exc:  # noqa: BLE001
            log.error(
                "boundary_verifier.tier1_failed",
                path=str(image_path),
                reason=str(exc),
            )
            return VisualAlignmentResult(status="UNCLEAR", issues=[], confidence=0.0)

    def _parse(self, content: str) -> VisualAlignmentResult:
        """Parse the VLM JSON response into a :class:`VisualAlignmentResult`."""
        try:
            data = json.loads(_strip_markdown_fences(content))
            return VisualAlignmentResult(
                status=data["status"],
                issues=data.get("issues", []),
                confidence=float(data.get("confidence", 0.0)),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            log.warning(
                "boundary_verifier.tier1_parse_failed",
                reason=str(exc),
                preview=content[:200],
            )
            return VisualAlignmentResult(status="UNCLEAR", issues=[], confidence=0.0)


# ---------------------------------------------------------------------------
# Tier 2: ScaleBarVerifier
# ---------------------------------------------------------------------------


class ScaleBarVerifier:
    """Tier 2 boundary verifier: VLM-based scale-bar measurement.

    Sends the location plan image to GPT-4o to read the scale bar and estimate
    frontage, depth, and area.  Compares the estimated area to the declared
    area and raises a flag when the discrepancy exceeds 15 %.

    Parameters
    ----------
    vision_client:
        An OpenAI-compatible client instance.
    prompts_dir:
        Directory containing ``boundary_scalebar.yaml``.
    """

    _TEMPLATE_NAME = "boundary_scalebar"
    _MODEL = "gpt-4o"

    def __init__(self, vision_client: Any, prompts_dir: Path) -> None:
        self._client = vision_client
        self._loader = PromptLoader(prompts_dir)

    def verify(self, image_path: Path, declared_area_m2: float) -> ScaleBarResult:
        """Estimate site area from scale bar and compare to *declared_area_m2*.

        Parameters
        ----------
        image_path:
            Path to the location plan image.
        declared_area_m2:
            Area declared in the planning application (m²).

        Returns
        -------
        ScaleBarResult
            Measurement result.  On VLM failure or null scale bar returns
            safe defaults (``discrepancy_flag=False``, ``confidence=0.0``).
        """
        try:
            template = self._loader.load(self._TEMPLATE_NAME)
            b64, mime_type = _b64_encode_image(image_path)

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": template.system_message},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": template.user_message_template},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                        },
                    ],
                },
            ]

            response = self._client.chat.completions.create(
                model=self._MODEL,
                messages=messages,
                temperature=0,
                max_tokens=500,
            )
            content: str = response.choices[0].message.content or ""
            return self._parse(content, declared_area_m2)

        except Exception as exc:  # noqa: BLE001
            log.error(
                "boundary_verifier.tier2_failed",
                path=str(image_path),
                reason=str(exc),
            )
            return self._safe_defaults(declared_area_m2)

    def _parse(self, content: str, declared_area_m2: float) -> ScaleBarResult:
        """Parse VLM JSON and compute discrepancy metrics."""
        try:
            data = json.loads(_strip_markdown_fences(content))
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning(
                "boundary_verifier.tier2_parse_failed",
                reason=str(exc),
                preview=content[:200],
            )
            return self._safe_defaults(declared_area_m2)

        frontage: float | None = data.get("frontage_m")
        depth: float | None = data.get("depth_m")
        estimated: float | None = data.get("area_m2")

        # If any measurement is missing, return safe defaults (no discrepancy
        # can be computed) with confidence 0 to signal low-quality data.
        if estimated is None:
            return ScaleBarResult(
                estimated_frontage_m=frontage,
                estimated_depth_m=depth,
                estimated_area_m2=None,
                declared_area_m2=declared_area_m2,
                discrepancy_pct=None,
                discrepancy_flag=False,
                confidence=0.0,
            )

        discrepancy_pct = (estimated - declared_area_m2) / declared_area_m2 * 100.0
        discrepancy_flag = abs(estimated - declared_area_m2) / declared_area_m2 > _DISCREPANCY_PCT_THRESHOLD

        return ScaleBarResult(
            estimated_frontage_m=frontage,
            estimated_depth_m=depth,
            estimated_area_m2=float(estimated),
            declared_area_m2=declared_area_m2,
            discrepancy_pct=discrepancy_pct,
            discrepancy_flag=discrepancy_flag,
            confidence=0.8,
        )

    @staticmethod
    def _safe_defaults(declared_area_m2: float) -> ScaleBarResult:
        return ScaleBarResult(
            estimated_frontage_m=None,
            estimated_depth_m=None,
            estimated_area_m2=None,
            declared_area_m2=declared_area_m2,
            discrepancy_pct=None,
            discrepancy_flag=False,
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Tier 3: InspireVerifier
# ---------------------------------------------------------------------------


class InspireVerifier:
    """Tier 3 boundary verifier: INSPIRE polygon area comparison.

    Geocodes the site postcode via postcodes.io, finds the nearest cadastral
    parcel in an :class:`~planproof.ingestion.inspire_parser.InspireIndex`,
    and compares the declared area against the polygon area to detect
    over-claiming (declared / polygon > 1.5).

    Parameters
    ----------
    inspire_index:
        Pre-built spatial index over INSPIRE Index Polygons GML data.
    """

    def __init__(self, inspire_index: InspireIndex) -> None:
        self._index = inspire_index

    def verify(self, postcode: str, declared_area_m2: float) -> InspireResult:
        """Verify the declared area against the nearest INSPIRE parcel.

        Parameters
        ----------
        postcode:
            UK postcode for the application site.
        declared_area_m2:
            Area declared in the planning application (m²).

        Returns
        -------
        InspireResult
            Verification result.  Returns ``confidence=0.0`` when geocoding
            fails or no parcel is found within 200 m of the postcode centroid.
        """
        coords = _geocode_postcode(postcode)
        if coords is None:
            log.warning("boundary_verifier.tier3_geocode_failed", postcode=postcode)
            return InspireResult(
                inspire_id=None,
                polygon_area_m2=None,
                declared_area_m2=declared_area_m2,
                area_ratio=None,
                over_claiming_flag=False,
                confidence=0.0,
            )

        easting, northing = coords
        parcel = self._index.find_nearest(easting, northing)
        if parcel is None:
            log.warning(
                "boundary_verifier.tier3_no_parcel",
                postcode=postcode,
                easting=easting,
                northing=northing,
            )
            return InspireResult(
                inspire_id=None,
                polygon_area_m2=None,
                declared_area_m2=declared_area_m2,
                area_ratio=None,
                over_claiming_flag=False,
                confidence=0.0,
            )

        area_ratio = declared_area_m2 / parcel.area_m2 if parcel.area_m2 > 0 else None
        over_claiming_flag = (
            area_ratio is not None and area_ratio > _OVER_CLAIMING_RATIO_THRESHOLD
        )

        log.info(
            "boundary_verifier.tier3_result",
            postcode=postcode,
            inspire_id=parcel.inspire_id,
            polygon_area_m2=parcel.area_m2,
            declared_area_m2=declared_area_m2,
            area_ratio=area_ratio,
            over_claiming_flag=over_claiming_flag,
        )

        return InspireResult(
            inspire_id=parcel.inspire_id,
            polygon_area_m2=parcel.area_m2,
            declared_area_m2=declared_area_m2,
            area_ratio=area_ratio,
            over_claiming_flag=over_claiming_flag,
            confidence=0.9,
        )
