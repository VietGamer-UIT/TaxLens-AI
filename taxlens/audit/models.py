"""Audit trail data structures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditRecord(BaseModel):
    """Single immutable audit event."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    ts: datetime = Field(default_factory=utc_now)
    actor: str = "system"
    action: str
    input_summary: dict[str, Any] = Field(default_factory=dict)
    model_decision: str | None = None
    retrieved_doc_refs: list[str] = Field(default_factory=list)
    reasoning_steps: list[str] = Field(default_factory=list)
    confidence: float | None = None
    requires_human_review: bool = True
    payload_redacted: dict[str, Any] = Field(default_factory=dict)
