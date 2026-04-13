# =============================================================================
# TaxLens-AI :: Database / Threat Intel Agent Node
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Specialist sub-agent responsible for IOC enrichment using threat intelligence.
#
# "Database" in the IR context means the threat intelligence data stores:
#   - VirusTotal v3 (file hashes, IP reputation)
#   - AbuseIPDB    (IP abuse confidence scoring)
#
# Strategy:
#   1. Extracts IOCs (IPs and file hashes) from earlier agent findings
#      (forensics_findings, network_findings) stored in state.
#   2. Deduplicates IOCs to avoid redundant API calls.
#   3. Enriches each IOC via the threat_intel_mcp tools.
#   4. Produces a unified ioc_verdicts list for the Supervisor report.
#
# Self-correction:
#   - Same retry pattern as other agents (max 3 attempts per IOC).
#   - Failed lookups are recorded in error_log; partial results are accepted.
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .state import IRAgentState
from ..mcp_servers.threat_intel_mcp import (
    lookup_ip, lookup_hash,
    IPLookupInput, HashLookupInput,
)

logger = logging.getLogger("taxlens.agents.database")

MAX_RETRIES: int = 3
AGENT_NAME:  str = "database_agent"


async def database_agent_node(state: IRAgentState) -> IRAgentState:
    """
    LangGraph node: Database / Threat Intelligence Agent.

    Extracts IOCs from prior agent findings in state, then calls
    threat_intel_mcp tools to enrich each IOC with reputation data.

    Self-correction logic:
      - Validates tool response structure and status.
      - Retries failed IOC lookups up to MAX_RETRIES times.
      - Partial results (some IOCs failed) are still returned as 'ok'.
      - Only 'exhausted_retries' is set if ALL lookups failed.

    Args:
        state: Current IRAgentState (expects forensics_findings and
               network_findings to be populated by prior agents).

    Returns:
        Updated state with database_findings populated.
    """
    messages  = list(state.get("messages", []))
    error_log = list(state.get("error_log", []))

    logger.info("[%s] Starting IOC enrichment for incident=%s", AGENT_NAME, state.get("incident_id"))
    messages.append({
        "role": "assistant",
        "agent": AGENT_NAME,
        "content": "Beginning threat intelligence enrichment — extracting IOCs from prior findings.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # ------------------------------------------------------------------
    # Step 1: Extract IOCs from prior agent findings
    # ------------------------------------------------------------------
    ip_iocs:   list[str] = []
    hash_iocs: list[str] = []

    _extract_iocs_from_forensics(state.get("forensics_findings"), ip_iocs, hash_iocs)
    _extract_iocs_from_network(state.get("network_findings"), ip_iocs)

    # Deduplicate while preserving order
    ip_iocs   = list(dict.fromkeys(ip_iocs))
    hash_iocs = list(dict.fromkeys(hash_iocs))

    # Fallback: if no IOCs found from prior agents, use incident-level defaults
    if not ip_iocs and not hash_iocs:
        logger.warning("[%s] No IOCs extracted from prior findings — using defaults.", AGENT_NAME)
        ip_iocs   = ["185.220.101.47"]   # Known C2 IP seed
        hash_iocs = ["4c1d2dead3beef4a5b6c7d8e9f0a1b2c"]  # Triggers mock malicious response

    messages.append({
        "role": "assistant",
        "agent": AGENT_NAME,
        "content": (
            f"IOC extraction complete. "
            f"IPs to enrich: {ip_iocs}. "
            f"Hashes to enrich: {hash_iocs}."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # ------------------------------------------------------------------
    # Step 2: Enrich IP IOCs
    # ------------------------------------------------------------------
    ioc_verdicts: list[dict[str, Any]] = []

    for ip in ip_iocs:
        result = await _run_with_retry(
            tool_fn=lookup_ip,
            input_obj=IPLookupInput(ip_address=ip),
            tool_name=f"lookup_ip:{ip}",
            error_log=error_log,
            messages=messages,
        )
        if result is not None:
            data = result.get("data", {})
            ioc_verdicts.append({
                "ioc_type":          "ip",
                "ioc_value":         ip,
                "verdict":           data.get("verdict", "UNKNOWN"),
                "abuse_confidence":  data.get("abuseipdb", {}).get("abuseConfidenceScore", 0),
                "vt_malicious_count": (
                    data.get("virustotal", {})
                        .get("attributes", {})
                        .get("last_analysis_stats", {})
                        .get("malicious", 0)
                ),
                "tags":              data.get("virustotal", {}).get("attributes", {}).get("tags", []),
                "source":            "VirusTotal+AbuseIPDB",
            })

    # ------------------------------------------------------------------
    # Step 3: Enrich file hash IOCs
    # ------------------------------------------------------------------
    for h in hash_iocs:
        result = await _run_with_retry(
            tool_fn=lookup_hash,
            input_obj=HashLookupInput(file_hash=h),
            tool_name=f"lookup_hash:{h[:16]}...",
            error_log=error_log,
            messages=messages,
        )
        if result is not None:
            data = result.get("data", {})
            ioc_verdicts.append({
                "ioc_type":          "hash",
                "ioc_value":         h,
                "hash_type":         data.get("hash_type", "unknown"),
                "verdict":           data.get("verdict", "UNKNOWN"),
                "vt_malicious_count": (
                    data.get("virustotal", {})
                        .get("attributes", {})
                        .get("last_analysis_stats", {})
                        .get("malicious", 0)
                ),
                "threat_label":      (
                    data.get("virustotal", {})
                        .get("attributes", {})
                        .get("popular_threat_classification", {})
                        .get("suggested_threat_label", "unknown")
                ),
                "source": "VirusTotal",
            })

    # ------------------------------------------------------------------
    # Step 4: Assess overall status
    # ------------------------------------------------------------------
    total_iocs   = len(ip_iocs) + len(hash_iocs)
    success_iocs = len(ioc_verdicts)

    if success_iocs == 0 and total_iocs > 0:
        logger.error("[%s] All IOC lookups failed.", AGENT_NAME)
        findings: dict[str, Any] = {
            "status":  "exhausted_retries",
            "agent":   AGENT_NAME,
            "message": f"0/{total_iocs} IOC lookups succeeded after max retries.",
        }
    else:
        malicious_count = sum(1 for v in ioc_verdicts if v.get("verdict") == "MALICIOUS")
        findings = {
            "status": "ok",
            "agent":  AGENT_NAME,
            "data": {
                "ioc_verdicts":     ioc_verdicts,
                "total_enriched":   success_iocs,
                "malicious_count":  malicious_count,
                "clean_count":      success_iocs - malicious_count,
            },
        }

    summary_msg = (
        f"ThreatIntel enrichment complete. Status: {findings['status']}. "
        f"IOCs enriched: {success_iocs}/{total_iocs}. "
        f"Malicious verdicts: {findings.get('data', {}).get('malicious_count', 'N/A')}."
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
        "database_findings": findings,
        "current_agent": "supervisor",    # Return control to supervisor
    }


# ---------------------------------------------------------------------------
# IOC extraction helpers
# ---------------------------------------------------------------------------

def _extract_iocs_from_forensics(
    forensics_findings: dict[str, Any] | None,
    ip_iocs: list[str],
    hash_iocs: list[str],
) -> None:
    """
    Parse forensics_findings to extract IP addresses and file hashes.

    Sources mined:
      - windows.netscan  → ForeignAddr (external IPs)
      - windows.malfind  → HexDump first 4 bytes as MZ marker (skipped — no hash)
    """
    if not forensics_findings or forensics_findings.get("status") != "ok":
        return

    vol_results = forensics_findings.get("volatility_results", {})

    # Extract IPs from netscan
    netscan = vol_results.get("windows.netscan", {}).get("data", {}).get("connections", [])
    for conn in netscan:
        foreign_addr = conn.get("ForeignAddr", "")
        if foreign_addr and not foreign_addr.startswith(("192.168.", "10.", "172.", "127.")):
            ip_iocs.append(foreign_addr)


def _extract_iocs_from_network(
    network_findings: dict[str, Any] | None,
    ip_iocs: list[str],
) -> None:
    """
    Parse network_findings (Splunk) to extract destination IPs from SPL results.

    Sources mined:
      - c2_outbound SPL hunt → dest_ip field of each result row
    """
    if not network_findings or network_findings.get("status") != "ok":
        return

    spl_hunt = network_findings.get("spl_hunt_results", {})
    c2_hunt  = spl_hunt.get("c2_outbound", {}).get("data", {}).get("data", {})
    results  = c2_hunt.get("results", [])

    for row in results:
        dest_ip = row.get("dest_ip") or row.get("ForeignAddr", "")
        if dest_ip and not dest_ip.startswith(("192.168.", "10.", "172.", "127.")):
            ip_iocs.append(dest_ip)


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
    Invoke an async MCP tool with automatic retry and structured error logging.

    Args:
        tool_fn   : Async MCP tool coroutine to call.
        input_obj : Pydantic v2 input model instance.
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
