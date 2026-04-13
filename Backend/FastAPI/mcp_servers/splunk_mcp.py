# =============================================================================
# TaxLens-AI :: Splunk MCP Server
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Wraps the Splunk REST API for the LangGraph IR agents.
#
# Endpoints targeted:
#   POST /services/search/jobs         — create a search job
#   GET  /services/search/jobs/<sid>   — poll job status
#   GET  /services/search/jobs/<sid>/results — fetch results
#   GET  /services/notable_events      — ES notable events (via saved search)
#
# Authentication: Bearer token loaded from environment variable SPLUNK_TOKEN.
# All requests enforce a 30-second timeout.
#
# NOTE (Hackathon): HTTP calls to Splunk are MOCKED with realistic JSON
# payloads.  Replace the _mock_* functions with live aiohttp/httpx calls
# when connecting to a real Splunk instance.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field, StrictStr, model_validator

logger = logging.getLogger("taxlens.mcp.splunk")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SPLUNK_BASE_URL: str = os.getenv("SPLUNK_BASE_URL", "https://splunk.taxlens.local:8089")
SPLUNK_TOKEN: str = os.getenv("SPLUNK_TOKEN", "eyJhbGciOiJIUzI1NiJ9.MOCK_TOKEN")
REQUEST_TIMEOUT_S: int = 30

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
SPLUNK_TOOL_REGISTRY: dict[str, Callable] = {}


def mcp_tool(name: str):
    """Decorator that registers a coroutine into SPLUNK_TOOL_REGISTRY."""
    def decorator(fn: Callable) -> Callable:
        SPLUNK_TOOL_REGISTRY[name] = fn
        logger.debug("Registered Splunk MCP tool: %s", name)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit_log(tool: str, params: dict[str, Any]) -> None:
    """Structured audit entry — required for Splunk Agentic Ops judging."""
    entry = {
        "event": "mcp_tool_invoked",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "server": "splunk_mcp",
        "tool": tool,
        "params": params,
    }
    logger.info(json.dumps(entry))


# ---------------------------------------------------------------------------
# Mock helpers — replace with real aiohttp calls in production
# ---------------------------------------------------------------------------

async def _mock_run_spl_search(spl_query: str, earliest: str, latest: str) -> dict[str, Any]:
    """Simulate Splunk search job creation + result retrieval."""
    await asyncio.sleep(0.15)   # Simulate network latency

    mock_sid = "1712345678.0001"
    mock_results = {
        "sid": mock_sid,
        "query": spl_query,
        "earliest": earliest,
        "latest": latest,
        "result_count": 3,
        "results": [
            {
                "_time": "2024-03-15T02:15:05.000Z",
                "host": "dc01.corp.local",
                "source": "WinEventLog:Security",
                "EventCode": "4688",
                "Account_Name": "SYSTEM",
                "New_Process_Name": r"C:\Users\victim\AppData\Roaming\evil.exe",
                "Creator_Process_Name": r"C:\Windows\System32\winlogon.exe",
                "severity": "critical",
            },
            {
                "_time": "2024-03-15T02:16:00.000Z",
                "host": "fw01.corp.local",
                "source": "cisco:asa",
                "src_ip": "192.168.1.10",
                "dst_ip": "185.220.101.47",
                "dst_port": "4444",
                "action": "allowed",
                "bytes_out": "142320",
                "severity": "critical",
            },
            {
                "_time": "2024-03-15T02:16:45.000Z",
                "host": "dc01.corp.local",
                "source": "WinEventLog:Security",
                "EventCode": "4698",
                "Account_Name": "SYSTEM",
                "Task_Name": "EvilPersist",
                "Task_Content": r"C:\Users\victim\AppData\Roaming\evil.exe",
                "severity": "high",
            },
        ],
    }
    return mock_results


async def _mock_get_notable_events(max_events: int, severity_filter: str) -> dict[str, Any]:
    """Simulate Splunk Enterprise Security Notable Events endpoint."""
    await asyncio.sleep(0.1)

    all_notables = [
        {
            "event_id": "NE-20240315-0001",
            "title": "Outbound C2 Communication Detected",
            "severity": "critical",
            "risk_score": 95,
            "src": "192.168.1.10",
            "dest": "185.220.101.47",
            "owner": "unassigned",
            "status": "new",
            "rule_name": "TOR Exit Node Communication",
            "time": "2024-03-15T02:16:00Z",
        },
        {
            "event_id": "NE-20240315-0002",
            "title": "Suspicious Process Execution from TEMP Path",
            "severity": "high",
            "risk_score": 80,
            "src": "dc01.corp.local",
            "dest": r"C:\Users\victim\AppData\Roaming\evil.exe",
            "owner": "soc-analyst-1",
            "status": "in_progress",
            "rule_name": "Execution from User AppData",
            "time": "2024-03-15T02:15:05Z",
        },
        {
            "event_id": "NE-20240315-0003",
            "title": "Scheduled Task Created for Persistence",
            "severity": "high",
            "risk_score": 75,
            "src": "dc01.corp.local",
            "dest": "Task: EvilPersist",
            "owner": "unassigned",
            "status": "new",
            "rule_name": "Scheduled Task Abuse",
            "time": "2024-03-15T02:16:45Z",
        },
        {
            "event_id": "NE-20240315-0004",
            "title": "Failed Login Spike Detected",
            "severity": "medium",
            "risk_score": 50,
            "src": "192.168.1.55",
            "dest": "dc01.corp.local",
            "owner": "unassigned",
            "status": "new",
            "rule_name": "Brute Force — Windows AD",
            "time": "2024-03-15T01:59:00Z",
        },
    ]

    # Filter by severity if requested
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    min_level = severity_order.get(severity_filter.lower(), 0)
    filtered = [
        e for e in all_notables
        if severity_order.get(e["severity"], 0) >= min_level
    ]

    return {
        "total_found": len(filtered),
        "returned": min(max_events, len(filtered)),
        "notable_events": filtered[:max_events],
    }


# ---------------------------------------------------------------------------
# Pydantic v2 Input Schemas
# ---------------------------------------------------------------------------

class SPLSearchInput(BaseModel):
    """Input schema for the run_spl_search tool."""
    spl_query: StrictStr = Field(
        ...,
        description="The full SPL (Search Processing Language) query string",
    )
    earliest: StrictStr = Field(
        default="-24h",
        description="Splunk time modifier for search start (e.g. '-24h', '2024-03-15T00:00:00')",
    )
    latest: StrictStr = Field(
        default="now",
        description="Splunk time modifier for search end",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum number of results to retrieve (1–10,000)",
    )

    @model_validator(mode="after")
    def validate_spl_safety(self) -> "SPLSearchInput":
        """Reject SPL queries containing data-modification commands."""
        # Splunk SPL write commands we never allow from agents
        dangerous_cmds = {"delete", "outputlookup", "collect", "outputcsv", "sendemail"}
        lower_query = self.spl_query.lower()
        for cmd in dangerous_cmds:
            if f"| {cmd}" in lower_query or lower_query.startswith(cmd):
                raise ValueError(f"SPL query contains a disallowed write command: '{cmd}'")
        return self


class NotableEventsInput(BaseModel):
    """Input schema for the get_notable_events tool."""
    max_events: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum number of notable events to retrieve",
    )
    severity_filter: StrictStr = Field(
        default="medium",
        description="Minimum severity to include: 'low' | 'medium' | 'high' | 'critical'",
    )

    @model_validator(mode="after")
    def validate_severity(self) -> "NotableEventsInput":
        allowed = {"low", "medium", "high", "critical"}
        if self.severity_filter.lower() not in allowed:
            raise ValueError(f"severity_filter must be one of {allowed}")
        return self


# ---------------------------------------------------------------------------
# MCP Tool Implementations
# ---------------------------------------------------------------------------

@mcp_tool("run_spl_search")
async def run_spl_search(params: SPLSearchInput) -> dict[str, Any]:
    """
    Submit a Splunk search job and retrieve its results.

    Flow (production):
      1. POST /services/search/jobs  → obtain sid
      2. Poll GET /services/search/jobs/<sid> until dispatchState == DONE
      3. GET /services/search/jobs/<sid>/results?output_mode=json&count=<max>

    All HTTP requests use Bearer token auth and a 30-second timeout.

    Args:
        params: SPLSearchInput — validated SPL query and time range.

    Returns:
        dict with search results or structured error information.
    """
    tool_name = "run_spl_search"
    _audit_log(tool_name, params.model_dump())

    # --- Production HTTP skeleton (commented out for mock mode) ---
    # headers = {"Authorization": f"Bearer {SPLUNK_TOKEN}"}
    # async with aiohttp.ClientSession(headers=headers) as session:
    #     # Step 1: Create search job
    #     async with session.post(
    #         f"{SPLUNK_BASE_URL}/services/search/jobs",
    #         data={"search": f"search {params.spl_query}", "earliest_time": params.earliest,
    #               "latest_time": params.latest, "output_mode": "json"},
    #         timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
    #         ssl=False,
    #     ) as resp:
    #         resp.raise_for_status()
    #         sid = (await resp.json())["sid"]
    #
    #     # Step 2: Poll until done
    #     for _ in range(30):
    #         await asyncio.sleep(1)
    #         async with session.get(
    #             f"{SPLUNK_BASE_URL}/services/search/jobs/{sid}?output_mode=json",
    #             timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
    #             ssl=False,
    #         ) as resp:
    #             state = (await resp.json())["entry"][0]["content"]["dispatchState"]
    #             if state == "DONE":
    #                 break
    #
    #     # Step 3: Fetch results
    #     async with session.get(
    #         f"{SPLUNK_BASE_URL}/services/search/jobs/{sid}/results",
    #         params={"output_mode": "json", "count": params.max_results},
    #         timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
    #         ssl=False,
    #     ) as resp:
    #         resp.raise_for_status()
    #         return {"status": "ok", "tool": tool_name, "data": await resp.json()}

    try:
        result = await asyncio.wait_for(
            _mock_run_spl_search(params.spl_query, params.earliest, params.latest),
            timeout=REQUEST_TIMEOUT_S,
        )
        return {"status": "ok", "tool": tool_name, "data": result}

    except asyncio.TimeoutError:
        logger.error("%s TIMEOUT: query=%s", tool_name, params.spl_query[:80])
        return {"status": "error", "tool": tool_name, "error_type": "TimeoutError",
                "message": f"Splunk search timed out after {REQUEST_TIMEOUT_S}s"}
    except Exception as exc:
        logger.exception("Unexpected error in %s", tool_name)
        return {"status": "error", "tool": tool_name, "error_type": type(exc).__name__, "message": str(exc)}


@mcp_tool("get_notable_events")
async def get_notable_events(params: NotableEventsInput) -> dict[str, Any]:
    """
    Retrieve Splunk Enterprise Security Notable Events.

    Calls the ES notable events saved search endpoint, filters by severity,
    and returns structured event records for agent triage.

    Args:
        params: NotableEventsInput — max count and minimum severity filter.

    Returns:
        dict with notable events list or structured error information.
    """
    tool_name = "get_notable_events"
    _audit_log(tool_name, params.model_dump())

    # --- Production HTTP skeleton (commented out for mock mode) ---
    # headers = {"Authorization": f"Bearer {SPLUNK_TOKEN}"}
    # spl = (
    #     f"search index=notable severity>={params.severity_filter} "
    #     f"| head {params.max_events} | table event_id, title, severity, "
    #     f"risk_score, src, dest, owner, status, rule_name, _time"
    # )
    # ... (follow same create/poll/fetch pattern as run_spl_search)

    try:
        result = await asyncio.wait_for(
            _mock_get_notable_events(params.max_events, params.severity_filter),
            timeout=REQUEST_TIMEOUT_S,
        )
        return {"status": "ok", "tool": tool_name, "data": result}

    except asyncio.TimeoutError:
        logger.error("%s TIMEOUT after %ss", tool_name, REQUEST_TIMEOUT_S)
        return {"status": "error", "tool": tool_name, "error_type": "TimeoutError",
                "message": f"Splunk notable events timed out after {REQUEST_TIMEOUT_S}s"}
    except Exception as exc:
        logger.exception("Unexpected error in %s", tool_name)
        return {"status": "error", "tool": tool_name, "error_type": type(exc).__name__, "message": str(exc)}
