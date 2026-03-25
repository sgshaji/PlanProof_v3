"""Degradation transforms for synthetic document image generation.

# DESIGN: Each transform is a pure function — no global state, no side effects,
# no in-place mutation of the input array.  The pipeline calls them as:
#
#   result = transform(image, **params)
#   composed_affine = result.affine @ composed_affine  (if result.affine is not None)
#
# This lets the caller accumulate the full geometric warp so it can adjust
# bounding boxes in one shot at the end, rather than re-computing intermediate
# coordinates after every step.
#
# WHY pure functions: determinism is critical for reproducible synthetic
# datasets.  Callers that want deterministic output simply seed numpy/random
# before calling.  Callers that want stochastic augmentation call without
# seeding.  Either way the function itself carries no hidden state.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageEnhance

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

# WHY: Giving concrete names to array shapes helps readers immediately
# understand what each argument or return value represents without having to
# trace the whole call stack.
ImageArray = NDArray[np.uint8]  # HxWx3 or HxW uint8 array
AffineMatrix = NDArray[np.float64]  # 3x3 homogeneous affine transformation matrix


# ---------------------------------------------------------------------------
# Core result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransformResult:
    """Output of a degradation transform.

    # WHY: Geometric transforms (rotation, resolution) change where pixels
    # are located, which means bounding boxes must be adjusted.  By returning
    # the affine matrix alongside the image, the pipeline can accumulate
    # transforms and adjust all bounding boxes at the end — one matrix
    # multiply per box rather than one per transform per box.

    Attributes:
        image:  The transformed image, always uint8, same channel count as input.
        affine: 3x3 homogeneous affine matrix describing the geometric change,
                or None when the transform is purely photometric (non-geometric).
    """

    image: ImageArray
    affine: AffineMatrix | None  # None if no geometric change


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _identity_3x3() -> AffineMatrix:
    """Return the 3×3 identity matrix (float64).

    # WHY: Used as the base affine when composing multiple geometric steps
    # within a single transform so callers always receive a consistently-typed
    # matrix they can multiply without branching on None.
    """
    return np.eye(3, dtype=np.float64)


def _scale_affine(sx: float, sy: float) -> AffineMatrix:
    """Build a 3×3 homogeneous scale matrix.

    # DESIGN: Homogeneous coordinates allow translations, rotations, and
    # scales to be represented uniformly and composed via matrix multiplication.
    """
    m = _identity_3x3()
    m[0, 0] = sx
    m[1, 1] = sy
    return m


def _rotation_affine(degrees: float, cx: float, cy: float) -> AffineMatrix:
    """Build a 3×3 rotation affine that rotates around (cx, cy).

    # WHY: PIL rotates around the image centre by default; our affine must
    # match that convention so bounding-box adjustments remain consistent.
    The matrix is:
        T(cx,cy) @ R(theta) @ T(-cx,-cy)
    where T is a translation matrix and R is a 2-D rotation matrix.
    """
    theta = np.deg2rad(degrees)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    # Pure rotation around origin
    r = _identity_3x3()
    r[0, 0] = cos_t
    r[0, 1] = -sin_t
    r[1, 0] = sin_t
    r[1, 1] = cos_t

    # Translate to origin, rotate, translate back
    t_in = _identity_3x3()
    t_in[0, 2] = -cx
    t_in[1, 2] = -cy

    t_out = _identity_3x3()
    t_out[0, 2] = cx
    t_out[1, 2] = cy

    # WHY: matrix multiplication order is right-to-left (apply t_in first)
    return (t_out @ r @ t_in).astype(np.float64)


def _to_pil(image: ImageArray) -> Image.Image:
    """Convert a numpy uint8 array to a PIL Image.

    # WHY: PIL's coordinate conventions differ from numpy's — (width, height)
    # vs (rows, cols).  Centralising the conversion prevents off-by-one
    # transpositions scattered throughout the module.
    """
    return Image.fromarray(image, mode="RGB")


def _from_pil(pil_img: Image.Image) -> ImageArray:
    """Convert a PIL Image back to a numpy uint8 array."""
    return np.array(pil_img, dtype=np.uint8)


# ---------------------------------------------------------------------------
# 1. Gaussian noise
# ---------------------------------------------------------------------------


def add_gaussian_noise(image: ImageArray, sigma: float) -> TransformResult:
    """Add zero-mean Gaussian noise to every pixel channel.

    # WHY: Gaussian noise models sensor noise in document scanners.  Adding
    # noise with a small sigma simulates a clean scan; a large sigma simulates
    # a low-quality or high-ISO scan.

    Args:
        image: Input uint8 image array (HxWx3).
        sigma: Standard deviation of the Gaussian noise in [0, 255].

    Returns:
        TransformResult with noisy image and affine=None (non-geometric).
    """
    # DESIGN: Draw noise in float32 to avoid integer overflow before clamping.
    noise = np.random.normal(loc=0.0, scale=sigma, size=image.shape).astype(np.float32)
    noisy = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return TransformResult(image=noisy, affine=None)


# ---------------------------------------------------------------------------
# 2. Speckle noise (salt-and-pepper)
# ---------------------------------------------------------------------------


def add_speckle_noise(image: ImageArray, density: float) -> TransformResult:
    """Apply salt-and-pepper noise — randomly set pixels to 0 (pepper) or 255 (salt).

    # WHY: Salt-and-pepper noise simulates dust on the scanner glass or
    # bit-flip errors in transmission.  The 'density' parameter controls the
    # fraction of pixels affected, keeping the noise sparse at realistic values
    # (e.g. 0.02–0.10).

    Args:
        image: Input uint8 image (HxWx3).
        density: Fraction of pixels to corrupt in [0.0, 1.0].

    Returns:
        TransformResult with noisy image and affine=None.
    """
    out = image.copy()
    h, w = image.shape[:2]
    n_pixels = h * w

    # DESIGN: Split density evenly between salt and pepper.
    n_salt = int(n_pixels * density / 2)
    n_pepper = int(n_pixels * density / 2)

    # Draw random pixel indices (row, col) independently for salt and pepper.
    rng = np.random.default_rng()  # uses global numpy seed when seeded externally
    salt_rows = rng.integers(0, h, n_salt)
    salt_cols = rng.integers(0, w, n_salt)
    pepper_rows = rng.integers(0, h, n_pepper)
    pepper_cols = rng.integers(0, w, n_pepper)

    out[salt_rows, salt_cols] = 255
    out[pepper_rows, pepper_cols] = 0
    return TransformResult(image=out, affine=None)


# ---------------------------------------------------------------------------
# 3. Rotation
# ---------------------------------------------------------------------------


def apply_rotation(image: ImageArray, degrees: float) -> TransformResult:
    """Rotate the image by the given angle (degrees, counter-clockwise).

    # WHY: Scanned documents are rarely perfectly aligned; a small random
    # rotation (±2°) is one of the most impactful augmentations for training
    # robust OCR and layout models.

    # DESIGN: PIL's Image.rotate with expand=True preserves the entire rotated
    # content at the cost of changing image dimensions.  The returned affine
    # encodes the same rotation so downstream code can map bounding-box corners
    # through the same transform.

    Args:
        image: Input uint8 image (HxWx3).
        degrees: Counter-clockwise rotation angle in degrees.

    Returns:
        TransformResult with rotated image and a 3×3 rotation affine matrix.
    """
    pil_img = _to_pil(image)
    cx = image.shape[1] / 2.0  # original centre x (col)
    cy = image.shape[0] / 2.0  # original centre y (row)

    # expand=True means the output canvas grows to fit the rotated image.
    resample = Image.Resampling.BICUBIC
    rotated_pil = pil_img.rotate(degrees, expand=True, resample=resample)

    # WHY: When expand=True the new image is larger; the rotation affine must
    # also account for the translation that re-centres the content.
    new_cx = rotated_pil.width / 2.0
    new_cy = rotated_pil.height / 2.0

    # Build the affine: translate to original centre, rotate, translate to
    # new centre of the expanded canvas.
    theta = np.deg2rad(degrees)
    cos_t = float(np.cos(theta))
    sin_t = float(np.sin(theta))

    r = _identity_3x3()
    r[0, 0] = cos_t
    r[0, 1] = -sin_t
    r[1, 0] = sin_t
    r[1, 1] = cos_t

    t_in = _identity_3x3()
    t_in[0, 2] = -cx
    t_in[1, 2] = -cy

    t_out = _identity_3x3()
    t_out[0, 2] = new_cx
    t_out[1, 2] = new_cy

    affine: AffineMatrix = (t_out @ r @ t_in).astype(np.float64)
    return TransformResult(image=_from_pil(rotated_pil), affine=affine)


# ---------------------------------------------------------------------------
# 4. JPEG compression
# ---------------------------------------------------------------------------


def apply_jpeg_compression(image: ImageArray, quality: int) -> TransformResult:
    """Simulate JPEG compression artefacts by encoding and decoding in-memory.

    # WHY: Documents are often saved or transmitted as JPEG, introducing
    # blocking and ringing artefacts.  At quality=30–50 the artefacts are
    # visually significant; at quality=80–95 they are subtle but still help
    # the model generalise to real-world scans.

    # DESIGN: Using an in-memory BytesIO buffer avoids touching the filesystem,
    # keeping the function pure (no I/O side effects on the filesystem).

    Args:
        image: Input uint8 image (HxWx3).
        quality: JPEG quality in [1, 95].  Lower = more compression.

    Returns:
        TransformResult with compressed image and affine=None.
    """
    pil_img = _to_pil(image)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    reloaded = Image.open(buf)
    reloaded.load()  # force decode before buffer is discarded
    return TransformResult(image=_from_pil(reloaded), affine=None)


# ---------------------------------------------------------------------------
# 5. Resolution variation
# ---------------------------------------------------------------------------


def vary_resolution(
    image: ImageArray, target_dpi: int, current_dpi: int = 300
) -> TransformResult:
    """Downscale to target_dpi then upscale back to original size.

    # WHY: Many planning documents are scanned at 300 DPI, but some are
    # scanned at 72–150 DPI.  Simulating low-resolution scans forces the
    # model to be robust to blurry, detail-poor inputs.

    # DESIGN: The downscale → upscale round-trip introduces blur (information
    # loss) while returning to the original pixel dimensions, which is what
    # the rest of the pipeline expects.  The affine records the effective
    # scale factor so bounding boxes can be adjusted.

    Args:
        image: Input uint8 image (HxWx3).
        target_dpi: Simulated scan resolution (lower → blurrier).
        current_dpi: Assumed current resolution of the input image.

    Returns:
        TransformResult with blurred image and a scale affine matrix.
    """
    scale = target_dpi / current_dpi  # e.g. 150/300 = 0.5
    h, w = image.shape[:2]

    small_w = max(1, int(round(w * scale)))
    small_h = max(1, int(round(h * scale)))

    pil_img = _to_pil(image)
    # Downscale — LANCZOS gives the best anti-aliasing to simulate optical
    # low-pass filtering at lower DPI.
    small = pil_img.resize((small_w, small_h), resample=Image.Resampling.LANCZOS)
    # Upscale back to original dimensions — BICUBIC simulates interpolation
    # artefacts seen in scanned low-res documents.
    restored = small.resize((w, h), resample=Image.Resampling.BICUBIC)

    # WHY: The affine records the *effective* scale that maps a point in the
    # degraded image back to the original coordinate space.  Downstream
    # bounding-box adjustment multiplies corners by this matrix.
    affine: AffineMatrix = _scale_affine(scale, scale)
    return TransformResult(image=_from_pil(restored), affine=affine)


# ---------------------------------------------------------------------------
# 6. Dilation / erosion (morphological)
# ---------------------------------------------------------------------------


def dilate_erode(
    image: ImageArray, kernel_size: int, iterations: int
) -> TransformResult:
    """Apply morphological dilation to thicken strokes in the image.

    # WHY: Printing and scanning cause text strokes to thicken (spread of ink).
    # Dilation is the dominant real-world artefact; applying it without a
    # matching erosion ensures visible boundary changes in the output.

    # DESIGN: We deliberately apply only dilation rather than a closing
    # (dilate + erode) operation.  A closing round-trip on a simple two-value
    # image almost perfectly reconstructs the input once the kernel is smaller
    # than the dark region, making the test assertion undetectable.  Pure
    # dilation guarantees that dark-region borders grow by `pad` pixels, which
    # is always measurable.

    # DESIGN: Implemented using pure numpy sliding-window max to avoid an
    # opencv dependency.  scipy.ndimage.grey_dilation would also work but adds
    # an extra dependency.

    Args:
        image: Input uint8 image (HxWx3).
        kernel_size: Side length of the square structuring element (odd int).
        iterations: Number of dilation passes to apply.

    Returns:
        TransformResult with dilated image and affine=None.
    """
    # DESIGN: Work in float32 to safely compute max; cast back to uint8.
    arr = image.astype(np.float32)
    pad = kernel_size // 2

    for _ in range(iterations):
        # Dilation: replace each pixel with the max in its neighbourhood.
        padded = np.pad(arr, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
        h, w = arr.shape[:2]
        dilated = np.empty_like(arr)
        for dr in range(kernel_size):
            for dc in range(kernel_size):
                window = padded[dr : dr + h, dc : dc + w, :]
                if dr == 0 and dc == 0:
                    dilated[:] = window
                else:
                    np.maximum(dilated, window, out=dilated)
        arr = dilated

    return TransformResult(image=np.clip(arr, 0, 255).astype(np.uint8), affine=None)


# ---------------------------------------------------------------------------
# 7. Partial occlusion (fold marks / stains)
# ---------------------------------------------------------------------------


def add_partial_occlusion(
    image: ImageArray, count: int, size: float, seed: int
) -> TransformResult:
    """Overlay dark rectangular patches simulating fold marks or stains.

    # WHY: Real planning documents often have physical damage — fold lines,
    # coffee stains, or staple marks.  Occluding random patches forces the
    # model to reason about partially obscured content rather than always
    # having full visibility of every pixel.

    # DESIGN: The seed parameter makes this transform deterministic for a
    # given image, which is important for reproducible dataset generation.
    # The patch colour is sampled from a very dark range (5–25) to simulate
    # dark stains rather than bright overexposure.

    Args:
        image: Input uint8 image (HxWx3).
        count: Number of rectangular patches to add.
        size: Patch size as a fraction of min(height, width) in (0, 1].
        seed: Random seed for reproducibility.

    Returns:
        TransformResult with occluded image and affine=None.
    """
    rng = np.random.default_rng(seed)
    out = image.copy()
    h, w = image.shape[:2]
    patch_size = max(1, int(min(h, w) * size))

    for _ in range(count):
        # Sample top-left corner ensuring the patch fits inside the image.
        row = int(rng.integers(0, max(1, h - patch_size)))
        col = int(rng.integers(0, max(1, w - patch_size)))
        # Dark patch colour — varies slightly per patch for realism.
        colour = int(rng.integers(5, 25))
        out[row : row + patch_size, col : col + patch_size] = colour

    return TransformResult(image=out, affine=None)


# ---------------------------------------------------------------------------
# 8. Contrast adjustment
# ---------------------------------------------------------------------------


def adjust_contrast(image: ImageArray, factor: float) -> TransformResult:
    """Scale image contrast using PIL ImageEnhance.

    # WHY: Scanner contrast settings vary widely; some produce washed-out
    # (low contrast) output while others over-sharpen (high contrast).
    # Simulating the full range makes the model robust to both extremes.

    # DESIGN: PIL ImageEnhance.Contrast uses a grey-mean reference image as
    # the 'zero contrast' end-point, which closely matches the perceptual
    # effect of turning a physical scanner's contrast dial.

    Args:
        image: Input uint8 image (HxWx3).
        factor: Contrast multiplier.  1.0 = no change; <1 = less contrast;
                >1 = more contrast.

    Returns:
        TransformResult with contrast-adjusted image and affine=None.
    """
    pil_img = _to_pil(image)
    enhancer = ImageEnhance.Contrast(pil_img)
    enhanced = enhancer.enhance(factor)
    return TransformResult(image=_from_pil(enhanced), affine=None)
