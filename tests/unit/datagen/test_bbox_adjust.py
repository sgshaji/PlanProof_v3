"""Tests for bounding-box affine adjustment.

# WHY: TDD-first — tests define the contract for adjust_bounding_boxes() before
# any implementation exists.  The three tests cover the three interesting cases:
# identity (no-op), scale (axis-aligned enlargement), and rotation (non-trivial
# corner mapping).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from planproof.datagen.degradation.transforms import AffineMatrix
from planproof.datagen.rendering.models import PlacedValue
from planproof.schemas.entities import BoundingBox, EntityType


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _identity_affine() -> AffineMatrix:
    """Return a 3×3 float64 identity matrix."""
    return np.eye(3, dtype=np.float64)


def _scale_affine(sx: float, sy: float) -> AffineMatrix:
    """Build a 3×3 homogeneous scale matrix."""
    m = _identity_affine()
    m[0, 0] = sx
    m[1, 1] = sy
    return m


def _rotation_affine(degrees: float) -> AffineMatrix:
    """Build a 3×3 rotation matrix around the origin.

    # WHY: Using a rotation around the origin keeps the expected values simple
    # and verifiable by hand, without the additional translation offset needed
    # for centre-anchored rotation.
    """
    theta = math.radians(degrees)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    m = _identity_affine()
    m[0, 0] = cos_t
    m[0, 1] = -sin_t
    m[1, 0] = sin_t
    m[1, 1] = cos_t
    return m


def _make_placed_value(x: float, y: float, w: float, h: float) -> PlacedValue:
    """Construct a minimal PlacedValue with the given bounding box."""
    return PlacedValue(
        attribute="test_attr",
        value=42,
        text_rendered="42",
        page=1,
        bounding_box=BoundingBox(x=x, y=y, width=w, height=h, page=1),
        entity_type=EntityType.MEASUREMENT,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_identity_affine_unchanged() -> None:
    """Identity affine must return bounding boxes unchanged (fast path).

    # WHY: Most pipelines produce no geometric transforms; the identity fast-path
    # avoids unnecessary coordinate arithmetic and preserves the exact float
    # values (no floating-point accumulation error).
    """
    from planproof.datagen.degradation.bbox_adjust import adjust_bounding_boxes

    pv = _make_placed_value(x=10.0, y=20.0, w=100.0, h=50.0)
    result = adjust_bounding_boxes((pv,), _identity_affine())

    assert len(result) == 1
    bb = result[0].bounding_box
    assert bb.x == pytest.approx(10.0)
    assert bb.y == pytest.approx(20.0)
    assert bb.width == pytest.approx(100.0)
    assert bb.height == pytest.approx(50.0)


def test_scale_affine_scales_bbox() -> None:
    """A 2× uniform scale must double all bbox coordinates.

    # WHY: Uniform scaling is the most common geometric change (resolution
    # variation); verifying it exactly validates the corner-mapping logic without
    # angular complexity.
    """
    from planproof.datagen.degradation.bbox_adjust import adjust_bounding_boxes

    pv = _make_placed_value(x=10.0, y=20.0, w=100.0, h=50.0)
    result = adjust_bounding_boxes((pv,), _scale_affine(2.0, 2.0))

    assert len(result) == 1
    bb = result[0].bounding_box
    assert bb.x == pytest.approx(20.0, abs=1e-6)
    assert bb.y == pytest.approx(40.0, abs=1e-6)
    assert bb.width == pytest.approx(200.0, abs=1e-6)
    assert bb.height == pytest.approx(100.0, abs=1e-6)


def test_rotation_adjusts_bbox() -> None:
    """A 90° rotation must produce a bbox that covers the rotated corners.

    # WHY: Rotation is the most impactful geometric degradation; the resulting
    # axis-aligned bounding box must be the minimal rectangle that contains all
    # four rotated corners of the original box.  For 90° this is deterministic
    # and verifiable by hand: a WxH rectangle becomes HxW.
    """
    from planproof.datagen.degradation.bbox_adjust import adjust_bounding_boxes

    # A box at (0, 0) with width=80, height=40.
    # After 90° CCW rotation around origin:
    #   (0,0) → (0,0), (80,0) → (0,80), (0,40) → (-40,0), (80,40) → (-40,80)
    # x range: [-40, 0]  → x=-40, width=40
    # y range: [0, 80]   → y=0, height=80
    pv = _make_placed_value(x=0.0, y=0.0, w=80.0, h=40.0)
    result = adjust_bounding_boxes((pv,), _rotation_affine(90.0))

    assert len(result) == 1
    bb = result[0].bounding_box
    # width and height swap
    assert bb.width == pytest.approx(40.0, abs=1e-4)
    assert bb.height == pytest.approx(80.0, abs=1e-4)


def test_empty_tuple_returns_empty() -> None:
    """adjust_bounding_boxes on an empty tuple must return an empty tuple.

    # WHY: Guard against IndexError or type errors when the document has no
    # placed values (e.g. the clean preset).
    """
    from planproof.datagen.degradation.bbox_adjust import adjust_bounding_boxes

    result = adjust_bounding_boxes((), _identity_affine())
    assert result == ()
