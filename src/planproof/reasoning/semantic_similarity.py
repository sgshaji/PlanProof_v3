"""Embedding-based semantic similarity for attribute matching.

Computes cosine similarity between attribute name strings using sentence
embeddings.  This supports SABLE Step 3 (semantic relevance filtering) —
see docs/SABLE_ALGORITHM.md section 3.2, Step 3.

Design decisions:
- Graceful fallback to difflib string matching when sentence-transformers
  is not installed.  This keeps the test suite runnable without heavyweight
  ML dependencies.
- Results are cached per (attr_a, attr_b) pair — attribute vocabularies are
  small so the cache stays bounded.
- No LLM calls, no API dependency, no circular dependency with extraction.
"""
from __future__ import annotations

from difflib import SequenceMatcher


class SemanticSimilarity:
    """Compute cosine similarity between attribute names using sentence embeddings.

    Uses ``sentence-transformers`` for deterministic, local embedding computation.
    Falls back to normalised string matching (difflib) when the library is
    unavailable.

    Parameters
    ----------
    model_name:
        Hugging Face model identifier for the sentence-transformer model.
        Default ``all-MiniLM-L6-v2`` — 80 MB, fast, deterministic.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        # Try importing sentence-transformers; fall back to basic string matching
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

            self._model = SentenceTransformer(model_name)
            self._use_embeddings = True
        except ImportError:
            self._model = None
            self._use_embeddings = False

        self._cache: dict[tuple[str, str], float] = {}

    def similarity(self, attr_a: str | None, attr_b: str | None) -> float:
        """Compute semantic similarity between two attribute names.

        Implements SABLE Step 3:
            r_i = cosine_similarity(embed(e_i.attribute), embed(R_j.attribute))

        Returns a float in [0, 1].  Falls back to normalised string matching
        when sentence-transformers is not installed.

        Parameters
        ----------
        attr_a:
            First attribute name (e.g. from an extracted entity).
        attr_b:
            Second attribute name (e.g. from a rule requirement).

        Returns
        -------
        float:
            Cosine similarity clamped to [0, 1].  Returns 0.0 when either
            input is ``None``.
        """
        if attr_a is None or attr_b is None:
            return 0.0

        # Exact match — fast path
        if attr_a == attr_b:
            return 1.0

        key = (attr_a, attr_b)
        if key in self._cache:
            return self._cache[key]

        if self._use_embeddings:
            sim = self._embedding_similarity(attr_a, attr_b)
        else:
            sim = self._fallback_similarity(attr_a, attr_b)

        self._cache[key] = sim
        return sim

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _embedding_similarity(self, attr_a: str, attr_b: str) -> float:
        """Cosine similarity via sentence-transformer embeddings."""
        assert self._model is not None  # guaranteed by _use_embeddings check
        embeddings = self._model.encode([attr_a, attr_b])
        dot = sum(a * b for a, b in zip(embeddings[0], embeddings[1]))
        norm_a = sum(a * a for a in embeddings[0]) ** 0.5
        norm_b = sum(b * b for b in embeddings[1]) ** 0.5
        sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
        return max(0.0, min(1.0, float(sim)))

    @staticmethod
    def _fallback_similarity(attr_a: str, attr_b: str) -> float:
        """Normalised string matching fallback when embeddings are unavailable.

        Heuristic tiers:
        1. Case-insensitive exact match → 1.0
        2. Substring containment → 0.8
        3. SequenceMatcher ratio → [0, 1]
        """
        a_lower = attr_a.lower().replace("_", " ")
        b_lower = attr_b.lower().replace("_", " ")

        if a_lower == b_lower:
            return 1.0
        if a_lower in b_lower or b_lower in a_lower:
            return 0.8

        return SequenceMatcher(None, a_lower, b_lower).ratio()
