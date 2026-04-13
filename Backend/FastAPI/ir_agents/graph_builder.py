# =============================================================================
# TaxLens-AI :: LangGraph IR Graph Builder
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Constructs and compiles the full StateGraph for the Incident Response
# Multi-Agent workflow.
#
# Graph topology:
#
#   START
#     │
#     ▼
#   [supervisor] ──► route_from_supervisor()
#                         │
#                         ├── "forensics_agent" ──► [forensics_agent] ──┐
#                         ├── "network_agent"   ──► [network_agent]   ──┤
#                         ├── "database_agent"  ──► [database_agent]  ──┤
#                         │                                              │
#                         │        ◄─────────────────────────────────────┘
#                         │        (all sub-agents route back to supervisor)
#                         │
#                         └── END  (when current_agent == "DONE")
#
# Key design decisions:
#   - All sub-agent → supervisor edges are unconditional (agents always
#     return to supervisor after completing their work).
#   - The conditional edge out of supervisor drives the dispatch logic.
#   - MAX_ITERATIONS guard lives in supervisor_node, not the graph edges,
#     to keep edge logic simple and auditable.
# =============================================================================

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from .state import IRAgentState
from .supervisor import supervisor_node
from .forensics_agent import forensics_agent_node
from .network_agent import network_agent_node
from .database_agent import database_agent_node

logger = logging.getLogger("taxlens.graph")

# ---------------------------------------------------------------------------
# Node name constants (single source of truth — avoids string typos)
# ---------------------------------------------------------------------------
NODE_SUPERVISOR      = "supervisor"
NODE_FORENSICS_AGENT = "forensics_agent"
NODE_NETWORK_AGENT   = "network_agent"
NODE_DATABASE_AGENT  = "database_agent"


# ---------------------------------------------------------------------------
# Conditional routing function
# ---------------------------------------------------------------------------

def route_from_supervisor(
    state: IRAgentState,
) -> Literal["forensics_agent", "network_agent", "database_agent", "__end__"]:
    """
    Conditional edge function: read state.current_agent and return the
    name of the next node (or '__end__') to direct the graph.

    Called by LangGraph after every supervisor_node execution.

    Args:
        state: Current IRAgentState with current_agent set by supervisor.

    Returns:
        One of the node name literals, or '__end__' to terminate the graph.
    """
    destination = state.get("current_agent", "DONE")

    if destination == NODE_FORENSICS_AGENT:
        logger.debug("[Router] supervisor → forensics_agent")
        return NODE_FORENSICS_AGENT

    if destination == NODE_NETWORK_AGENT:
        logger.debug("[Router] supervisor → network_agent")
        return NODE_NETWORK_AGENT

    if destination == NODE_DATABASE_AGENT:
        logger.debug("[Router] supervisor → database_agent")
        return NODE_DATABASE_AGENT

    # "DONE" or any unexpected value → terminate the graph
    logger.info("[Router] supervisor → END (current_agent=%s)", destination)
    return END


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_ir_graph() -> StateGraph:
    """
    Construct, configure, and compile the ThreatLens-IR StateGraph.

    Graph construction steps:
      1. Instantiate StateGraph with IRAgentState schema.
      2. Add all agent nodes (supervisor + 3 specialists).
      3. Set entry point to supervisor (intake phase).
      4. Add conditional edges from supervisor using route_from_supervisor().
      5. Add unconditional return edges from each specialist → supervisor.
      6. Compile and return the runnable graph.

    Returns:
        A compiled LangGraph StateGraph ready for .invoke() / .stream().

    Usage:
        graph = build_ir_graph()
        result = await graph.ainvoke({
            "incident_id":    "IR-2024-0047",
            "evidence_paths": ["/evidence/mem.raw"],
            "messages":       [],
            "error_log":      [],
            "retry_count":    0,
            "iteration_count": 0,
        })
    """
    logger.info("[GraphBuilder] Building TaxLens-AI StateGraph...")

    # ------------------------------------------------------------------
    # 1. Instantiate graph with typed state
    # ------------------------------------------------------------------
    graph = StateGraph(IRAgentState)

    # ------------------------------------------------------------------
    # 2. Register all nodes
    # ------------------------------------------------------------------
    graph.add_node(NODE_SUPERVISOR,      supervisor_node)
    graph.add_node(NODE_FORENSICS_AGENT, forensics_agent_node)
    graph.add_node(NODE_NETWORK_AGENT,   network_agent_node)
    graph.add_node(NODE_DATABASE_AGENT,  database_agent_node)

    logger.debug("[GraphBuilder] Nodes registered: %s", [
        NODE_SUPERVISOR, NODE_FORENSICS_AGENT, NODE_NETWORK_AGENT, NODE_DATABASE_AGENT
    ])

    # ------------------------------------------------------------------
    # 3. Set entry point
    # ------------------------------------------------------------------
    graph.set_entry_point(NODE_SUPERVISOR)

    # ------------------------------------------------------------------
    # 4. Conditional edges: supervisor → specialist agents (or END)
    # ------------------------------------------------------------------
    graph.add_conditional_edges(
        source=NODE_SUPERVISOR,
        path=route_from_supervisor,
        path_map={
            NODE_FORENSICS_AGENT: NODE_FORENSICS_AGENT,
            NODE_NETWORK_AGENT:   NODE_NETWORK_AGENT,
            NODE_DATABASE_AGENT:  NODE_DATABASE_AGENT,
            END:                  END,
        },
    )

    # ------------------------------------------------------------------
    # 5. Unconditional return edges: specialist → supervisor
    #    (Each agent sets current_agent = "supervisor" before returning)
    # ------------------------------------------------------------------
    graph.add_edge(NODE_FORENSICS_AGENT, NODE_SUPERVISOR)
    graph.add_edge(NODE_NETWORK_AGENT,   NODE_SUPERVISOR)
    graph.add_edge(NODE_DATABASE_AGENT,  NODE_SUPERVISOR)

    logger.debug("[GraphBuilder] Edges configured.")

    # ------------------------------------------------------------------
    # 6. Compile
    # ------------------------------------------------------------------
    compiled = graph.compile()

    logger.info("[GraphBuilder] StateGraph compiled successfully.")
    return compiled


# ---------------------------------------------------------------------------
# Quick-test helper (run: python -m Backend.FastAPI.ir_agents.graph_builder)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    import json
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    async def _run_demo():
        """End-to-end smoke test using all-mock data."""
        print("\n" + "=" * 70)
        print("  TaxLens-AI — LangGraph Multi-Agent Smoke Test")
        print("=" * 70)

        ir_graph = build_ir_graph()

        # Seed state that mimics an analyst-supplied incident brief
        initial_state: IRAgentState = {
            "incident_id":    "IR-2024-DEMO-001",
            "evidence_paths": [
                "/evidence/dc01_mem.raw",
                "/evidence/dc01_disk.E01",
                "/evidence/fw01.pcap",
            ],
            "messages":       [],
            "error_log":      [],
            "retry_count":    0,
            "iteration_count": 0,
        }

        print(f"\n[+] Invoking graph for incident: {initial_state['incident_id']}")
        print(f"[+] Evidence paths: {initial_state['evidence_paths']}\n")

        final_state: IRAgentState = await ir_graph.ainvoke(initial_state)

        print("\n" + "=" * 70)
        print("  FINAL SUPERVISOR REPORT")
        print("=" * 70)
        print(json.dumps(final_state.get("supervisor_report"), indent=2))

        print("\n" + "=" * 70)
        print(f"  Total iterations: {final_state.get('iteration_count')}")
        print(f"  Error log entries: {len(final_state.get('error_log', []))}")
        print(f"  Message trail length: {len(final_state.get('messages', []))}")
        print("=" * 70 + "\n")

    asyncio.run(_run_demo())
