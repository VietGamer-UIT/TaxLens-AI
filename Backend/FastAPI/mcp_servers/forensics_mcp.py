# =============================================================================
# TaxLens-AI :: Forensics MCP Server
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Wraps SIFT (SANS Investigative Forensic Toolkit) CLI tools:
#   - volatility3     : Memory forensics (process trees, network conns, etc.)
#   - log2timeline    : Super-timeline generation via Plaso
#
# SECURITY CONSTRAINTS (read-only enforcement):
#   - subprocess execution is validated against a denylist of write commands
#   - FilePath inputs are validated by Pydantic v2 before any invocation
#   - All tool invocations are logged to stdout for audit trail
#
# NOTE (Hackathon): subprocess execution is MOCKED with realistic dummy
# JSON payloads so that the full agent flow can be tested locally without
# a live SIFT workstation.  Replace the _mock_* functions with real
# subprocess.run() calls when running in a SIFT environment.
# =============================================================================

from __future__ import annotations

import asyncio
import functools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, StrictStr, model_validator

logger = logging.getLogger("taxlens.mcp.forensics")

# ---------------------------------------------------------------------------
# Read-only denylist — any command containing these tokens will be blocked.
# ---------------------------------------------------------------------------
_WRITE_CMD_DENYLIST: set[str] = {
    "rm", "mv", "cp", "dd", "shred", "truncate", "chmod", "chown",
    "write", "format", "mkfs", "fdisk", "parted", "wipefs",
    ">", ">>",           # shell redirects  (basic string-match guard)
    "tee", "install",
}

# ---------------------------------------------------------------------------
# Tool decorator registry
# ---------------------------------------------------------------------------
FORENSICS_TOOL_REGISTRY: dict[str, Callable] = {}


def mcp_tool(name: str):
    """Decorator that registers an async function into FORENSICS_TOOL_REGISTRY."""
    def decorator(fn: Callable) -> Callable:
        FORENSICS_TOOL_REGISTRY[name] = fn
        logger.debug("Registered forensics MCP tool: %s", name)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _audit_log(tool: str, params: dict[str, Any]) -> None:
    """Emit a structured audit event to stdout / log.
    SANS FIND EVIL criterion: every tool invocation must be traceable.
    """
    entry = {
        "event": "mcp_tool_invoked",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "server": "forensics_mcp",
        "tool": tool,
        "params": params,
    }
    logger.info(json.dumps(entry))


def _deny_write_operations(cmd_parts: list[str]) -> None:
    """Raise PermissionError if any element of cmd_parts is in the denylist."""
    joined = " ".join(cmd_parts).lower()
    for token in _WRITE_CMD_DENYLIST:
        if token in joined:
            raise PermissionError(
                f"[SECURITY] Blocked write operation detected in command: '{joined}'"
            )


# ---------------------------------------------------------------------------
# Mock helpers — replace with real subprocess.run() for production
# ---------------------------------------------------------------------------

async def _mock_volatility3(image_path: str, plugin: str) -> dict[str, Any]:
    """
    Simulates the output of:
        vol -f <image_path> <plugin>
    Returns realistic dummy forensics data for judge demonstration.
    """
    # Simulated 100 ms I/O delay to mimic real tool latency
    await asyncio.sleep(0.1)
    mock_outputs: dict[str, Any] = {
        "windows.pslist": {
            "plugin": "windows.pslist",
            "image": image_path,
            "processes": [
                {"PID": 4,    "PPID": 0,   "Name": "System",       "Handles": 1234, "Threads": 120},
                {"PID": 624,  "PPID": 4,   "Name": "smss.exe",     "Handles": 40,   "Threads": 3},
                {"PID": 748,  "PPID": 624, "Name": "csrss.exe",    "Handles": 512,  "Threads": 10},
                {"PID": 844,  "PPID": 748, "Name": "winlogon.exe", "Handles": 800,  "Threads": 5},
                {"PID": 1337, "PPID": 844, "Name": "evil.exe",     "Handles": 203,  "Threads": 2,
                 "ALERT": "Suspicious: spawned from winlogon, unusual name"},
            ],
        },
        "windows.netscan": {
            "plugin": "windows.netscan",
            "image": image_path,
            "connections": [
                {"Proto": "TCPv4", "LocalAddr": "192.168.1.10", "LocalPort": 49201,
                 "ForeignAddr": "185.220.101.47", "ForeignPort": 4444,
                 "State": "ESTABLISHED", "PID": 1337, "Process": "evil.exe",
                 "ALERT": "Known C2 IP (TOR exit node)"},
                {"Proto": "TCPv4", "LocalAddr": "192.168.1.10", "LocalPort": 49210,
                 "ForeignAddr": "8.8.8.8", "ForeignPort": 53,
                 "State": "ESTABLISHED", "PID": 4, "Process": "System"},
            ],
        },
        "windows.malfind": {
            "plugin": "windows.malfind",
            "image": image_path,
            "injections": [
                {"PID": 1337, "Process": "evil.exe", "Start": "0x400000",
                 "Protection": "PAGE_EXECUTE_READWRITE",
                 "HexDump": "4D5A90000300000004000000FFFF0000",
                 "ALERT": "PE header in RWX region — likely code injection"},
            ],
        },
    }
    return mock_outputs.get(
        plugin,
        {"plugin": plugin, "image": image_path, "result": f"Mock: no template for plugin '{plugin}'"},
    )


async def _mock_log2timeline(evidence_path: str, output_format: str) -> dict[str, Any]:
    """
    Simulates the output of:
        log2timeline.py --storage-file /tmp/plaso.dump <evidence_path>
    Returns a condensed super-timeline as dummy events.
    """
    await asyncio.sleep(0.1)
    return {
        "tool": "log2timeline/plaso",
        "evidence": evidence_path,
        "output_format": output_format,
        "timeline_events": [
            {
                "timestamp": "2024-03-15T02:14:33Z",
                "source": "WindowsRegistryKey",
                "artifact": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                "description": "evil.exe added to Run key (persistence)",
                "severity": "CRITICAL",
            },
            {
                "timestamp": "2024-03-15T02:15:01Z",
                "source": "FileSystem",
                "artifact": r"C:\Users\victim\AppData\Roaming\evil.exe",
                "description": "File created: evil.exe (2.1 MB, signed=False)",
                "severity": "HIGH",
            },
            {
                "timestamp": "2024-03-15T02:15:05Z",
                "source": "WindowsEventLog",
                "artifact": "Security/4688",
                "description": "Process creation: evil.exe (PID 1337) by winlogon.exe",
                "severity": "HIGH",
            },
            {
                "timestamp": "2024-03-15T02:16:00Z",
                "source": "NetworkCapture",
                "artifact": "eth0.pcap",
                "description": "Outbound connection to 185.220.101.47:4444 (C2)",
                "severity": "CRITICAL",
            },
        ],
        "total_events_parsed": 84721,
        "filtered_to": 4,
    }


# ---------------------------------------------------------------------------
# Pydantic v2 Input Schemas
# ---------------------------------------------------------------------------

class VolatilityInput(BaseModel):
    """Input schema for the run_volatility_plugin tool."""
    image_path: StrictStr = Field(
        ...,
        description="Absolute path to the memory image file (e.g. /evidence/mem.raw)",
    )
    plugin: StrictStr = Field(
        ...,
        description="Volatility3 plugin name (e.g. windows.pslist, windows.netscan)",
    )

    @model_validator(mode="after")
    def validate_plugin_name(self) -> "VolatilityInput":
        """Ensure plugin name uses dot-notation and contains no shell-injection chars."""
        forbidden = {";", "&", "|", "$", "`", ">", "<", "\\n", "\\r"}
        for char in forbidden:
            if char in self.plugin:
                raise ValueError(f"Plugin name contains forbidden character: '{char}'")
        return self


class Log2TimelineInput(BaseModel):
    """Input schema for the run_log2timeline tool."""
    evidence_path: StrictStr = Field(
        ...,
        description="Absolute path to the evidence directory or image to parse",
    )
    output_format: StrictStr = Field(
        default="json",
        description="Output format: 'json' | 'l2tcsv' | 'dynamic'",
    )

    @model_validator(mode="after")
    def validate_output_format(self) -> "Log2TimelineInput":
        allowed = {"json", "l2tcsv", "dynamic"}
        if self.output_format not in allowed:
            raise ValueError(f"output_format must be one of {allowed}")
        return self


# ---------------------------------------------------------------------------
# MCP Tool Implementations
# ---------------------------------------------------------------------------

@mcp_tool("run_volatility_plugin")
async def run_volatility_plugin(params: VolatilityInput) -> dict[str, Any]:
    """
    Execute a Volatility3 plugin against a memory image.

    Security: runs in read-only mode — no plugins that write or modify the image
    are permitted.  Command construction is validated against _WRITE_CMD_DENYLIST
    before execution.

    Args:
        params: VolatilityInput — validated image path and plugin name.

    Returns:
        dict with plugin output or structured error information.
    """
    tool_name = "run_volatility_plugin"
    _audit_log(tool_name, params.model_dump())

    # Build the command as a list (no shell=True — prevents injection)
    cmd = ["vol", "-f", params.image_path, params.plugin, "--output=json"]

    try:
        # Read-only enforcement: scan command for write tokens
        _deny_write_operations(cmd)

        # --- MOCK EXECUTION ---
        # Production replacement:
        #   proc = await asyncio.create_subprocess_exec(
        #       *cmd,
        #       stdout=asyncio.subprocess.PIPE,
        #       stderr=asyncio.subprocess.PIPE,
        #   )
        #   stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        #   if proc.returncode != 0:
        #       raise OSError(f"vol exited {proc.returncode}: {stderr.decode()}")
        #   return json.loads(stdout.decode())
        result = await _mock_volatility3(params.image_path, params.plugin)
        return {"status": "ok", "tool": tool_name, "data": result}

    except PermissionError as exc:
        logger.warning("%s BLOCKED: %s", tool_name, exc)
        return {"status": "error", "tool": tool_name, "error_type": "PermissionError", "message": str(exc)}
    except TimeoutError:
        logger.error("%s TIMEOUT after 120s for image=%s", tool_name, params.image_path)
        return {"status": "error", "tool": tool_name, "error_type": "TimeoutError",
                "message": "Volatility3 timed out after 120 seconds"}
    except OSError as exc:
        logger.error("%s OSError: %s", tool_name, exc)
        return {"status": "error", "tool": tool_name, "error_type": "OSError", "message": str(exc)}
    except Exception as exc:
        logger.exception("Unexpected error in %s", tool_name)
        return {"status": "error", "tool": tool_name, "error_type": type(exc).__name__, "message": str(exc)}


@mcp_tool("run_log2timeline")
async def run_log2timeline(params: Log2TimelineInput) -> dict[str, Any]:
    """
    Run log2timeline (Plaso) to generate a forensic super-timeline.

    Parses artifacts from the given evidence_path and returns a condensed
    timeline of events ordered by timestamp.

    Args:
        params: Log2TimelineInput — validated evidence path and output format.

    Returns:
        dict containing timeline events or structured error information.
    """
    tool_name = "run_log2timeline"
    _audit_log(tool_name, params.model_dump())

    # Command structure — no shell=True
    cmd = [
        "log2timeline.py",
        "--storage-file", "/tmp/plaso_taxlens.dump",
        "--output", params.output_format,
        params.evidence_path,
    ]

    try:
        _deny_write_operations(cmd)

        # --- MOCK EXECUTION ---
        # Production replacement:
        #   proc = await asyncio.create_subprocess_exec(
        #       *cmd,
        #       stdout=asyncio.subprocess.PIPE,
        #       stderr=asyncio.subprocess.PIPE,
        #   )
        #   stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        #   if proc.returncode != 0:
        #       raise OSError(f"log2timeline exited {proc.returncode}: {stderr.decode()}")
        #   return json.loads(stdout.decode())
        result = await _mock_log2timeline(params.evidence_path, params.output_format)
        return {"status": "ok", "tool": tool_name, "data": result}

    except PermissionError as exc:
        logger.warning("%s BLOCKED: %s", tool_name, exc)
        return {"status": "error", "tool": tool_name, "error_type": "PermissionError", "message": str(exc)}
    except TimeoutError:
        logger.error("%s TIMEOUT after 300s for evidence=%s", tool_name, params.evidence_path)
        return {"status": "error", "tool": tool_name, "error_type": "TimeoutError",
                "message": "log2timeline timed out after 300 seconds"}
    except OSError as exc:
        logger.error("%s OSError: %s", tool_name, exc)
        return {"status": "error", "tool": tool_name, "error_type": "OSError", "message": str(exc)}
    except Exception as exc:
        logger.exception("Unexpected error in %s", tool_name)
        return {"status": "error", "tool": tool_name, "error_type": type(exc).__name__, "message": str(exc)}
