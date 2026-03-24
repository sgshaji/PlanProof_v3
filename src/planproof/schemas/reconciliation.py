"""Schemas for evidence reconciliation across multiple document sources.

When the same attribute (e.g. site area) appears in multiple documents,
the reconciliation layer determines whether those sources agree, conflict,
or whether evidence is missing entirely.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from planproof.schemas.entities import ExtractedEntity


class ReconciliationStatus(StrEnum):
    """Outcome of comparing evidence across sources for a single attribute."""

    AGREED = "AGREED"
    CONFLICTING = "CONFLICTING"
    # WHY: SINGLE_SOURCE is distinct from AGREED — a value corroborated by
    # multiple documents carries more weight than one seen only once.
    SINGLE_SOURCE = "SINGLE_SOURCE"
    MISSING = "MISSING"


class ReconciledEvidence(BaseModel):
    """Result of reconciling all evidence for a single attribute.

    Aggregates every ExtractedEntity that speaks to this attribute and
    records whether they agree, conflict, or are absent.
    """

    attribute: str
    status: ReconciliationStatus
    best_value: Any | None = None
    sources: list[ExtractedEntity]
    conflict_details: str | None = None

    model_config = {"from_attributes": True}
