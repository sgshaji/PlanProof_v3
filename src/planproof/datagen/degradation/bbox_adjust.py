"""Bounding-box adjustment using accumulated affine matrices.

# DESIGN: Bounding boxes are recorded at generation time in the original image
# coordinate space.  When the degradation pipeline applies geometric transforms
# (rotation, resolution scaling), those transforms displace every pixel — and
# therefore every bounding box corner.  This module projects all four corners of
# each bounding box through the accumulated affine and computes the new
# axis-aligned bounding box (AABB) that encloses the projected corners.
#
# WHY AABB: The downstream evaluation harness crops regions using x/y/w/h
# rectangles, not arbitrary quads.  Taking the AABB of the transformed corners
# guarantees the original content is still inside the crop even when a rotation
# has made the box non-axis-aligned.  The crop is slightly conservative (larger
# than the rotated quad) which is the correct trade-off: a crop that is too
# large is better than one that clips part of the value.
#
# WHY pure FP: no mutation of the input tuple; a new tuple of new PlacedValue
# objects is always returned.  This preserves deep immutability for frozen
# dataclasses and enables safe parallel use.
"""

from __future__ import annotations

import numpy as np

from planproof.datagen.degradation.transforms import AffineMatrix
from planproof.datagen.rendering.models import PlacedValue
from planproof.schemas.entities import BoundingBox


def _is_identity(affine: AffineMatrix) -> bool:
    """Return True when *affine* is numerically equal to the 3×3 identity.

    # WHY: The identity fast-path is critical for the common case where the
    # pipeline contains no geometric transforms (e.g. clean or noise-only
    # presets).  Skipping the matrix operations preserves the exact original
    # float values without any floating-point accumulation error.
    """
    return bool(np.allclose(affine, np.eye(3, dtype=np.float64), atol=1e-9))


def _transform_bbox(bbox: BoundingBox, affine: AffineMatrix) -> BoundingBox:
    """Project all four corners of *bbox* through *affine* and return the AABB.

    # DESIGN: We use homogeneous 2-D coordinates [x, y, 1] so that the 3×3
    # affine (which may encode translation, rotation, and scale) can be applied
    # with a single matrix–vector multiply.  The four corners are:
    #
    #   top-left     (x,      y     )
    #   top-right    (x+w,    y     )
    #   bottom-left  (x,      y+h   )
    #   bottom-right (x+w,    y+h   )
    #
    # After projection we take min/max over all transformed x and y values to
    # produce the axis-aligned bounding box.

    Args:
        bbox:   Original BoundingBox in the pre-transform image space.
        affine: 3×3 homogeneous affine matrix (accumulated from the pipeline).

    Returns:
        New BoundingBox whose x/y/width/height enclose the projected corners.
        The page number is preserved unchanged.
    """
    x, y, w, h = bbox.x, bbox.y, bbox.width, bbox.height

    # Build a (3, 4) matrix: each column is one homogeneous corner [x, y, 1].
    corners = np.array(
        [
            [x, x + w, x, x + w],  # x coordinates
            [y, y, y + h, y + h],  # y coordinates
            [1.0, 1.0, 1.0, 1.0],  # homogeneous row
        ],
        dtype=np.float64,
    )

    # Project all four corners in one matrix multiply.
    # Result shape: (3, 4) — rows are [x', y', w'] in homogeneous coords.
    projected = affine @ corners

    # Normalise by homogeneous weight (w') in case of perspective transforms.
    # For affine-only transforms w' == 1 everywhere, so this is a no-op.
    xs = projected[0] / projected[2]
    ys = projected[1] / projected[2]

    # Compute the axis-aligned bounding box from the extremes.
    new_x = float(np.min(xs))
    new_y = float(np.min(ys))
    new_w = float(np.max(xs) - np.min(xs))
    new_h = float(np.max(ys) - np.min(ys))

    return BoundingBox(x=new_x, y=new_y, width=new_w, height=new_h, page=bbox.page)


def adjust_bounding_boxes(
    placed_values: tuple[PlacedValue, ...],
    affine: AffineMatrix,
) -> tuple[PlacedValue, ...]:
    """Return a new tuple of PlacedValues with bounding boxes adjusted for *affine*.

    # WHY: All bounding boxes accumulated during document rendering are in the
    # original (pre-degradation) image coordinate space.  After the degradation
    # pipeline runs, any geometric transforms (rotation, scale) must be reflected
    # in the bounding boxes so the evaluation harness can still locate the right
    # pixel region for each placed value.

    # DESIGN: The function is a pure transform — it never mutates its inputs.
    # New PlacedValue dataclasses are constructed with the adjusted bounding box
    # and all other attributes copied unchanged.  Because PlacedValue is a frozen
    # dataclass, we use dataclasses.replace() to construct the new instances
    # without manually repeating every field name.

    Args:
        placed_values: Tuple of PlacedValue records from the document renderer.
        affine:        3×3 accumulated affine from compose() or a single
                       TransformResult.affine.

    Returns:
        New tuple of PlacedValue objects with adjusted bounding_box fields.
        When *affine* is identity the input tuple is returned unchanged (same
        object) to avoid unnecessary allocations.
    """
    # WHY fast-path: the identity case is extremely common (clean preset, all
    # non-geometric pipelines) and returning the same tuple avoids allocating
    # new PlacedValue objects with effectively identical data.
    if _is_identity(affine):
        return placed_values

    if not placed_values:
        return placed_values

    from dataclasses import replace

    adjusted = tuple(
        replace(pv, bounding_box=_transform_bbox(pv.bounding_box, affine))
        for pv in placed_values
    )
    return adjusted
