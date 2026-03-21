"""Agent workflow base: structured steps + tool hooks + audit."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from taxlens.audit.logger import append_audit
from taxlens.audit.models import AuditRecord


class AgentResult(BaseModel):
    agent_name: str
    steps: list[str] = Field(default_factory=list)
    structured_output: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    requires_human_review: bool = True
    citations: list[str] = Field(default_factory=list)


class AuditAgent(ABC):
    name: str

    @abstractmethod
    def run(self, context: dict[str, Any]) -> AgentResult:
        """Execute workflow; must not finalize compliance decisions."""


def record_agent_audit(
    agent: str,
    result: AgentResult,
    *,
    actor: str = "system",
    input_summary: dict[str, Any] | None = None,
    retrieved_doc_refs: list[str] | None = None,
) -> None:
    append_audit(
        AuditRecord(
            actor=actor,
            action=f"agent:{agent}",
            input_summary=input_summary or {},
            model_decision=str(result.structured_output)[:2000],
            retrieved_doc_refs=retrieved_doc_refs or result.citations,
            reasoning_steps=result.steps,
            confidence=result.confidence,
            requires_human_review=result.requires_human_review,
        )
    )
