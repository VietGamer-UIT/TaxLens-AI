# =============================================================================
# TaxLens-AI :: MCP Servers Package
# =============================================================================
# This package exposes a unified registry of all Model Context Protocol (MCP)
# tool servers used by the LangGraph IR agents.
#
# Servers included:
#   - forensics_mcp   : Wraps SIFT/Volatility3 & log2timeline/Plaso
#   - splunk_mcp      : Wraps Splunk REST API search endpoints
#   - threat_intel_mcp: Wraps VirusTotal v3 & AbuseIPDB APIs
# =============================================================================

from .forensics_mcp import FORENSICS_TOOL_REGISTRY
from .splunk_mcp import SPLUNK_TOOL_REGISTRY
from .threat_intel_mcp import THREAT_INTEL_TOOL_REGISTRY

# Master registry — all callable MCP tools across every server.
# Keys  : globally unique tool names (snake_case)
# Values: async callables that accept a Pydantic-v2 input model instance
MCP_TOOL_REGISTRY: dict = {
    **FORENSICS_TOOL_REGISTRY,
    **SPLUNK_TOOL_REGISTRY,
    **THREAT_INTEL_TOOL_REGISTRY,
}

__all__ = [
    "MCP_TOOL_REGISTRY",
    "FORENSICS_TOOL_REGISTRY",
    "SPLUNK_TOOL_REGISTRY",
    "THREAT_INTEL_TOOL_REGISTRY",
]
