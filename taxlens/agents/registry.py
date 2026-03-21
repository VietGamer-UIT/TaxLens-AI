"""Registered agent stubs — workflows to be expanded with tools (RAG, OCR, ERP)."""

from __future__ import annotations

from typing import Any

from taxlens.agents.base import AgentResult, AuditAgent, record_agent_audit


class BankReconciliationAgent(AuditAgent):
    name = "BankReconciliation"

    def run(self, context: dict[str, Any]) -> AgentResult:
        steps = [
            "Step 1: Ingest bank statement lines (on-premise file upload).",
            "Step 2: Match to GL by amount/date/reference.",
            "Step 3: Flag unmatched or duplicate matches for human review.",
        ]
        result = AgentResult(
            agent_name=self.name,
            steps=steps,
            structured_output={"matches": [], "unmatched": context.get("preview", [])},
            confidence=0.5,
            requires_human_review=True,
        )
        record_agent_audit(self.name, result, input_summary={"keys": list(context.keys())})
        return result


class TransferPricingAgent(AuditAgent):
    name = "TransferPricingAnalysis"

    def run(self, context: dict[str, Any]) -> AgentResult:
        steps = [
            "Step 1: Load related-party transaction list.",
            "Step 2: Benchmark margins (local comparable set — to be configured).",
            "Step 3: Rank by deviation from arm's length range.",
        ]
        result = AgentResult(
            agent_name=self.name,
            steps=steps,
            structured_output={"related_party_tx": context.get("tx", [])},
            confidence=0.45,
            requires_human_review=True,
        )
        record_agent_audit(self.name, result, input_summary={"keys": list(context.keys())})
        return result


class AuditReportDraftAgent(AuditAgent):
    name = "AuditReportDrafting"

    def run(self, context: dict[str, Any]) -> AgentResult:
        steps = [
            "Step 1: Aggregate findings from risk engine and agents.",
            "Step 2: RAG for disclosure wording with citations.",
            "Step 3: Emit draft sections marked DRAFT — human edits required.",
        ]
        result = AgentResult(
            agent_name=self.name,
            steps=steps,
            structured_output={"draft_sections": context.get("sections", [])},
            confidence=0.4,
            requires_human_review=True,
        )
        record_agent_audit(self.name, result, input_summary={"keys": list(context.keys())})
        return result
