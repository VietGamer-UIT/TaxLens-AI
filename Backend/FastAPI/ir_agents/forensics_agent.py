# =============================================================================
# TaxLens-AI :: Forensics Agent Node
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Specialist sub-agent responsible for memory & disk forensics.
#
# Calls MCP tools:
#   - run_volatility_plugin (windows.pslist, windows.netscan, windows.malfind)
#   - run_log2timeline      (artifact super-timeline)
#
# Self-correction:
#   - On tool error or JSON parse failure → appends to state.error_log
#   - Retries up to MAX_RETRIES (3) per tool call
#   - After exhausting retries → writes {"status": "exhausted_retries"} to
#     forensics_findings so Supervisor knows to move on
# =============================================================================

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .state import IRAgentState
from ..mcp_servers.forensics_mcp import (
    run_volatility_plugin, run_log2timeline,
    VolatilityInput, Log2TimelineInput,
)

logger = logging.getLogger("taxlens.agents.forensics")

MAX_RETRIES: int = 3      # Maximum per-tool retry attempts
AGENT_NAME:  str = "forensics_agent"


async def forensics_agent_node(state: IRAgentState) -> IRAgentState:
    """
    LangGraph node: Forensics Agent.

    Orchestrates Volatility3 and log2timeline MCP calls against the evidence
    paths registered in state.evidence_paths.

    Self-correction logic:
      - Validates each tool response as a dict with 'status' key.
      - On failure, logs to error_log and retries up to MAX_RETRIES times.
      - After MAX_RETRIES failures, marks findings as 'exhausted_retries'.

    Args:
        state: Current IRAgentState.

    Returns:
        Updated state with forensics_findings populated.
    """
    messages    = list(state.get("messages", []))
    error_log   = list(state.get("error_log", []))
    retry_count = state.get("retry_count", 0)
    evidence_paths = state.get("evidence_paths", [])

    # Use first evidence path that looks like a memory image (.raw/.vmem/.dmp)
    mem_image = next(
        (p for p in evidence_paths if any(p.endswith(ext) for ext in (".raw", ".vmem", ".dmp", ".mem"))),
        evidence_paths[0] if evidence_paths else "/evidence/sample_mem.raw",
    )

    logger.info("[%s] Starting — evidence=%s", AGENT_NAME, mem_image)
    messages.append({
        "role": "assistant",
        "agent": AGENT_NAME,
        "content": f"Beginning forensics analysis of {mem_image}.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # ------------------------------------------------------------------
    # Run Volatility3 plugins
    # ------------------------------------------------------------------
    vol_results: dict[str, Any] = {}
    plugins = ["windows.pslist", "windows.netscan", "windows.malfind"]

    for plugin in plugins:
        result = await _run_with_retry(
            tool_fn=run_volatility_plugin,
            input_obj=VolatilityInput(image_path=mem_image, plugin=plugin),
            tool_name=f"run_volatility_plugin:{plugin}",
            error_log=error_log,
            messages=messages,
        )
        if result is not None:
            vol_results[plugin] = result

    # ------------------------------------------------------------------
    # Run log2timeline for super-timeline
    # ------------------------------------------------------------------
    timeline_result = await _run_with_retry(
        tool_fn=run_log2timeline,
        input_obj=Log2TimelineInput(evidence_path=mem_image, output_format="json"),
        tool_name="run_log2timeline",
        error_log=error_log,
        messages=messages,
    )

    # ------------------------------------------------------------------
    # Assess overall status
    # ------------------------------------------------------------------
    all_tools_failed = (not vol_results) and (timeline_result is None)

    if all_tools_failed:
        logger.error("[%s] All tools exhausted retries.", AGENT_NAME)
        findings: dict[str, Any] = {
            "status": "exhausted_retries",
            "agent": AGENT_NAME,
            "message": "All forensics MCP tools failed after max retries.",
        }
    else:
        findings = {
            "status": "ok",
            "agent": AGENT_NAME,
            "volatility_results": vol_results,
            "data": timeline_result,
        }

    messages.append({
        "role": "assistant",
        "agent": AGENT_NAME,
        "content": (
            f"Forensics analysis complete. Status: {findings['status']}. "
            f"Plugins succeeded: {list(vol_results.keys())}. "
            f"Timeline: {'ok' if timeline_result else 'failed'}."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
    logger.info("[%s] Done — status=%s", AGENT_NAME, findings["status"])

    return {
        **state,
        "messages": messages,
        "error_log": error_log,
        "forensics_findings": findings,
        "current_agent": "supervisor",    # Hand back to supervisor after work
    }


# ---------------------------------------------------------------------------
# Self-correction helper
# ---------------------------------------------------------------------------

async def _run_with_retry(
    tool_fn,
    input_obj,
    tool_name: str,
    error_log: list,
    messages: list,
) -> dict[str, Any] | None:
    """
    Call an async MCP tool function up to MAX_RETRIES times.

    On each failure:
      - Appends a structured entry to error_log.
      - Appends a reasoning message to messages (full audit trail).
      - Waits 0 seconds between retries (mock env — would use backoff in prod).

    Returns the tool result dict on success, or None after exhausting retries.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result: dict[str, Any] = await tool_fn(input_obj)

            # Validate response structure (self-correction check)
            if not isinstance(result, dict):
                raise ValueError(f"Expected dict response, got {type(result).__name__}")
            if result.get("status") == "error":
                raise RuntimeError(
                    f"Tool returned error: {result.get('error_type')} — {result.get('message')}"
                )

            logger.debug("[%s] Tool '%s' succeeded on attempt %d.", AGENT_NAME, tool_name, attempt)
            return result

        except Exception as exc:
            error_entry = {
                "agent":      AGENT_NAME,
                "tool":       tool_name,
                "attempt":    attempt,
                "error_type": type(exc).__name__,
                "message":    str(exc),
                "timestamp":  datetime.now(tz=timezone.utc).isoformat(),
            }
            error_log.append(error_entry)
            messages.append({
                "role": "system",
                "agent": AGENT_NAME,
                "content": (
                    f"[Self-correction] Tool '{tool_name}' failed on attempt {attempt}/{MAX_RETRIES}: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                ),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })
            logger.warning(
                "[%s] Tool '%s' attempt %d/%d failed: %s",
                AGENT_NAME, tool_name, attempt, MAX_RETRIES, exc
            )

    logger.error("[%s] Tool '%s' exhausted all %d retries.", AGENT_NAME, tool_name, MAX_RETRIES)
    return None
