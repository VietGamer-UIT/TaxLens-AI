# =============================================================================
# TaxLens-AI :: FastAPI Application Entry Point
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Wires together:
#   - AuditMiddleware  (HTTP request/response logging → PostgreSQL)
#   - Lifespan events  (DB init on startup, engine dispose on shutdown)
#   - API routers      (IR investigation + audit query endpoints)
#
# Run locally (development):
#   uvicorn Backend.FastAPI.main:app --reload --port 8000
#
# Run via Docker:
#   docker compose up --build
# =============================================================================

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .audit.database import init_db, close_db
from .audit.middleware import AuditMiddleware, set_audit_context
from .ir_agents import IRAgentState, build_ir_graph

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("taxlens.main")


# ---------------------------------------------------------------------------
# Application lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    - Startup  : Initialise PostgreSQL audit tables, compile IR graph.
    - Shutdown : Dispose async engine connection pool.
    """
    logger.info("[Startup] TaxLens-AI initialising...")

    # Create audit DB tables (idempotent — safe to call on existing schema)
    await init_db()
    logger.info("[Startup] Audit DB ready.")

    # Pre-compile the LangGraph IR graph once at startup (warm caches)
    app.state.ir_graph = build_ir_graph()
    logger.info("[Startup] LangGraph IR graph compiled.")

    yield  # Application is running

    logger.info("[Shutdown] Disposing database engine...")
    await close_db()
    logger.info("[Shutdown] TaxLens-AI shut down cleanly.")


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TaxLens-AI",
    description=(
        "TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer). "
        "Multi-Agent Incident Response & Observability Platform. "
        "Built for SANS FIND EVIL! and Splunk Agentic Ops Hackathons."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

# Audit middleware must be added BEFORE CORS so every request (including
# preflight OPTIONS) is captured in the audit log.
app.add_middleware(AuditMiddleware)

# ---------------------------------------------------------------------------
# CORS — Smart Origin Matching
# ---------------------------------------------------------------------------
# WHY allow_origin_regex instead of allow_origins=["..."]?
#
# GitHub Codespaces (and similar cloud IDEs) generate unpredictable,
# per-user, per-session hostnames like:
#   https://someuser-laughing-space-abc12345-8000.app.github.dev
#
# A static whitelist can NEVER enumerate these upfront.  The CORS spec
# (Fetch §4.6) allows the server to respond with a matching Origin header
# if it passes a regex check — Starlette (FastAPI's ASGI layer) implements
# this via the `allow_origin_regex` parameter.
#
# Regex anatomy:
#   http://localhost:\d+             — any local port (3000, 8000, etc.)
#   http://127\.0\.0\.1:\d+         — numeric loopback           
#   http://frontend:\d+              — Docker-internal service name
#   https://[\w-]+-\d+\.app\.github\.dev   — Codespaces port URLs
#   https://[\w-]+\.preview\.app\.github\.dev — Codespaces preview
#
# SECURITY NOTE: allow_credentials=True REQUIRES that allow_origins is NOT
# ["*"] (the spec forbids this combination).  The regex approach is both
# safe (specific pattern) and flexible (handles dynamic domains).
# ---------------------------------------------------------------------------
_CORS_ORIGIN_REGEX = (
    r"http://localhost:\d+"
    r"|http://127\.0\.0\.1:\d+"
    r"|https://.*-3000\.app\.github\.dev"
    r"|https://.*-3000\.preview\.app\.github\.dev"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],              # empty — regex handles all matching
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],           # Cho phép all methods
    allow_headers=["*"],           # Cho phép all headers
    expose_headers=["X-Incident-ID"],
)


# ---------------------------------------------------------------------------
# Pydantic v2 Request / Response Schemas
# ---------------------------------------------------------------------------

class InvestigateRequest(BaseModel):
    """Request body for the IR investigation endpoint."""
    incident_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique incident identifier (e.g. 'IR-2024-0047')",
        examples=["IR-2024-DEMO-001"],
    )
    evidence_paths: list[str] = Field(
        default_factory=list,
        description="Absolute paths to evidence artefacts (memory images, disk images, PCAPs)",
        examples=[["/evidence/dc01_mem.raw", "/evidence/fw01.pcap"]],
    )


class InvestigateResponse(BaseModel):
    """Response body returned after the IR graph completes."""
    graph_run_id:     str
    incident_id:      str
    status:           str
    severity:         str
    summary:          str
    iteration_count:  int
    completed_at:     str
    supervisor_report: dict[str, Any]


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """
    Liveness health check endpoint used by Docker HEALTHCHECK and CI/CD pipeline.
    Returns 200 OK when the application is running.
    """
    return {"status": "ok", "service": "TaxLens-AI"}


@app.post(
    "/api/v1/ir/investigate",
    response_model=InvestigateResponse,
    status_code=status.HTTP_200_OK,
    tags=["incident-response"],
    summary="Launch a multi-agent IR investigation",
)
async def investigate(request: InvestigateRequest) -> InvestigateResponse:
    """
    Trigger a full LangGraph multi-agent investigation for the given incident.

    Flow:
      1. Generates a unique graph_run_id for this invocation.
      2. Sets audit context (incident_id + graph_run_id) for all decorators.
      3. Invokes the pre-compiled StateGraph with the initial IRAgentState.
      4. Returns the supervisor_report from the final state.

    The audit middleware automatically logs this HTTP request/response.
    Each MCP tool call is logged by the @audit_tool_call decorator in mcp_servers.
    """
    graph_run_id = str(uuid.uuid4())

    # Propagate correlation IDs into async context for decorator capture
    set_audit_context(
        incident_id=request.incident_id,
        graph_run_id=graph_run_id,
    )

    # Build initial state
    initial_state: IRAgentState = {
        "incident_id":     request.incident_id,
        "evidence_paths":  request.evidence_paths or ["/evidence/sample_mem.raw"],
        "messages":        [],
        "error_log":       [],
        "retry_count":     0,
        "iteration_count": 0,
    }

    logger.info(
        "[API] Launching IR investigation — incident=%s run_id=%s",
        request.incident_id, graph_run_id,
    )

    try:
        final_state: IRAgentState = await app.state.ir_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("[API] IR graph failed for incident=%s", request.incident_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"IR graph execution failed: {type(exc).__name__}: {exc}",
        )

    report: dict[str, Any] = final_state.get("supervisor_report", {})

    return InvestigateResponse(
        graph_run_id=graph_run_id,
        incident_id=report.get("incident_id", request.incident_id),
        status=report.get("status", "unknown"),
        severity=report.get("severity", "unknown"),
        summary=report.get("summary", "No summary available."),
        iteration_count=report.get("iteration_count", 0),
        completed_at=report.get("completed_at", ""),
        supervisor_report=report,
    )


@app.get(
    "/api/v1/audit/events",
    tags=["audit"],
    summary="Query audit events for an incident",
)
async def get_audit_events(
    incident_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Return the most recent audit events for a given incident_id.

    This endpoint demonstrates the immutable audit trail to hackathon judges.
    In production, add pagination (cursor-based) and authentication.
    """
    from sqlalchemy import select, desc
    from .audit.database import AsyncSessionFactory
    from .audit.models import AuditEvent

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(AuditEvent)
            .where(AuditEvent.incident_id == incident_id)
            .order_by(desc(AuditEvent.recorded_at))
            .limit(min(limit, 500))     # Hard cap at 500 to prevent DoS
        )
        events = result.scalars().all()

    return {
        "incident_id": incident_id,
        "count": len(events),
        "events": [
            {
                "id":             str(e.id),
                "event_type":     e.event_type,
                "agent_name":     e.agent_name,
                "status":         e.status,
                "tool_name":      e.tool_name,
                "retry_attempt":  e.retry_attempt,
                "duration_ms":    e.duration_ms,
                "sha256_hash":    e.sha256_state_hash,
                "recorded_at":    e.recorded_at.isoformat() if e.recorded_at else None,
            }
            for e in events
        ],
    }
