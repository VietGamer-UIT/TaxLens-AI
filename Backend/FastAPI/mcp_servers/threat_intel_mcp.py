# =============================================================================
# TaxLens-AI :: Threat Intelligence MCP Server
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Wraps external threat intelligence APIs:
#   - VirusTotal v3 API : file hash & IP reputation lookup
#   - AbuseIPDB v2 API  : IP abuse confidence scoring
#
# Authentication:
#   - VirusTotal : x-apikey header  (env: VIRUSTOTAL_API_KEY)
#   - AbuseIPDB  : Key header       (env: ABUSEIPDB_API_KEY)
#
# NOTE (Hackathon): All API calls are MOCKED with realistic threat intel
# payloads.  Replace _mock_* functions with live aiohttp calls for production.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field, StrictStr, model_validator

logger = logging.getLogger("taxlens.mcp.threat_intel")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VIRUSTOTAL_API_KEY: str = os.getenv("VIRUSTOTAL_API_KEY", "MOCK_VT_KEY")
ABUSEIPDB_API_KEY: str = os.getenv("ABUSEIPDB_API_KEY", "MOCK_ABUSEIPDB_KEY")
REQUEST_TIMEOUT_S: int = 30

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
THREAT_INTEL_TOOL_REGISTRY: dict[str, Callable] = {}


def mcp_tool(name: str):
    """Decorator that registers a coroutine into THREAT_INTEL_TOOL_REGISTRY."""
    def decorator(fn: Callable) -> Callable:
        THREAT_INTEL_TOOL_REGISTRY[name] = fn
        logger.debug("Registered Threat Intel MCP tool: %s", name)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit_log(tool: str, params: dict[str, Any]) -> None:
    """Emit a structured audit event for evidence chain compliance."""
    entry = {
        "event": "mcp_tool_invoked",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "server": "threat_intel_mcp",
        "tool": tool,
        "params": params,
    }
    logger.info(json.dumps(entry))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
_MD5_RE   = re.compile(r"^[a-fA-F0-9]{32}$")
_SHA1_RE  = re.compile(r"^[a-fA-F0-9]{40}$")
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


def _is_valid_ip(value: str) -> bool:
    return bool(_IPV4_RE.match(value))


def _is_valid_hash(value: str) -> bool:
    return any(p.match(value) for p in (_MD5_RE, _SHA1_RE, _SHA256_RE))


# ---------------------------------------------------------------------------
# Mock helpers — replace with live aiohttp calls in production
# ---------------------------------------------------------------------------

async def _mock_lookup_ip(ip_address: str) -> dict[str, Any]:
    """Simulate VirusTotal /ip_addresses/<ip> + AbuseIPDB /check responses."""
    await asyncio.sleep(0.12)

    is_malicious = ip_address == "185.220.101.47"  # Seed a "known bad" IP

    vt_data = {
        "id": ip_address,
        "type": "ip_address",
        "attributes": {
            "last_analysis_stats": {
                "malicious": 47 if is_malicious else 0,
                "suspicious": 3 if is_malicious else 0,
                "undetected": 5,
                "harmless": 10 if not is_malicious else 0,
            },
            "country": "DE" if is_malicious else "US",
            "as_owner": "Frantech Solutions" if is_malicious else "Google LLC",
            "asn": 53667 if is_malicious else 15169,
            "tags": ["tor", "vpn", "proxy"] if is_malicious else [],
            "reputation": -85 if is_malicious else 0,
            "last_modification_date": "2024-03-14T20:00:00Z",
        },
    }
    abuseipdb_data = {
        "ipAddress": ip_address,
        "isPublic": True,
        "ipVersion": 4,
        "isWhitelisted": False,
        "abuseConfidenceScore": 97 if is_malicious else 0,
        "countryCode": "DE" if is_malicious else "US",
        "usageType": "Data Center/Web Hosting/Transit" if is_malicious else "Fixed Line ISP",
        "isp": "Frantech Solutions" if is_malicious else "Google",
        "domain": "buyvm.net" if is_malicious else "google.com",
        "totalReports": 412 if is_malicious else 0,
        "numDistinctUsers": 87 if is_malicious else 0,
        "lastReportedAt": "2024-03-14T21:43:00+00:00" if is_malicious else None,
    }
    verdict = "MALICIOUS" if is_malicious else "CLEAN"
    return {
        "ip_address": ip_address,
        "verdict": verdict,
        "virustotal": vt_data,
        "abuseipdb": abuseipdb_data,
    }


async def _mock_lookup_hash(file_hash: str) -> dict[str, Any]:
    """Simulate VirusTotal /files/<hash> response."""
    await asyncio.sleep(0.12)

    # Seed a "known bad" SHA256 for demonstration
    EVIL_HASH = "d41d8cd98f00b204e9800998ecf8427e" + "0" * 16  # padded 48 char for demo
    is_malicious = "4c1d" in file_hash.lower() or "dead" in file_hash.lower()

    vt_data = {
        "id": file_hash,
        "type": "file",
        "attributes": {
            "meaningful_name": "evil.exe" if is_malicious else "unknown.bin",
            "size": 2183168 if is_malicious else 512,
            "type_description": "Win32 EXE",
            "last_analysis_stats": {
                "malicious": 58 if is_malicious else 0,
                "suspicious": 4 if is_malicious else 1,
                "undetected": 2,
                "harmless": 0,
            },
            "popular_threat_classification": {
                "suggested_threat_label": "trojan.metasploit/meterpreter" if is_malicious else "grayware",
                "popular_threat_category": [
                    {"value": "trojan", "count": 42},
                ],
                "popular_threat_name": [
                    {"value": "Meterpreter", "count": 38},
                    {"value": "Metasploit", "count": 20},
                ],
            } if is_malicious else {},
            "pe_info": {
                "imphash": "a5d4e7c3b29f1087654321abcdef1234",
                "compilation_timestamp": "2024-03-10T14:22:11Z",
                "sections": [
                    {"name": ".text", "virtual_size": 802816, "entropy": 7.9,
                     "ALERT": "High entropy — possible packing" if is_malicious else None},
                ],
            },
        },
    }
    verdict = "MALICIOUS" if is_malicious else "CLEAN"
    return {
        "file_hash": file_hash,
        "hash_type": "sha256" if len(file_hash) == 64 else "md5" if len(file_hash) == 32 else "sha1",
        "verdict": verdict,
        "virustotal": vt_data,
    }


# ---------------------------------------------------------------------------
# Pydantic v2 Input Schemas
# ---------------------------------------------------------------------------

class IPLookupInput(BaseModel):
    """Input schema for the lookup_ip tool."""
    ip_address: StrictStr = Field(
        ...,
        description="IPv4 address to look up in VirusTotal and AbuseIPDB",
    )

    @model_validator(mode="after")
    def validate_ip_format(self) -> "IPLookupInput":
        if not _is_valid_ip(self.ip_address):
            raise ValueError(f"'{self.ip_address}' is not a valid IPv4 address")
        return self


class HashLookupInput(BaseModel):
    """Input schema for the lookup_hash tool."""
    file_hash: StrictStr = Field(
        ...,
        description="MD5, SHA-1, or SHA-256 hash of the file to look up",
    )

    @model_validator(mode="after")
    def validate_hash_format(self) -> "HashLookupInput":
        if not _is_valid_hash(self.file_hash):
            raise ValueError(
                f"'{self.file_hash}' is not a valid MD5 (32), SHA-1 (40), or SHA-256 (64) hex hash"
            )
        return self


# ---------------------------------------------------------------------------
# MCP Tool Implementations
# ---------------------------------------------------------------------------

@mcp_tool("lookup_ip")
async def lookup_ip(params: IPLookupInput) -> dict[str, Any]:
    """
    Look up an IP address against VirusTotal v3 and AbuseIPDB.

    Queries:
      - VT  : GET https://www.virustotal.com/api/v3/ip_addresses/<ip>
      - AIDB: GET https://api.abuseipdb.com/api/v2/check?ipAddress=<ip>

    Returns a combined verdict with raw API responses for audit trail.

    Args:
        params: IPLookupInput — validated IPv4 address.

    Returns:
        dict with verdict, VT data, AbuseIPDB data, or structured error.
    """
    tool_name = "lookup_ip"
    _audit_log(tool_name, params.model_dump())

    # --- Production HTTP skeleton (commented out for mock mode) ---
    # async with aiohttp.ClientSession() as session:
    #     # VirusTotal lookup
    #     async with session.get(
    #         f"https://www.virustotal.com/api/v3/ip_addresses/{params.ip_address}",
    #         headers={"x-apikey": VIRUSTOTAL_API_KEY},
    #         timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
    #     ) as vt_resp:
    #         vt_resp.raise_for_status()
    #         vt_data = (await vt_resp.json())["data"]
    #
    #     # AbuseIPDB lookup
    #     async with session.get(
    #         "https://api.abuseipdb.com/api/v2/check",
    #         headers={"Key": ABUSEIPDB_API_KEY, "Accept": "application/json"},
    #         params={"ipAddress": params.ip_address, "maxAgeInDays": 90},
    #         timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
    #     ) as ai_resp:
    #         ai_resp.raise_for_status()
    #         abuseipdb_data = (await ai_resp.json())["data"]
    #
    #     verdict = "MALICIOUS" if (
    #         vt_data["attributes"]["last_analysis_stats"]["malicious"] > 5
    #         or abuseipdb_data["abuseConfidenceScore"] > 50
    #     ) else "CLEAN"
    #     return {"status": "ok", "tool": tool_name, "data": {
    #         "ip_address": params.ip_address, "verdict": verdict,
    #         "virustotal": vt_data, "abuseipdb": abuseipdb_data,
    #     }}

    try:
        result = await asyncio.wait_for(
            _mock_lookup_ip(params.ip_address),
            timeout=REQUEST_TIMEOUT_S,
        )
        return {"status": "ok", "tool": tool_name, "data": result}

    except asyncio.TimeoutError:
        logger.error("%s TIMEOUT for ip=%s", tool_name, params.ip_address)
        return {"status": "error", "tool": tool_name, "error_type": "TimeoutError",
                "message": f"Threat intel lookup timed out after {REQUEST_TIMEOUT_S}s"}
    except Exception as exc:
        logger.exception("Unexpected error in %s", tool_name)
        return {"status": "error", "tool": tool_name, "error_type": type(exc).__name__, "message": str(exc)}


@mcp_tool("lookup_hash")
async def lookup_hash(params: HashLookupInput) -> dict[str, Any]:
    """
    Look up a file hash (MD5/SHA-1/SHA-256) against VirusTotal v3.

    Queries:
      - VT: GET https://www.virustotal.com/api/v3/files/<hash>

    Returns PE metadata, detection stats, and threat classification.

    Args:
        params: HashLookupInput — validated file hash.

    Returns:
        dict with verdict, VT data, or structured error.
    """
    tool_name = "lookup_hash"
    _audit_log(tool_name, params.model_dump())

    # --- Production HTTP skeleton (commented out for mock mode) ---
    # async with aiohttp.ClientSession() as session:
    #     async with session.get(
    #         f"https://www.virustotal.com/api/v3/files/{params.file_hash}",
    #         headers={"x-apikey": VIRUSTOTAL_API_KEY},
    #         timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
    #     ) as resp:
    #         resp.raise_for_status()
    #         vt_data = (await resp.json())["data"]
    #         malicious_count = vt_data["attributes"]["last_analysis_stats"]["malicious"]
    #         verdict = "MALICIOUS" if malicious_count > 5 else "CLEAN"
    #         return {"status": "ok", "tool": tool_name, "data": {
    #             "file_hash": params.file_hash, "verdict": verdict, "virustotal": vt_data,
    #         }}

    try:
        result = await asyncio.wait_for(
            _mock_lookup_hash(params.file_hash),
            timeout=REQUEST_TIMEOUT_S,
        )
        return {"status": "ok", "tool": tool_name, "data": result}

    except asyncio.TimeoutError:
        logger.error("%s TIMEOUT for hash=%s", tool_name, params.file_hash[:16])
        return {"status": "error", "tool": tool_name, "error_type": "TimeoutError",
                "message": f"Hash lookup timed out after {REQUEST_TIMEOUT_S}s"}
    except Exception as exc:
        logger.exception("Unexpected error in %s", tool_name)
        return {"status": "error", "tool": tool_name, "error_type": type(exc).__name__, "message": str(exc)}
