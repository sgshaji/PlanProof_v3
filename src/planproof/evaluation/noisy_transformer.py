"""Noisy entity transformer for extraction-quality robustness experiments.

Applies controlled degradation to a list of ExtractedEntity objects to simulate
imperfect extraction quality. Used by the robustness runner to generate
robustness curves showing how the system degrades under noisy extraction.

Each transformer operates on NEW entity instances — originals are never mutated.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from planproof.schemas.entities import ExtractedEntity


@dataclass
class DegradationConfig:
    """Configuration for one level of extraction degradation.

    All parameters default to 0.0 (identity transform / oracle quality).
    """

    # Gaussian noise std as a fraction of the original numeric value.
    # e.g. 0.05 means ±5% noise on average.
    value_noise_pct: float = 0.0

    # Fraction of entities to randomly remove.
    # e.g. 0.10 removes ~10% of entities.
    entity_dropout_pct: float = 0.0

    # Gaussian noise std added to confidence scores.
    # Result is clamped to [0.01, 1.0].
    confidence_noise_std: float = 0.0

    # Fraction of entities whose attribute names are randomly swapped.
    # Simulates extraction misattribution.
    attribute_swap_pct: float = 0.0

    def label(self) -> str:
        """Short human-readable label for this config."""
        return (
            f"v{self.value_noise_pct:.0%}"
            f"_d{self.entity_dropout_pct:.0%}"
            f"_c{self.confidence_noise_std:.0%}"
            f"_s{self.attribute_swap_pct:.0%}"
        )


class NoisyEntityTransformer:
    """Applies controlled degradation to extracted entities.

    All four degradation modes are applied in order:
    1. Attribute swap (before dropout so swaps affect the full set)
    2. Entity dropout
    3. Value noise
    4. Confidence noise

    Parameters
    ----------
    config:
        Degradation parameters.
    seed:
        Random seed for reproducibility.
    """

    def __init__(self, config: DegradationConfig, seed: int = 42) -> None:
        self._config = config
        self._rng = random.Random(seed)
        # Use a separate Random for numpy-style Gaussian via the Box-Muller method
        # so we don't require numpy as a hard dependency (though it is available).
        import numpy as np

        self._np_rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transform(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Apply degradation and return a new list of (new) entity instances."""
        if not entities:
            return []

        result = list(entities)  # shallow copy — we'll replace elements below

        # Step 1: attribute swap (operates on full set before dropout)
        result = self._apply_attribute_swap(result)

        # Step 2: entity dropout
        result = self._apply_dropout(result)

        # Step 3: value noise
        result = self._apply_value_noise(result)

        # Step 4: confidence noise
        result = self._apply_confidence_noise(result)

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clone(self, entity: ExtractedEntity, **overrides: Any) -> ExtractedEntity:
        """Return a new ExtractedEntity with selected fields overridden."""
        data = entity.model_dump()
        data.update(overrides)
        return ExtractedEntity(**data)

    def _apply_dropout(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Randomly remove entity_dropout_pct fraction of entities."""
        pct = self._config.entity_dropout_pct
        if pct <= 0.0:
            return entities
        # Shuffle indices and drop the first k
        n = len(entities)
        n_drop = min(round(pct * n), n)
        if n_drop == 0:
            return entities
        indices_to_drop = set(self._rng.sample(range(n), n_drop))
        return [e for i, e in enumerate(entities) if i not in indices_to_drop]

    def _apply_value_noise(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Add Gaussian noise to numeric entity values."""
        noise_pct = self._config.value_noise_pct
        if noise_pct <= 0.0:
            return entities

        result: list[ExtractedEntity] = []
        for entity in entities:
            try:
                original = float(entity.value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                # Non-numeric value — leave unchanged
                result.append(entity)
                continue

            noise_factor = float(self._np_rng.normal(0.0, noise_pct))
            noisy_value = original * (1.0 + noise_factor)
            # Clamp to a small positive value — measurements must be > 0
            noisy_value = max(noisy_value, 1e-6)
            result.append(self._clone(entity, value=round(noisy_value, 6)))

        return result

    def _apply_confidence_noise(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Add Gaussian noise to confidence scores and clamp to [0.01, 1.0]."""
        noise_std = self._config.confidence_noise_std
        if noise_std <= 0.0:
            return entities

        result: list[ExtractedEntity] = []
        for entity in entities:
            noise = float(self._np_rng.normal(0.0, noise_std))
            new_conf = float(entity.confidence) + noise
            new_conf = max(0.01, min(1.0, new_conf))
            result.append(self._clone(entity, confidence=round(new_conf, 6)))

        return result

    def _apply_attribute_swap(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Randomly swap attribute names between pairs of entities.

        Only entities that have a non-None attribute field are eligible for
        swapping. Swaps are done in pairs so the total number of entities is
        unchanged.
        """
        swap_pct = self._config.attribute_swap_pct
        if swap_pct <= 0.0:
            return entities

        # Find indices of entities with non-None attributes
        eligible_indices = [i for i, e in enumerate(entities) if e.attribute is not None]
        n_eligible = len(eligible_indices)
        if n_eligible < 2:
            return entities

        n_to_swap = min(round(swap_pct * n_eligible), n_eligible)
        # Make it even so we can pair them up
        if n_to_swap % 2 != 0:
            n_to_swap = max(0, n_to_swap - 1)
        if n_to_swap == 0:
            return entities

        swap_indices = self._rng.sample(eligible_indices, n_to_swap)

        # Clone all entities first (to avoid mutating originals)
        result = list(entities)

        # Swap attribute names in pairs
        for i in range(0, n_to_swap, 2):
            idx_a = swap_indices[i]
            idx_b = swap_indices[i + 1]
            attr_a = entities[idx_a].attribute
            attr_b = entities[idx_b].attribute
            result[idx_a] = self._clone(entities[idx_a], attribute=attr_b)
            result[idx_b] = self._clone(entities[idx_b], attribute=attr_a)

        return result
