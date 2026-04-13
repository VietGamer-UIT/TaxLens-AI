# =============================================================================
# TaxLens-AI :: Supervisor Agent Node
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# The Supervisor is the master orchestrator of the LangGraph IR workflow.
#
# Responsibilities:
#   1. INTAKE   : Receive the incident and initialise state defaults.
#   2. ROUTING  : Decide which specialist sub-agent to invoke next.
#   3. SYNTHESIS: Once all 3 agent reports are in (or max_iterations reached),
#                 compile the final supervisor_report.
#
# Termination conditions (in priority order):
#   A. All three sub-agents have returned non-None findings  → "complete"
#   B. iteration_count >= MAX_ITERATIONS (15)                → "partial"
#   C. Critical unrecoverable error in all three agents      → "failed"
#
# The Supervisor uses a deterministic rule-based router (no LLM for routing)
# to keep latency low and the control flow auditable.
# =============================================================================

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .state import IRAgentState

logger = logging.getLogger("taxlens.agents.supervisor")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_ITERATIONS: int = 15                          # Global graph iteration cap
AGENTS_IN_ORDER: list[str] = [                   # Deterministic dispatch order
    "forensics_agent",
    "network_agent",
    "database_agent",
]


# ---------------------------------------------------------------------------
# Public node function
# ---------------------------------------------------------------------------

async def supervisor_node(state: IRAgentState) -> IRAgentState:
    """
    LangGraph node: Supervisor / Master Agent.

    Called at graph start (intake) and again after each sub-agent completes.
    Mutates and returns the updated state dict.

    Args:
        state: Current IRAgentState passed in by LangGraph.

    Returns:
        Updated IRAgentState with routing decision or final supervisor_report.
    """
    incident_id: str = state.get("incident_id", "UNKNOWN")
    iteration_count: int = state.get("iteration_count", 0) + 1

    logger.info(
        "[Supervisor] Tick #%d for incident=%s", iteration_count, incident_id
    )

    # --- Append routing message to audit trail ---
    messages: list[dict[str, Any]] = list(state.get("messages", []))
    messages.append({
        "role": "system",
        "agent": "supervisor",
        "content": f"Supervisor tick #{iteration_count} — evaluating routing decision.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # --- Global iteration guard ---
    if iteration_count >= MAX_ITERATIONS:
        logger.warning(
            "[Supervisor] MAX_ITERATIONS (%d) reached for incident=%s — forcing partial report.",
            MAX_ITERATIONS, incident_id,
        )
        report = _compile_report(state, status="partial", iteration_count=iteration_count)
        return {
            **state,
            "messages": messages,
            "iteration_count": iteration_count,
            "current_agent": "DONE",
            "supervisor_report": report,
        }

    # --- Check which agents still need to run ---
    next_agent = _decide_next_agent(state)

    if next_agent is None:
        # All three findings are in — synthesise final report
        logger.info("[Supervisor] All sub-agents complete — compiling final report.")
        report = _compile_report(state, status="complete", iteration_count=iteration_count)
        messages.append({
            "role": "assistant",
            "agent": "supervisor",
            "content": "All specialist agents have reported. Final IR report compiled.",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
        return {
            **state,
            "messages": messages,
            "iteration_count": iteration_count,
            "current_agent": "DONE",
            "supervisor_report": report,
        }

    # --- Route to next agent ---
    logger.info("[Supervisor] Routing to: %s", next_agent)
    messages.append({
        "role": "assistant",
        "agent": "supervisor",
        "content": f"Dispatching to {next_agent}.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    return {
        **state,
        "messages": messages,
        "iteration_count": iteration_count,
        "current_agent": next_agent,
        "retry_count": 0,          # Reset retry counter for the incoming agent
    }


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------

def _decide_next_agent(state: IRAgentState) -> str | None:
    """
    Determine which sub-agent should run next.

    Strategy: run agents in a fixed order; skip those that already have
    findings (status == "ok") in state.

    Returns None when all three agents have completed successfully or
    exhausted their retries.
    """
    forensics_done = _findings_ready(state.get("forensics_findings"))
    network_done   = _findings_ready(state.get("network_findings"))
    database_done  = _findings_ready(state.get("database_findings"))

    status_map = {
        "forensics_agent": forensics_done,
        "network_agent":   network_done,
        "database_agent":  database_done,
    }

    for agent in AGENTS_IN_ORDER:
        if not status_map[agent]:
            return agent   # First incomplete agent in deterministic order

    return None            # All done


def _findings_ready(findings: dict[str, Any] | None) -> bool:
    """Return True if findings exist and are not a retry-eligible error state."""
    if findings is None:
        return False
    # Treat "ok" or "exhausted_retries" as terminal (don't re-run)
    return findings.get("status") in {"ok", "exhausted_retries"}


# ---------------------------------------------------------------------------
# Report synthesis
# ---------------------------------------------------------------------------

def _compile_report(
    state: IRAgentState,
    status: str,
    iteration_count: int,
) -> dict[str, Any]:
    """
    Synthesise a final supervisor report from all sub-agent findings.

    Extracts key IOCs, timeline events, and notable events into a unified
    structure suitable for SOC triage and hackathon judging.
    """
    incident_id = state.get("incident_id", "UNKNOWN")
    forensics   = state.get("forensics_findings") or {}
    network     = state.get("network_findings")   or {}
    database    = state.get("database_findings")  or {}
    error_log   = state.get("error_log", [])

    # --- Severity derivation (simple heuristic for demo) ---
    severity = _derive_severity(forensics, network, database)

    # --- Flatten IOCs from database findings ---
    ioc_verdicts = database.get("data", {}).get("ioc_verdicts", [])

    # --- Flatten timeline from forensics ---
    timeline = (
        forensics.get("data", {})
                 .get("data", {})
                 .get("timeline_events", [])
    )

    # --- Flatten notable events from network ---
    notable_events = (
        network.get("data", {})
               .get("data", {})
               .get("notable_events", [])
    )

    # --- Recommendations ---
    recommendations = _generate_recommendations(forensics, network, database)

    return {
        "incident_id":     incident_id,
        "status":          status,          # "complete" | "partial" | "failed"
        "severity":        severity,
        "summary":         _build_summary(incident_id, severity, status, error_log),
        "ioc_table":       ioc_verdicts,
        "timeline":        timeline,
        "notable_events":  notable_events,
        "recommendations": recommendations,
        "agents_invoked":  AGENTS_IN_ORDER,
        "error_count":     len(error_log),
        "iteration_count": iteration_count,
        "completed_at":    datetime.now(tz=timezone.utc).isoformat(),
    }


def _derive_severity(
    forensics: dict, network: dict, database: dict
) -> str:
    """Heuristically derive overall incident severity from agent findings."""
    # Check for CRITICAL indicators in findings
    forensics_data = forensics.get("data", {}).get("data", {})
    network_data   = network.get("data", {}).get("data", {})
    database_data  = database.get("data", {}).get("data", {})

    # Memory injection or high-entropy sections → critical
    if forensics_data.get("injections"):
        return "critical"

    # Active C2 connection → critical
    conns = forensics_data.get("connections", [])
    if any(c.get("ForeignPort") == 4444 for c in conns):
        return "critical"

    # Splunk critical notable event → critical
    notables = network_data.get("notable_events", [])
    if any(n.get("severity") == "critical" for n in notables):
        return "critical"

    # Malicious IOC verdict → high
    iocs = database_data.get("ioc_verdicts", [])
    if any(i.get("verdict") == "MALICIOUS" for i in iocs):
        return "high"

    return "medium"


def _generate_recommendations(
    forensics: dict, network: dict, database: dict
) -> list[str]:
    """Produce actionable recommendations based on collected findings."""
    recs: list[str] = []
    forensics_data = forensics.get("data", {}).get("data", {})
    network_data   = network.get("data", {}).get("data", {})

    if forensics_data.get("injections"):
        recs.append("ISOLATE: Immediately isolate affected host from network.")
        recs.append("MEMORY DUMP: Preserve full memory image for deep forensic analysis.")

    conns = forensics_data.get("connections", [])
    c2_ips = {c["ForeignAddr"] for c in conns if c.get("ForeignPort") in {4444, 1337, 31337}}
    for ip in c2_ips:
        recs.append(f"BLOCK: Add firewall rule to block C2 IP {ip} (all ports).")
        recs.append(f"HUNT: Search all hosts for outbound connections to {ip}.")

    processes = forensics_data.get("processes", [])
    for proc in processes:
        if proc.get("ALERT"):
            recs.append(
                f"TERMINATE: Kill process {proc['Name']} (PID {proc['PID']}) "
                f"and remove associated persistence mechanisms."
            )

    notables = network_data.get("notable_events", [])
    for event in notables:
        if "persistence" in event.get("title", "").lower():
            recs.append("REMEDIATE: Remove scheduled task 'EvilPersist' and registry Run key entries.")
            break

    if not recs:
        recs.append("MONITOR: Continue monitoring — no critical indicators detected in current dataset.")

    return recs


def _build_summary(
    incident_id: str, severity: str, status: str, error_log: list
) -> str:
    error_note = f"  {len(error_log)} tool error(s) were encountered during analysis." if error_log else ""
    return (
        f"[TaxLens-AI] Incident {incident_id} analysis {status.upper()}. "
        f"Overall severity assessed as {severity.upper()}. "
        f"Three specialist agents (Forensics, Network, Database/ThreatIntel) were invoked "
        f"to investigate the incident artefacts.{error_note}"
    )
