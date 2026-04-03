"""Pure-Python parser for HM Land Registry INSPIRE Index Polygons GML.

Parses cadastral parcel boundaries from the 347 MB WFS 2.0 / GML 3.2 download
without geopandas, fiona, or shapely.  Uses ``xml.etree.ElementTree.iterparse``
so the file is streamed rather than loaded into memory wholesale.

Typical usage
-------------
>>> index = InspireIndex.from_gml(Path("INSPIRE_Index_Polygons.gml"))
>>> parcel = index.find_nearest(easting=530_000, northing=180_000)
"""
from __future__ import annotations

import bisect
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from planproof.infrastructure.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# GML namespace map
# ---------------------------------------------------------------------------
_NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "LR": "www.landregistry.gov.uk",
}

_TAG_PREDEFINED = f"{{{_NS['LR']}}}PREDEFINED"
_TAG_INSPIREID = f"{{{_NS['LR']}}}INSPIREID"
_TAG_POSLIST = f"{{{_NS['gml']}}}posList"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def shoelace_area(coords: list[tuple[float, float]]) -> float:
    """Return the area of a polygon using the shoelace formula.

    Parameters
    ----------
    coords:
        Ordered vertex list ``[(x0, y0), (x1, y1), ...]``.  May be an open or
        closed ring — the formula handles both correctly.

    Returns
    -------
    float
        Absolute area in the same units as *coords*.  Returns ``0.0`` for
        fewer than 3 vertices.
    """
    n = len(coords)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x_i, y_i = coords[i]
        x_j, y_j = coords[(i + 1) % n]
        total += x_i * y_j - x_j * y_i
    return abs(total) * 0.5


def _centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Return the mean-vertex centroid, excluding a closing vertex if present.

    Parameters
    ----------
    coords:
        Ordered vertex list ``[(x0, y0), ...]``.

    Returns
    -------
    tuple[float, float]
        ``(mean_easting, mean_northing)``.

    Raises
    ------
    ValueError
        If *coords* is empty.
    """
    if not coords:
        raise ValueError("coords must not be empty")

    pts = coords
    # Drop closing vertex when polygon ring is closed (first == last)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]

    n = len(pts)
    e = sum(p[0] for p in pts) / n
    n_ = sum(p[1] for p in pts) / n
    return e, n_


def _parse_pos_list(text: str) -> list[tuple[float, float]]:
    """Convert a GML ``posList`` string into a coordinate list.

    INSPIRE GML uses interleaved easting/northing pairs::

        "e1 n1 e2 n2 ..."

    Parameters
    ----------
    text:
        Raw ``posList`` text content.

    Returns
    -------
    list[tuple[float, float]]
        ``[(easting, northing), ...]``
    """
    values = [float(v) for v in text.split()]
    return [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CadastralParcel:
    """One cadastral parcel extracted from an INSPIRE GML file.

    Attributes
    ----------
    inspire_id:
        The INSPIRE identifier string (``LR:INSPIREID`` element text).
    coordinates:
        Ordered boundary vertices as ``[(easting, northing), ...]`` in OSGB36
        (EPSG:27700).  The ring may be open or closed.
    area_m2:
        Polygon area in square metres, computed via the shoelace formula.
    centroid_e:
        Mean easting of the polygon vertices (metres, EPSG:27700).
    centroid_n:
        Mean northing of the polygon vertices (metres, EPSG:27700).
    """

    inspire_id: str
    coordinates: list[tuple[float, float]]
    area_m2: float
    centroid_e: float
    centroid_n: float


class InspireIndex:
    """In-memory spatial index over a parsed INSPIRE GML file.

    The index sorts parcels by centroid easting so that
    :meth:`find_nearest` can use binary search to prune candidates before
    computing Euclidean distances.

    Attributes
    ----------
    parcels:
        All parsed parcels, sorted ascending by ``centroid_e``.
    """

    def __init__(self, parcels: list[CadastralParcel]) -> None:
        # Keep sorted by centroid easting for binary-search lookup
        self.parcels: list[CadastralParcel] = sorted(
            parcels, key=lambda p: p.centroid_e
        )
        # Parallel list of easting values used by bisect
        self._eastings: list[float] = [p.centroid_e for p in self.parcels]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_gml(cls, gml_path: Path) -> "InspireIndex":
        """Stream-parse an INSPIRE GML file and build an :class:`InspireIndex`.

        Uses ``ET.iterparse`` so only one ``LR:PREDEFINED`` element is held in
        memory at a time, keeping peak RAM manageable even for the 347 MB
        production file.

        Parameters
        ----------
        gml_path:
            Path to the ``.gml`` (or ``.xml``) INSPIRE download.

        Returns
        -------
        InspireIndex
            Populated index ready for spatial queries.
        """
        log.info("inspire_parser.parsing_start", path=str(gml_path))
        parcels: list[CadastralParcel] = []
        skipped = 0

        for event, elem in ET.iterparse(str(gml_path), events=("end",)):
            if elem.tag != _TAG_PREDEFINED:
                continue

            try:
                parcel = _element_to_parcel(elem)
                if parcel is not None:
                    parcels.append(parcel)
                else:
                    skipped += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                log.warning(
                    "inspire_parser.parcel_skip",
                    reason=str(exc),
                    elem_attrib=elem.attrib,
                )
            finally:
                # Release the element subtree to keep memory flat
                elem.clear()

        log.info(
            "inspire_parser.parsing_done",
            parsed=len(parcels),
            skipped=skipped,
        )
        return cls(parcels)

    # ------------------------------------------------------------------
    # Spatial query
    # ------------------------------------------------------------------

    def find_nearest(
        self,
        easting: float,
        northing: float,
        max_distance_m: float = 200.0,
    ) -> Optional[CadastralParcel]:
        """Return the nearest parcel centroid within *max_distance_m* metres.

        Uses binary search on the easting axis to identify a candidate window,
        then performs exact Euclidean distance comparison within that window.

        Parameters
        ----------
        easting:
            Query easting in EPSG:27700 metres.
        northing:
            Query northing in EPSG:27700 metres.
        max_distance_m:
            Search radius.  Parcels further than this are ignored.

        Returns
        -------
        CadastralParcel | None
            Closest parcel, or ``None`` if no parcel falls within the radius.
        """
        if not self.parcels:
            return None

        # Binary search bounds on easting axis
        lo = bisect.bisect_left(self._eastings, easting - max_distance_m)
        hi = bisect.bisect_right(self._eastings, easting + max_distance_m)

        best: Optional[CadastralParcel] = None
        best_dist = math.inf

        for parcel in self.parcels[lo:hi]:
            de = parcel.centroid_e - easting
            dn = parcel.centroid_n - northing
            dist = math.sqrt(de * de + dn * dn)
            if dist <= max_distance_m and dist < best_dist:
                best_dist = dist
                best = parcel

        return best


# ---------------------------------------------------------------------------
# Private parsing helper
# ---------------------------------------------------------------------------

def _element_to_parcel(elem: ET.Element) -> Optional[CadastralParcel]:
    """Convert a ``LR:PREDEFINED`` XML element into a :class:`CadastralParcel`.

    Parameters
    ----------
    elem:
        The element representing one feature member.

    Returns
    -------
    CadastralParcel | None
        Parsed parcel, or ``None`` if mandatory data is absent.
    """
    # --- INSPIRE ID -------------------------------------------------------
    id_elem = elem.find(_TAG_INSPIREID)
    if id_elem is None or not (id_elem.text or "").strip():
        return None
    inspire_id = id_elem.text.strip()

    # --- Geometry (first posList found) -----------------------------------
    pos_elem = elem.find(f".//{_TAG_POSLIST}")
    if pos_elem is None or not (pos_elem.text or "").strip():
        return None

    coords = _parse_pos_list(pos_elem.text.strip())
    if len(coords) < 3:
        return None

    area = shoelace_area(coords)
    ce, cn = _centroid(coords)

    return CadastralParcel(
        inspire_id=inspire_id,
        coordinates=coords,
        area_m2=area,
        centroid_e=ce,
        centroid_n=cn,
    )
