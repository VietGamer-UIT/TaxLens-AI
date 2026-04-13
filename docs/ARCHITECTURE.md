# TaxLens-AI — System Architecture

> **TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)**  
> *Multi-Agent Incident Response & Observability Platform*

---

## 1. Overview

TaxLens-AI is designed around a **LangGraph StateGraph** that orchestrates four specialised AI agents. The architecture deliberately separates concerns across domain-specific agents rather than using a single monolithic LLM call. This document explains the design decisions, the context window management strategy, and the full agent communication flow.

---

## 2. Why LangGraph? The Context Window Problem

### The Problem with Monolithic IR Prompts

A naive approach to AI-driven incident response would feed all available evidence — raw memory dumps, Splunk SPL results, threat intelligence lookups, and timeline artefacts — into a single LLM prompt. This approach fails at production scale for three reasons:

| Problem | Impact |
|---|---|
| **Context Window Overflow** | A full Volatility3 `pslist` output + 3 SPL search results + VirusTotal reports can easily exceed 128K tokens, causing truncation or API errors. |
| **Loss of Analytical Depth** | When a 128K context is filled with raw data, the LLM spends its "attention" on data retrieval rather than reasoning. |
| **No Audit Trail** | A single-shot prompt produces no machine-readable intermediate steps — a SANS forensic requirement is violated. |

### The LangGraph Solution: Divide and Conquer

TaxLens-AI decomposes the IR workflow into **atomic, bounded sub-tasks**, each handled by a specialist agent with its own focused context window:

```
Total Incident Context  →  split across 3 specialist agents
                            each consuming < 8K tokens per invocation
```

Each specialist agent:
1. Receives **only the data it needs** (e.g., Forensics Agent only sees memory image paths, not Splunk results).
2. Produces a **structured JSON findings object** (not raw prose) which is compact and machine-parseable.
3. Returns control to the Supervisor, which accumulates findings without holding raw evidence in its own context.

---

## 3. Agent Topology

### 3.1 Nodes

| Agent | Node Name | Primary Responsibility |
|---|---|---|
| **Supervisor** | `supervisor` | Orchestration, routing, report synthesis |
| **Forensics Agent** | `forensics_agent` | Memory forensics (Volatility3), timeline generation (Plaso/log2timeline) |
| **Network Agent** | `network_agent` | SIEM correlation (Splunk SPL), Notable Event triage |
| **Database Agent** | `database_agent` | IOC enrichment (VirusTotal v3, AbuseIPDB v2) |

### 3.2 Graph Topology (ASCII)

```
START
  │
  ▼
[supervisor] ──► route_from_supervisor()
                      │
                      ├── "forensics_agent" ──► [forensics_agent] ──┐
                      ├── "network_agent"   ──► [network_agent]   ──┤
                      ├── "database_agent"  ──► [database_agent]  ──┤
                      │                                              │
                      │        ◄─────────── (unconditional edge) ────┘
                      │        (all sub-agents return to supervisor)
                      │
                      └── END  (when current_agent == "DONE")
```

### 3.3 Mermaid Flow Diagram

```mermaid
graph TD
    START([▶ START]) --> SUP[Supervisor Node\nrouting · synthesis]

    SUP -->|route_from_supervisor| R{Decision}

    R -->|forensics_agent| FA[🔬 Forensics Agent\nVolatility3 · Plaso]
    R -->|network_agent|   NA[📡 Network Agent\nSplunk SPL · ES Notables]
    R -->|database_agent|  DA[🗄️ Database Agent\nVirusTotal · AbuseIPDB]
    R -->|DONE|            END_NODE([⏹ END])

    FA -->|forensics_findings| SUP
    NA -->|network_findings|   SUP
    DA -->|database_findings|  SUP

    style SUP  fill:#1a1a2e,color:#fff,stroke:#4a9eff
    style FA   fill:#16213e,color:#fff,stroke:#4a9eff
    style NA   fill:#16213e,color:#fff,stroke:#4a9eff
    style DA   fill:#16213e,color:#fff,stroke:#4a9eff
    style END_NODE fill:#0f3460,color:#fff
```

---

## 4. Shared State: `IRAgentState`

All agents communicate exclusively through a **typed Python TypedDict** — `IRAgentState`. There is no direct agent-to-agent message passing; all data flows through the centralised state object managed by LangGraph.

```python
class IRAgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────
    incident_id:        str               # Analyst-supplied incident ID
    evidence_paths:     list[str]         # Absolute paths to artefacts

    # ── Control flow ───────────────────────────────────────
    current_agent:      str               # Target node for next dispatch
    iteration_count:    int               # Global graph tick counter
    retry_count:        int               # Per-agent retry counter (max 3)

    # ── Agent findings (accumulated progressively) ─────────
    forensics_findings: dict | None       # Populated by forensics_agent
    network_findings:   dict | None       # Populated by network_agent
    database_findings:  dict | None       # Populated by database_agent

    # ── Output ─────────────────────────────────────────────
    supervisor_report:  dict[str, Any]    # Final compiled IR report

    # ── Audit log ──────────────────────────────────────────
    messages:           list[dict]        # Agent message audit trail
    error_log:          list[dict]        # Tool error records
```

**Why TypedDict over Pydantic?** LangGraph requires the state schema to be a `TypedDict` for its internal graph diffing and merging mechanism. Pydantic is used for MCP tool *inputs*, not graph state.

---

## 5. Supervisor Routing Logic

The Supervisor uses a **deterministic, rule-based router** — no LLM inference for routing decisions. This design choice is intentional:

| Decision | Rationale |
|---|---|
| **No LLM routing** | Deterministic routing = zero routing hallucination risk; full auditability of every decision. |
| **Fixed dispatch order** | `forensics → network → database` ensures downstream agents (Database) can enrich IOCs found by upstream agents (Forensics, Network). |
| **Skip-if-complete** | If an agent's findings slot is already populated (`status == "ok"`), the Supervisor skips it — enabling partial reruns without redundant work. |

### Routing Pseudocode

```python
AGENTS_IN_ORDER = ["forensics_agent", "network_agent", "database_agent"]

def _decide_next_agent(state):
    for agent in AGENTS_IN_ORDER:
        findings = state.get(f"{agent.replace('_agent', '')}_findings")
        if findings is None or findings.get("status") not in {"ok", "exhausted_retries"}:
            return agent  # First incomplete agent
    return None  # All done → compile final report
```

---

## 6. Self-Correction Mechanism

Each specialist agent implements a **retry loop** (max 3 attempts) for transient tool failures:

```
Tool Call Attempt 1
  └── Success → return findings (status=ok)
  └── Failure → log error, increment retry_count

Tool Call Attempt 2 (if retry_count < 3)
  └── Success → return findings (status=ok)
  └── Failure → log error, increment retry_count

Tool Call Attempt 3 (if retry_count < 3)
  └── Success → return findings (status=ok)
  └── Failure → return findings (status=exhausted_retries)
```

Retried errors are written to `state["error_log"]` and to the PostgreSQL `audit_events` table with `retry_attempt > 0` for forensic traceability.

---

## 7. Iteration Guard

The Supervisor enforces a **global iteration cap** (`MAX_ITERATIONS = 15`). If the graph has not reached a terminal state within 15 ticks (e.g., due to cascading retries), the Supervisor forces a `status="partial"` report and terminates. This prevents infinite loops and runaway LLM token consumption.

---

## 8. Audit Integration

Every state transition is reflected in the PostgreSQL `audit_events` table via fire-and-forget `asyncio` background tasks:

```
Agent Start    → AGENT_STARTED  event
Tool Call      → TOOL_CALLED    event (with input redaction)
Tool Success   → TOOL_SUCCEEDED event (with output & duration_ms)
Tool Failure   → TOOL_FAILED    event (with error_type, retry_attempt)
Supervisor     → SUPERVISOR_ROUTED / SUPERVISOR_COMPLETED events
Graph End      → GRAPH_COMPLETED event
```

Each event carries a `sha256_state_hash` — a SHA-256 digest of the canonical JSON serialisation of the current `IRAgentState` snapshot — enabling tamper detection of the audit ledger.

---

> *TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer) — Architecture Document v1.0*
