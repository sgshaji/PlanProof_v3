"""Compose utility and YAML preset loader for degradation pipelines.

# DESIGN: This module is the glue layer between individual transform functions
# and the rest of the data-generation pipeline.  `compose()` is a pure
# higher-order function — it takes callables and returns a new callable; it
# never mutates its arguments or any global state.  `load_preset()` builds on
# `compose()` by resolving YAML-declared transform names through a static
# registry, applying `functools.partial` to bind the YAML-provided parameters,
# and handing the resulting list of bound functions to `compose()`.
#
# WHY pure FP: determinism is critical for reproducible synthetic datasets.
# compose() is idempotent — calling it twice with the same functions always
# returns two equivalent (but distinct) pipeline objects.  There are no hidden
# queues, no shared mutable lists, no class-level caches.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import cast

import numpy as np
import yaml

from planproof.datagen.degradation import transforms
from planproof.datagen.degradation.transforms import AffineMatrix, ImageArray

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

# WHY: Giving a name to the "un-parameterised" transform signature makes
# the compose() signature self-documenting.  A DegradeFn accepts only an
# image and returns a TransformResult; params are already bound via partial().
DegradeFn = Callable[[ImageArray], transforms.TransformResult]


# ---------------------------------------------------------------------------
# ComposedResult — output of a composed pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComposedResult:
    """Result of applying a composed degradation pipeline.

    # WHY: A dedicated result type (rather than reusing TransformResult)
    # communicates that the affine here is the *accumulated* product of all
    # geometric transforms in the pipeline, not the affine of a single step.
    # Downstream code (bbox_adjust) only needs the accumulated form.

    Attributes:
        image:             The final degraded image, uint8.
        accumulated_affine: Product of all geometric affines encountered during
                            the pipeline run.  Identity matrix when no geometric
                            transforms were applied.
    """

    image: ImageArray
    accumulated_affine: AffineMatrix


# ---------------------------------------------------------------------------
# TRANSFORM_REGISTRY — maps YAML short names to transform functions
# ---------------------------------------------------------------------------

# DESIGN: The registry intentionally supports both the full function name
# (e.g. "add_gaussian_noise") and a common short alias (e.g. "gaussian_noise")
# so that YAML presets can use the more human-friendly short form without
# breaking any callers that use the full programmatic name.
#
# WHY a plain dict: a dict is the simplest, most readable registry.  Adding
# a new transform is one line — no base-class boilerplate or decorator magic.
TRANSFORM_REGISTRY: dict[str, Callable[..., transforms.TransformResult]] = {
    # Full programmatic names (matches function names in transforms.py)
    "add_gaussian_noise": transforms.add_gaussian_noise,
    "add_speckle_noise": transforms.add_speckle_noise,
    "apply_rotation": transforms.apply_rotation,
    "apply_jpeg_compression": transforms.apply_jpeg_compression,
    "vary_resolution": transforms.vary_resolution,
    "dilate_erode": transforms.dilate_erode,
    "add_partial_occlusion": transforms.add_partial_occlusion,
    "adjust_contrast": transforms.adjust_contrast,
    # Short aliases used in YAML preset files (e.g. moderate_scan.yaml)
    "gaussian_noise": transforms.add_gaussian_noise,
    "speckle_noise": transforms.add_speckle_noise,
    "rotation": transforms.apply_rotation,
    "jpeg_compression": transforms.apply_jpeg_compression,
    "resolution": transforms.vary_resolution,
    "morphology": transforms.dilate_erode,
    "occlusion": transforms.add_partial_occlusion,
    "contrast": transforms.adjust_contrast,
}


# ---------------------------------------------------------------------------
# compose() — pure higher-order function
# ---------------------------------------------------------------------------


def compose(*fns: DegradeFn) -> Callable[[ImageArray], ComposedResult]:
    """Return a new pipeline function that applies *fns* in sequence.

    # DESIGN: Each fn in *fns* is a DegradeFn — a callable that accepts only
    # an ImageArray and returns a TransformResult.  Callers must bind any
    # required parameters (e.g. sigma, quality) using functools.partial before
    # passing the fn here.  This keeps compose() agnostic about parameter names
    # and types.
    #
    # Affine accumulation: the composed function starts with a 3×3 identity
    # matrix and right-multiplies each non-None affine returned by the
    # individual transforms.  The product order ensures that the first
    # transform's affine is applied first when projecting a point:
    #
    #   p' = (A_n @ ... @ A_2 @ A_1) @ p
    #
    # WHY accumulated right-multiplication: the affines describe how pixels
    # move in the image coordinate space.  Composing them as a chain lets
    # bbox_adjust project original bounding-box corners through the full
    # warp in a single matrix–vector multiply rather than iterating through
    # every transform step.

    Args:
        *fns: Zero or more DegradeFn callables (image → TransformResult).

    Returns:
        A new callable (ImageArray → ComposedResult).  Calling the returned
        function never mutates *fns* or any external state.
    """

    def _pipeline(image: ImageArray) -> ComposedResult:
        # WHY: Start with identity so the accumulation loop has no special
        # case for the first transform.
        accumulated: AffineMatrix = np.eye(3, dtype=np.float64)
        current_image: ImageArray = image

        for fn in fns:
            result = fn(current_image)
            current_image = result.image
            if result.affine is not None:
                # WHY: Right-multiply so the first transform's affine is
                # innermost (applied first to a point vector).
                accumulated = result.affine @ accumulated

        return ComposedResult(image=current_image, accumulated_affine=accumulated)

    return _pipeline


# ---------------------------------------------------------------------------
# load_preset() — YAML preset loader
# ---------------------------------------------------------------------------


def load_preset(yaml_path: Path) -> Callable[[ImageArray], ComposedResult]:
    """Load a degradation preset YAML and return a ready-to-call pipeline.

    # DESIGN: The function is intentionally side-effect-free after the file
    # is read.  File I/O happens once at load time; the returned pipeline is
    # a pure function that can be called any number of times.
    #
    # WHY YAML: Human-readable presets let researchers tune degradation
    # settings without touching Python code.  The registry pattern prevents
    # arbitrary code execution that would result from eval()-based approaches.

    YAML schema::

        preset_id: <str>
        transforms:
          - name: <registry key>
            params:
              <key>: <value>
              ...

    Args:
        yaml_path: Path to a ``*.yaml`` preset file.

    Returns:
        A callable (ImageArray → ComposedResult) equivalent to calling
        compose() with the bound transform functions specified in the YAML.

    Raises:
        KeyError: If a transform name in the YAML is not in TRANSFORM_REGISTRY.
        FileNotFoundError: If yaml_path does not exist.
    """
    raw = yaml_path.read_text(encoding="utf-8")
    preset = yaml.safe_load(raw)

    # WHY: Treat a missing or empty transforms list as an empty pipeline so
    # the clean preset (transforms: []) works without special handling.
    transform_specs: list[dict[str, object]] = preset.get("transforms") or []

    bound_fns: list[DegradeFn] = []
    for spec in transform_specs:
        name = str(spec["name"])
        raw_params = spec.get("params") or {}
        params: dict[str, object] = dict(
            cast(dict[str, object], raw_params)
        )

        if name not in TRANSFORM_REGISTRY:
            raise KeyError(
                f"Unknown transform '{name}' in preset '{yaml_path}'. "
                f"Available: {sorted(TRANSFORM_REGISTRY)}"
            )

        # DESIGN: partial() binds the YAML params to the base transform
        # function, producing a DegradeFn (image → TransformResult) that
        # compose() can call without knowing the param names.
        #
        # WHY not a lambda: partial() is serialisable (useful for multiprocessing)
        # and has a clear repr that shows the wrapped function and params,
        # which helps debugging.
        fn = partial(TRANSFORM_REGISTRY[name], **params)
        bound_fns.append(fn)

    return compose(*bound_fns)
