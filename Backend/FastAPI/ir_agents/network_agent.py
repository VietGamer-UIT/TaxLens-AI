# =============================================================================
# TaxLens-AI :: Network Agent Node
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Specialist sub-agent responsible for SIEM correlation & network analysis.
#
# Calls MCP tools:
#   - run_spl_search     : Run targeted SPL queries for C2, lateral movement
#   - get_notable_events : Pull Splunk ES alerts for this incident window
#
# Self-correction:
#   - Same retry pattern as ForensicsAgent (max 3 attempts per tool).
#   - On tool error → appends to state.error_log and retries.
#   - After exhausting retries → writes {"status": "exhausted_retries"} to
#     network_findings so Supervisor can move on.
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .state import IRAgentState
from ..mcp_servers.splunk_mcp import (
    run_spl_search, get_notable_events,
    SPLSearchInput, NotableEventsInput,
)

logger = logging.getLogger("taxlens.agents.network")

MAX_RETRIES: int = 3
AGENT_NAME:  str = "network_agent"

# Pre-built SPL queries for common IR hunting scenarios
_SPL_QUERIES: list[dict[str, str]] = [
    {
        "label": "c2_outbound",
        "query": (
            'index=network (dest_port=4444 OR dest_port=1337 OR dest_port=31337) '
            'action=allowed | stats count by src_ip, dest_ip, dest_port'
        ),
        "description": "Hunt for known C2 ports in firewall/proxy logs",
    },
    {
        "label": "proc_creation_suspicious",
        "query": (
            'index=wineventlog EventCode=4688 '
            'New_Process_Name="*AppData*" OR New_Process_Name="*Temp*" '
            '| table _time, host, Account_Name, New_Process_Name, Creator_Process_Name'
        ),
        "description": "Suspicious process creation from user directories",
    },
    {
        "label": "scheduled_task_creation",
        "query": (
            'index=wineventlog EventCode=4698 '
            '| table _time, host, Account_Name, Task_Name, Task_Content'
        ),
        "description": "Scheduled task creation events (persistence)",
    },
]


async def network_agent_node(state: IRAgentState) -> IRAgentState:
    """
    LangGraph node: Network Agent.

    Orchestrates Splunk SPL search queries and notable event retrieval
    to surface C2 communications, lateral movement, and persistence.

    Self-correction logic:
      - Validates each tool response (must be dict with status == "ok").
      - On failure: logs structured entry to error_log and retries up to
        MAX_RETRIES times before marking the tool as failed.
      - If all tools fail: sets network_findings to 'exhausted_retries'.

    Args:
        state: Current IRAgentState.

    Returns:
        Updated state with network_findings populated.
    """
    messages  = list(state.get("messages", []))
    error_log = list(state.get("error_log", []))

    logger.info("[%s] Starting SIEM correlation for incident=%s", AGENT_NAME, state.get("incident_id"))
    messages.append({
        "role": "assistant",
        "agent": AGENT_NAME,
        "content": "Beginning network/SIEM correlation — running SPL queries against Splunk.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # ------------------------------------------------------------------
    # Step 1: Run targeted SPL hunting queries
    # ------------------------------------------------------------------
    spl_results: dict[str, Any] = {}

    for query_def in _SPL_QUERIES:
        result = await _run_with_retry(
            tool_fn=run_spl_search,
            input_obj=SPLSearchInput(
                spl_query=query_def["query"],
                earliest="-48h",
                latest="now",
                max_results=200,
            ),
            tool_name=f"run_spl_search:{query_def['label']}",
            error_log=error_log,
            messages=messages,
        )
        if result is not None:
            spl_results[query_def["label"]] = {
                "description": query_def["description"],
                "data": result,
            }

    # ------------------------------------------------------------------
    # Step 2: Pull Splunk ES notable events
    # ------------------------------------------------------------------
    notable_result = await _run_with_retry(
        tool_fn=get_notable_events,
        input_obj=NotableEventsInput(max_events=50, severity_filter="medium"),
        tool_name="get_notable_events",
        error_log=error_log,
        messages=messages,
    )

    # ------------------------------------------------------------------
    # Assess overall status
    # ------------------------------------------------------------------
    all_tools_failed = (not spl_results) and (notable_result is None)

    if all_tools_failed:
        logger.error("[%s] All tools exhausted retries.", AGENT_NAME)
        findings: dict[str, Any] = {
            "status": "exhausted_retries",
            "agent": AGENT_NAME,
            "message": "All network MCP tools failed after max retries.",
        }
    else:
        # Flatten notable events for quick access by Supervisor
        notable_events = (
            notable_result.get("data", {}).get("notable_events", [])
            if notable_result else []
        )
        findings = {
            "status": "ok",
            "agent": AGENT_NAME,
            "spl_hunt_results": spl_results,
            "data": notable_result,
            # Denormalized for fast Supervisor severity assessment
            "notable_events_count": len(notable_events),
            "critical_event_count": sum(
                1 for e in notable_events if e.get("severity") == "critical"
            ),
        }

    summary_msg = (
        f"Network analysis complete. Status: {findings['status']}. "
        f"SPL queries executed: {list(spl_results.keys())}. "
        f"Notable events: {findings.get('notable_events_count', 0)} "
        f"({findings.get('critical_event_count', 0)} critical)."
    )
    messages.append({
        "role": "assistant",
        "agent": AGENT_NAME,
        "content": summary_msg,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
    logger.info("[%s] Done — status=%s", AGENT_NAME, findings["status"])

    return {
        **state,
        "messages": messages,
        "error_log": error_log,
        "network_findings": findings,
        "current_agent": "supervisor",    # Return control to supervisor
    }


# ---------------------------------------------------------------------------
# Self-correction helper (identical pattern to ForensicsAgent — DRY candidate)
# ---------------------------------------------------------------------------

async def _run_with_retry(
    tool_fn,
    input_obj,
    tool_name: str,
    error_log: list,
    messages: list,
) -> dict[str, Any] | None:
    """
    Invoke an async MCP tool with automatic retry and structured error logging.

    Args:
        tool_fn   : Async MCP tool coroutine to call.
        input_obj : Pydantic v2 input model instance for the tool.
        tool_name : Human-readable tool identifier for audit entries.
        error_log : Mutable list — error entries appended on failure.
        messages  : Mutable list — reasoning steps appended on failure.

    Returns:
        Tool result dict on success, or None after MAX_RETRIES failures.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result: dict[str, Any] = await tool_fn(input_obj)

            if not isinstance(result, dict):
                raise ValueError(f"Expected dict, got {type(result).__name__}")
            if result.get("status") == "error":
                raise RuntimeError(
                    f"Tool error: {result.get('error_type')} — {result.get('message')}"
                )

            logger.debug("[%s] '%s' succeeded on attempt %d.", AGENT_NAME, tool_name, attempt)
            return result

        except Exception as exc:
            error_log.append({
                "agent":      AGENT_NAME,
                "tool":       tool_name,
                "attempt":    attempt,
                "error_type": type(exc).__name__,
                "message":    str(exc),
                "timestamp":  datetime.now(tz=timezone.utc).isoformat(),
            })
            messages.append({
                "role": "system",
                "agent": AGENT_NAME,
                "content": (
                    f"[Self-correction] '{tool_name}' failed on attempt {attempt}/{MAX_RETRIES}: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                ),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })
            logger.warning(
                "[%s] '%s' attempt %d/%d failed: %s",
                AGENT_NAME, tool_name, attempt, MAX_RETRIES, exc,
            )

    logger.error("[%s] '%s' exhausted all %d retries.", AGENT_NAME, tool_name, MAX_RETRIES)
    return None
