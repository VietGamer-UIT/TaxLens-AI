"""Tax Compliance Check Agent — example autonomous workflow (human must approve)."""

from __future__ import annotations

from typing import Any

from taxlens.agents.base import AgentResult, AuditAgent, record_agent_audit
from taxlens.masking import mask_sensitive_text
from taxlens.rag.pipeline import CitedAnswer, build_index_from_knowledge_dir, query_with_citations


class TaxComplianceAgent(AuditAgent):
    name = "TaxComplianceCheck"

    def __init__(self, index: Any | None = None) -> None:
        self._index = index

    def _ensure_index(self) -> Any:
        if self._index is None:
            self._index = build_index_from_knowledge_dir()
        return self._index

    def run(self, context: dict[str, Any]) -> AgentResult:
        """
        Workflow:
        1. Mask identifiers in free-text question.
        2. RAG query for legal grounding.
        3. Build reasoning steps and structured output (no final legal determination).
        """
        raw_q = str(context.get("question", ""))
        masked = mask_sensitive_text(raw_q)
        steps = [
            "Step 1: Mask customer names, tax IDs, bank accounts before LLM processing.",
            "Step 2: Retrieve Vietnam tax / IFRS sources via local vector index.",
            "Step 3: Synthesize answer with mandatory citation or 'Insufficient legal basis.'",
        ]
        try:
            idx = self._ensure_index()
            cited: CitedAnswer = query_with_citations(idx, masked.masked_text)
        except Exception as exc:  # noqa: BLE001 — surface local stack to logs in deployment
            err = f"{type(exc).__name__}: {exc}"
            steps.append(f"Step 4: RAG unavailable — {err}")
            result = AgentResult(
                agent_name=self.name,
                steps=steps,
                structured_output={
                    "masked_question": masked.masked_text,
                    "legal_answer": "Insufficient legal basis.",
                    "insufficient_legal_basis": True,
                    "sources": [],
                    "error": err,
                },
                confidence=0.2,
                requires_human_review=True,
                citations=[],
            )
            record_agent_audit(
                self.name,
                result,
                input_summary={"question_len": len(raw_q)},
                retrieved_doc_refs=[],
            )
            return result

        if cited.insufficient_legal_basis:
            steps.append("Step 4: No qualifying sources — block substantive compliance conclusion.")

        structured = {
            "masked_question": masked.masked_text,
            "legal_answer": cited.text,
            "insufficient_legal_basis": cited.insufficient_legal_basis,
            "sources": cited.source_nodes,
        }
        confidence = 0.35 if cited.insufficient_legal_basis else 0.72

        result = AgentResult(
            agent_name=self.name,
            steps=steps,
            structured_output=structured,
            confidence=confidence,
            requires_human_review=True,
            citations=cited.citations,
        )
        record_agent_audit(
            self.name,
            result,
            input_summary={"question_len": len(raw_q)},
            retrieved_doc_refs=cited.citations,
        )
        return result
