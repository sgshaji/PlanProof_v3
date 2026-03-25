"""Tests for degradation transforms.

# WHY: TDD-first — these tests define the contract for each transform before
# any implementation exists. Running them red first confirms the module is
# absent, then green after implementation confirms correctness.
"""

import numpy as np
import pytest

from planproof.datagen.degradation.transforms import (
    ImageArray,
    TransformResult,
    add_gaussian_noise,
    add_partial_occlusion,
    add_speckle_noise,
    adjust_contrast,
    apply_jpeg_compression,
    apply_rotation,
    dilate_erode,
    vary_resolution,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_test_image(width: int = 200, height: int = 300) -> ImageArray:
    """Create a simple test image with some structure (not blank).

    # WHY: A uniform blank image would make several transforms indistinguishable
    # (e.g. contrast, noise). Embedding a dark rectangle ensures there is
    # meaningful variation in pixel values for all assertions.
    """
    img = np.ones((height, width, 3), dtype=np.uint8) * 200
    img[50:100, 50:150] = 50  # dark rectangle
    return img


# ---------------------------------------------------------------------------
# 1. Gaussian noise
# ---------------------------------------------------------------------------


def test_gaussian_noise_changes_pixels() -> None:
    """Output pixel values must differ from input; no geometric change."""
    img = _make_test_image()
    result = add_gaussian_noise(img, sigma=25.0)

    assert isinstance(result, TransformResult)
    assert result.affine is None, "gaussian noise is non-geometric — affine must be None"
    assert not np.array_equal(result.image, img), "noise must change at least some pixels"
    assert result.image.shape == img.shape, "shape must be preserved"


# ---------------------------------------------------------------------------
# 2. Speckle noise (salt-and-pepper)
# ---------------------------------------------------------------------------


def test_speckle_noise_sparse_changes() -> None:
    """Some pixels should change; most should stay the same (sparse); no affine."""
    img = _make_test_image()
    result = add_speckle_noise(img, density=0.05)

    assert isinstance(result, TransformResult)
    assert result.affine is None, "speckle noise is non-geometric"
    changed = np.sum(result.image != img)
    total = img.size
    # With 5 % density we expect some pixels changed but not all
    assert changed > 0, "at least some pixels must change"
    assert changed < total, "not every pixel should be touched"
    assert result.image.shape == img.shape


# ---------------------------------------------------------------------------
# 3. Rotation
# ---------------------------------------------------------------------------


def test_rotation_returns_affine() -> None:
    """Rotation is geometric — affine must be a 3x3 float64 matrix."""
    img = _make_test_image()
    result = apply_rotation(img, degrees=15.0)

    assert isinstance(result, TransformResult)
    assert result.affine is not None, "rotation must return an affine matrix"
    assert result.affine.shape == (3, 3), "affine must be 3x3"
    assert result.affine.dtype == np.float64, "affine dtype must be float64"
    assert result.image.ndim == 3, "output must still be an HxWx3 image"


# ---------------------------------------------------------------------------
# 4. JPEG compression
# ---------------------------------------------------------------------------


def test_jpeg_compression_reduces_quality() -> None:
    """JPEG is lossy — output must differ from input; no affine."""
    img = _make_test_image()
    result = apply_jpeg_compression(img, quality=30)

    assert isinstance(result, TransformResult)
    assert result.affine is None, "jpeg compression is non-geometric"
    assert not np.array_equal(result.image, img), "JPEG lossy encoding must change pixels"
    assert result.image.shape == img.shape, "shape must be preserved"


# ---------------------------------------------------------------------------
# 5. Resolution variation
# ---------------------------------------------------------------------------


def test_vary_resolution_returns_affine() -> None:
    """Downscale then upscale — affine must encode scale; image may be resized."""
    img = _make_test_image(width=200, height=300)
    result = vary_resolution(img, target_dpi=150, current_dpi=300)

    assert isinstance(result, TransformResult)
    assert result.affine is not None, "resolution change is geometric — affine required"
    assert result.affine.shape == (3, 3)
    assert result.affine.dtype == np.float64
    # The scale factor should be embedded in the diagonal
    # target/current = 0.5 → pixels are scaled 0.5 then back; final image
    # may be same size as input but the affine records the effective scale.
    scale = result.affine[0, 0]
    assert scale == pytest.approx(0.5, abs=0.01), (
        f"affine diagonal should encode scale 0.5, got {scale}"
    )


# ---------------------------------------------------------------------------
# 6. Dilate / erode
# ---------------------------------------------------------------------------


def test_dilate_erode_changes_strokes() -> None:
    """Morphological ops must change pixel values; no affine."""
    img = _make_test_image()
    result = dilate_erode(img, kernel_size=3, iterations=2)

    assert isinstance(result, TransformResult)
    assert result.affine is None, "dilate/erode is non-geometric"
    assert not np.array_equal(result.image, img), "morphological op must change some pixels"
    assert result.image.shape == img.shape


# ---------------------------------------------------------------------------
# 7. Partial occlusion
# ---------------------------------------------------------------------------


def test_partial_occlusion_adds_patches() -> None:
    """Dark patches must appear; the image should have new very-dark pixels."""
    img = _make_test_image()
    result = add_partial_occlusion(img, count=3, size=0.1, seed=42)

    assert isinstance(result, TransformResult)
    assert result.affine is None, "occlusion is non-geometric"
    # Patches are dark — look for pixels < 30 outside the original dark rect
    out = result.image.copy()
    # Mask out original dark area (rows 50-100, cols 50-150)
    out[50:100, 50:150] = 200
    dark_pixels = np.sum(out < 30)
    assert dark_pixels > 0, "occlusion patches should create very dark pixels"


# ---------------------------------------------------------------------------
# 8. Contrast adjustment
# ---------------------------------------------------------------------------


def test_adjust_contrast_changes_histogram() -> None:
    """A contrast factor != 1.0 must change the pixel histogram."""
    img = _make_test_image()
    result = adjust_contrast(img, factor=2.0)

    assert isinstance(result, TransformResult)
    assert result.affine is None, "contrast adjustment is non-geometric"
    original_hist, _ = np.histogram(img, bins=256, range=(0, 255))
    result_hist, _ = np.histogram(result.image, bins=256, range=(0, 255))
    assert not np.array_equal(original_hist, result_hist), "histogram must change after contrast boost"
    assert result.image.shape == img.shape


# ---------------------------------------------------------------------------
# 9. dtype preservation across all transforms
# ---------------------------------------------------------------------------


def test_transforms_preserve_dtype() -> None:
    """Every transform must return a uint8 image regardless of internal ops."""
    img = _make_test_image()

    transforms_and_args = [
        (add_gaussian_noise, {"sigma": 15.0}),
        (add_speckle_noise, {"density": 0.05}),
        (apply_rotation, {"degrees": 10.0}),
        (apply_jpeg_compression, {"quality": 50}),
        (vary_resolution, {"target_dpi": 150, "current_dpi": 300}),
        (dilate_erode, {"kernel_size": 3, "iterations": 1}),
        (add_partial_occlusion, {"count": 2, "size": 0.08, "seed": 0}),
        (adjust_contrast, {"factor": 1.5}),
    ]

    for fn, kwargs in transforms_and_args:
        result = fn(img, **kwargs)  # type: ignore[operator]
        assert result.image.dtype == np.uint8, (
            f"{fn.__name__} returned dtype {result.image.dtype}, expected uint8"
        )
