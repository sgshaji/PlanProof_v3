"""Tests for compose() utility and load_preset() YAML loader.

# WHY: TDD-first — tests define the contract before implementation exists.
# Running them red first confirms the modules are absent, then green after
# implementation confirms correctness of the composing and preset-loading logic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from planproof.datagen.degradation.transforms import (
    AffineMatrix,
    ImageArray,
    apply_rotation,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

CONFIGS_DIR = Path(__file__).parents[3] / "configs" / "datagen" / "degradation"


def _make_image(height: int = 60, width: int = 80) -> ImageArray:
    """Return a small uint8 RGB test image with some structure.

    # WHY: Using a non-blank image ensures that transforms which depend on
    # pixel variation (e.g. contrast, noise) produce measurable changes.
    """
    img = np.ones((height, width, 3), dtype=np.uint8) * 128
    img[10:30, 10:40] = 30  # dark rectangle for structural variation
    return img


def _is_identity(m: AffineMatrix) -> bool:
    """Return True when the matrix is numerically close to a 3×3 identity."""
    return bool(np.allclose(m, np.eye(3, dtype=np.float64), atol=1e-9))


# ---------------------------------------------------------------------------
# Task 13 — compose()
# ---------------------------------------------------------------------------


def test_compose_empty_returns_identity() -> None:
    """compose() with no functions must return identity affine and unchanged image.

    # WHY: An empty pipeline should be a no-op; callers should be able to
    # compose zero transforms and safely use the result without special-casing.
    """
    from planproof.datagen.degradation.compose import compose

    pipeline = compose()
    img = _make_image()
    result = pipeline(img)

    assert np.array_equal(result.image, img), "empty compose must not alter image"
    assert _is_identity(result.accumulated_affine), (
        "empty compose must return identity affine"
    )


def test_compose_single_transform() -> None:
    """compose() wrapping one function must return the same image as calling it directly.

    # WHY: The single-function case is a regression guard — any wrapping overhead
    # must not alter the pixel values or affine produced by the inner function.
    """
    from planproof.datagen.degradation.compose import compose

    img = _make_image()

    # Use a deterministic transform with known output for comparison.
    from functools import partial

    from planproof.datagen.degradation.transforms import add_gaussian_noise

    np.random.seed(0)
    direct = add_gaussian_noise(img, sigma=10.0)

    np.random.seed(0)
    pipeline = compose(partial(add_gaussian_noise, sigma=10.0))
    composed = pipeline(img)

    assert np.array_equal(composed.image, direct.image), (
        "single-fn compose must produce same image as direct call"
    )
    # gaussian_noise has affine=None; accumulated_affine should be identity
    assert _is_identity(composed.accumulated_affine), (
        "non-geometric transform must leave accumulated affine as identity"
    )


def test_compose_accumulates_affines() -> None:
    """Two geometric transforms must produce a composed affine (matrix product).

    # WHY: The whole point of tracking affines through the pipeline is so that
    # bounding-box adjustment can be done in one shot.  If we rotate twice the
    # accumulated affine must equal R2 @ R1, not just R2.
    """
    from functools import partial

    from planproof.datagen.degradation.compose import compose

    img = _make_image()

    rot15 = partial(apply_rotation, degrees=15.0)
    rot10 = partial(apply_rotation, degrees=10.0)

    # Compute expected affine: apply rot15 first then rot10
    r1 = apply_rotation(img, degrees=15.0)
    r2 = apply_rotation(r1.image, degrees=10.0)
    # Expected accumulated = r2.affine @ r1.affine
    assert r1.affine is not None
    assert r2.affine is not None
    expected = r2.affine @ r1.affine

    pipeline = compose(rot15, rot10)
    result = pipeline(img)

    assert np.allclose(result.accumulated_affine, expected, atol=1e-6), (
        "accumulated affine must equal the matrix product of the two rotations"
    )


def test_compose_result_has_correct_attributes() -> None:
    """ComposedResult must expose .image and .accumulated_affine.

    # WHY: Downstream code (bbox_adjust) depends on these attribute names;
    # verifying them here catches any accidental renaming early.
    """
    from planproof.datagen.degradation.compose import ComposedResult, compose

    img = _make_image()
    pipeline = compose()
    result = pipeline(img)

    assert isinstance(result, ComposedResult)
    assert result.image is not None
    assert result.accumulated_affine is not None
    assert result.accumulated_affine.shape == (3, 3)
    assert result.accumulated_affine.dtype == np.float64


# ---------------------------------------------------------------------------
# Task 13 — load_preset()
# ---------------------------------------------------------------------------


def test_load_preset_moderate_scan() -> None:
    """load_preset for moderate_scan.yaml must return a callable pipeline.

    # WHY: Integration smoke test — confirms the YAML is parsed, names are
    # resolved via TRANSFORM_REGISTRY, and partial() params are applied.
    """
    from planproof.datagen.degradation.compose import load_preset

    preset_path = CONFIGS_DIR / "moderate_scan.yaml"
    assert preset_path.exists(), f"test fixture missing: {preset_path}"

    pipeline = load_preset(preset_path)
    assert callable(pipeline), "load_preset must return a callable"

    img = _make_image(height=100, width=120)
    result = pipeline(img)

    # The pipeline contains a rotation, so the affine must not be identity.
    assert not _is_identity(result.accumulated_affine), (
        "moderate_scan contains rotation — accumulated affine must differ from identity"
    )


def test_load_preset_clean() -> None:
    """clean.yaml has no transforms — image must be unchanged and affine must be identity.

    # WHY: The clean preset is the zero-degradation baseline used to isolate
    # extraction errors from imaging errors; it must not alter the document at all.
    """
    from planproof.datagen.degradation.compose import load_preset

    preset_path = CONFIGS_DIR / "clean.yaml"
    assert preset_path.exists(), f"test fixture missing: {preset_path}"

    pipeline = load_preset(preset_path)
    img = _make_image()
    result = pipeline(img)

    assert np.array_equal(result.image, img), (
        "clean preset must return the image completely unchanged"
    )
    assert _is_identity(result.accumulated_affine), (
        "clean preset must return identity affine (no geometric change)"
    )
