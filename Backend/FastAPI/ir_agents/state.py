# =============================================================================
# TaxLens-AI :: IR Agent State Schema
# =============================================================================
# Defines the shared typed state object passed between all LangGraph nodes.
#
# Design principles:
#   - TypedDict for LangGraph compatibility (StateGraph requires TypedDict).
#   - Every field is annotated with its purpose for hackathon judging clarity.
#   - Supports SANS FIND EVIL criterion: full audit trail via error_log.
#   - Supports Splunk Agentic Ops criterion: iteration guards prevent runaway.
# =============================================================================

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class IRAgentState(TypedDict, total=False):
    """
    Shared state object for the TaxLens-AI LangGraph workflow.

    Lifecycle:
        1. Initialised by the caller with incident_id + evidence_paths.
        2. Supervisor sets current_agent and routes to sub-agents.
        3. Each sub-agent writes its report to the corresponding *_findings key.
        4. Supervisor reads all *_findings and writes supervisor_report.
        5. Graph terminates when all reports are collected OR iteration_count
           exceeds MAX_ITERATIONS (global guard = 15).
    """

    # ------------------------------------------------------------------
    # Core identification
    # ------------------------------------------------------------------
    incident_id: str
    """Unique incident identifier (e.g. 'IR-2024-0047').  Never mutated."""

    # ------------------------------------------------------------------
    # LangChain / LangGraph message history (used by LLM nodes)
    # ------------------------------------------------------------------
    messages: list[dict[str, Any]]
    """
    Conversation-style message list:
        [{"role": "system"|"human"|"assistant", "content": "..."}]
    Agents append their reasoning steps here for a full audit trail.
    """

    # ------------------------------------------------------------------
    # Evidence inputs
    # ------------------------------------------------------------------
    evidence_paths: list[str]
    """
    Absolute paths to evidence artefacts supplied at incident intake.
    Examples: ["/evidence/mem.raw", "/evidence/disk.E01", "/evidence/fw.pcap"]
    """

    # ------------------------------------------------------------------
    # Routing control
    # ------------------------------------------------------------------
    current_agent: str
    """
    Name of the agent node currently executing.
    Set by Supervisor before routing; used for logging and conditional edges.
    Values: "forensics_agent" | "network_agent" | "database_agent" | "supervisor"
    """

    # ------------------------------------------------------------------
    # Sub-agent findings  (written by each specialist agent)
    # ------------------------------------------------------------------
    forensics_findings: Optional[dict[str, Any]]
    """
    Output from ForensicsAgent.
    Schema: {"status": "ok"|"error", "timeline": [...], "processes": [...], ...}
    """

    network_findings: Optional[dict[str, Any]]
    """
    Output from NetworkAgent.
    Schema: {"status": "ok"|"error", "notable_events": [...], "c2_connections": [...], ...}
    """

    database_findings: Optional[dict[str, Any]]
    """
    Output from DatabaseAgent (threat intel enrichment).
    Schema: {"status": "ok"|"error", "ioc_verdicts": [...], ...}
    """

    # ------------------------------------------------------------------
    # Self-correction mechanism (SANS criterion: resilience)
    # ------------------------------------------------------------------
    error_log: list[dict[str, Any]]
    """
    Accumulated list of structured error records.  Each sub-agent appends here
    when it catches a bad response, parse error, or MCP tool failure.
    Schema per entry:
        {
          "agent":      str,        # which agent caught the error
          "tool":       str,        # MCP tool name that errored
          "attempt":    int,        # 1-indexed retry attempt number
          "error_type": str,        # exception class name
          "message":    str,        # human-readable description
          "timestamp":  ISO-8601,
        }
    Used by the Supervisor to decide whether to halt or continue.
    """

    retry_count: int
    """
    Per-agent retry counter.  Reset to 0 each time Supervisor routes to a
    new agent.  Sub-agents increment this on each failed attempt.
    Maximum per-agent retries: 3 (hard-coded in each agent node).
    """

    # ------------------------------------------------------------------
    # Global iteration guard (prevents infinite loops)
    # ------------------------------------------------------------------
    iteration_count: int
    """
    Total number of node transitions executed in the graph.
    Incremented by every agent node before doing any work.
    If iteration_count >= MAX_ITERATIONS (15), Supervisor terminates the run
    with a partial report and records the reason in the supervisor_report.
    """

    # ------------------------------------------------------------------
    # Final output
    # ------------------------------------------------------------------
    supervisor_report: Optional[dict[str, Any]]
    """
    Synthesised incident response report produced by Supervisor after all
    sub-agents complete (or after max_iterations is reached).
    Schema:
        {
          "incident_id":   str,
          "status":        "complete" | "partial" | "failed",
          "severity":      "critical" | "high" | "medium" | "low",
          "summary":       str,
          "ioc_table":     [...],
          "timeline":      [...],
          "recommendations": [...],
          "agents_invoked": [...],
          "iteration_count": int,
          "completed_at":  ISO-8601,
        }
    """
