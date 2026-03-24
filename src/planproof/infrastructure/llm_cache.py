"""SQLite-backed deterministic LLM response cache.

Implements the ``ResponseCache`` Protocol from ``planproof.interfaces.cache``.

# WHY: LLM calls are expensive (~$0.03-0.10 each) and non-deterministic.
# Caching by (prompt_hash, doc_hash, model) makes runs reproducible during
# development, prevents redundant API spend when re-processing the same
# document, and enables offline development once responses are seeded.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class SQLiteLLMCache:
    """Content-addressed SQLite cache for LLM responses.

    # WHY keying strategy:
    #   - prompt_hash: captures the exact instruction/template sent to the LLM.
    #   - doc_hash: captures the document content being analysed, so the same
    #     prompt against a *different* document produces a separate entry.
    #   - model: different models produce different outputs even for the same
    #     input, so the model name is part of the composite key.
    #
    # WHY manual-only invalidation:
    #   There is no TTL or automatic eviction.  LLM responses for a given
    #   (prompt, document, model) triple are deterministic at temperature=0,
    #   so the cache should only be invalidated when the *prompt template*
    #   changes — which is a conscious developer action, not a time-based one.
    #   Developers clear the cache by deleting the SQLite file or specific rows.
    """

    def __init__(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        db_path = cache_dir / "llm_cache.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                prompt_hash TEXT,
                doc_hash    TEXT,
                model       TEXT,
                response    TEXT,
                created_at  TEXT,
                PRIMARY KEY (prompt_hash, doc_hash, model)
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _hash(text: str) -> str:
        """Return the SHA-256 hex digest of *text*."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(
        self, prompt_hash: str, doc_hash: str, model: str
    ) -> str | None:
        """Return cached response or ``None`` on miss."""
        cursor = self._conn.execute(
            "SELECT response FROM cache"
            " WHERE prompt_hash = ? AND doc_hash = ? AND model = ?",
            (prompt_hash, doc_hash, model),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def put(
        self,
        prompt_hash: str,
        doc_hash: str,
        model: str,
        response: str,
    ) -> None:
        """Store a response under the composite key."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO cache
            (prompt_hash, doc_hash, model, response, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prompt_hash, doc_hash, model, response, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
