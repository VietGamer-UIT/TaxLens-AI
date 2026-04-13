# =============================================================================
# TaxLens-AI :: IR Agents Package
# =============================================================================
# LangGraph-powered Multi-Agent Incident Response (IR) system.
#
# Agent topology:
#   Supervisor ──► ForensicsAgent  (memory & timeline forensics)
#              ──► NetworkAgent    (Splunk SIEM + network C2 detection)
#              ──► DatabaseAgent   (threat intel & IOC enrichment)
#
# Entry point: build_ir_graph() from graph_builder.py
# State schema: IRAgentState from state.py
# =============================================================================

from .state import IRAgentState
from .graph_builder import build_ir_graph

__all__ = ["IRAgentState", "build_ir_graph"]
