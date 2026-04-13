# =============================================================================
# TaxLens-AI :: Audit Trail — Middleware & Decorator
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Two complementary capture mechanisms:
#
#   1. AuditMiddleware (Starlette BaseHTTPMiddleware)
#      Wraps every FastAPI HTTP request/response cycle to record the
#      endpoint called, status code, and latency.  Lightweight — runs
#      entirely in the background task queue to avoid blocking the main
#      response path.
#
#   2. @audit_tool_call decorator
#      Wraps individual MCP tool async functions to automatically capture
#      TOOL_CALLED → TOOL_SUCCEEDED / TOOL_FAILED events with full
#      input/output JSON and timing.  Designed to be applied at the
#      MCP server layer without modifying agent code.
#
#   3. audit_agent_event() helper
#      Standalone coroutine for agent nodes to manually emit
#      AGENT_STARTED / AGENT_COMPLETED / SUPERVISOR_ROUTED events.
#
# Security:
#   - All DB writes are parameterised ORM inserts (zero raw SQL).
#   - tool_input_json is sanitised to redact sensitive keys before storage.
#   - Errors in the audit path are caught and logged — they NEVER propagate
#     to the main application flow (audit must not break the system).
# =============================================================================

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from .database import AsyncSessionFactory
from .models import AgentName, AuditEvent, EventStatus, EventType

logger = logging.getLogger("taxlens.audit.middleware")

# ---------------------------------------------------------------------------
# Sensitive key redaction (GDPR / security hygiene)
# ---------------------------------------------------------------------------
_REDACTED_KEYS: frozenset[str] = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "x-apikey", "key", "credential", "private_key",
})


def _redact_sensitive(data: Any, depth: int = 0) -> Any:
    """
    Recursively redact sensitive keys from a dict/list before writing to DB.
    Maximum recursion depth: 10 (prevents stack overflow on deeply nested data).
    """
    if depth > 10:
        return data
    if isinstance(data, dict):
        return {
            k: ("***REDACTED***" if k.lower() in _REDACTED_KEYS else _redact_sensitive(v, depth + 1))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_redact_sensitive(item, depth + 1) for item in data]
    return data


def _compute_state_hash(snapshot: dict) -> str:
    """
    Compute SHA-256 hex digest of the canonical JSON representation of a
    state snapshot.  Uses sort_keys=True and separators=(',', ':') for a
    deterministic byte sequence regardless of insertion order.
    """
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_json(obj: Any, max_bytes: int = 65_536) -> dict | None:
    """
    Attempt to JSON-serialise an arbitrary object into a dict safe for JSONB.
    Truncates string representations larger than max_bytes to prevent
    bloating the audit table with enormous payloads.
    """
    try:
        if obj is None:
            return None
        if isinstance(obj, dict):
            serialised = json.dumps(obj, default=str)
            if len(serialised) > max_bytes:
                return {"_truncated": True, "preview": serialised[:max_bytes]}
            return obj
        # Fallback: wrap non-dict in a container
        return {"value": str(obj)[:max_bytes]}
    except Exception:
        return {"_serialisation_error": True}


# ---------------------------------------------------------------------------
# Low-level DB writer (fire-and-forget background task)
# ---------------------------------------------------------------------------

async def _write_audit_event(event_kwargs: dict[str, Any]) -> None:
    """
    Persist a single AuditEvent row to PostgreSQL.

    Runs as a background task — errors here are LOGGED but never re-raised
    so that audit failures cannot disrupt the main IR agent pipeline.
    """
    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                event = AuditEvent(**event_kwargs)
                session.add(event)
        # session.begin() auto-commits on context exit
    except Exception as exc:
        # Audit must not crash the application — swallow and log only
        logger.error("[AuditWriter] Failed to persist audit event: %s — %s", type(exc).__name__, exc)


def _fire_audit(event_kwargs: dict[str, Any]) -> None:
    """
    Schedule _write_audit_event as a background asyncio task.
    Safe to call from both sync and async contexts.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write_audit_event(event_kwargs))
    except RuntimeError:
        # No running event loop (e.g. in unit tests)
        asyncio.run(_write_audit_event(event_kwargs))


# =============================================================================
# 1. HTTP Request Audit Middleware
# =============================================================================

class AuditMiddleware(BaseHTTPMiddleware):
    """
    Starlette BaseHTTPMiddleware that records every HTTP request/response pair.

    Captures:
      - HTTP method, path, status code, latency (ms)
      - X-Incident-ID and X-Graph-Run-ID request headers (if present)
      - Stores as EventType.AGENT_STARTED / AGENT_COMPLETED using
        AgentName.SYSTEM to distinguish HTTP-level events from agent events.

    Performance note:
      - DB write is dispatched as a non-blocking asyncio background task.
      - The middleware adds < 1 ms of overhead to the critical path.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_ns: int = time.perf_counter_ns()

        # Extract correlation IDs from request headers (set by API callers)
        incident_id:  str = request.headers.get("X-Incident-ID",  "HTTP")
        graph_run_id: str = request.headers.get("X-Graph-Run-ID", str(uuid.uuid4()))

        # --- Emit REQUEST event (fire-and-forget) ---
        _fire_audit({
            "incident_id":  incident_id,
            "graph_run_id": graph_run_id,
            "event_type":   EventType.AGENT_STARTED,
            "agent_name":   AgentName.SYSTEM,
            "status":       EventStatus.OK,
            "tool_name":    f"HTTP {request.method} {request.url.path}",
            "tool_input_json": {
                "method": request.method,
                "path":   str(request.url.path),
                "query":  str(request.url.query),
            },
        })

        # --- Process the actual request ---
        response: Response = await call_next(request)

        duration_ms: int = (time.perf_counter_ns() - start_ns) // 1_000_000

        # --- Emit RESPONSE event (fire-and-forget) ---
        status = EventStatus.OK if response.status_code < 400 else EventStatus.ERROR
        _fire_audit({
            "incident_id":   incident_id,
            "graph_run_id":  graph_run_id,
            "event_type":    EventType.AGENT_COMPLETED,
            "agent_name":    AgentName.SYSTEM,
            "status":        status,
            "tool_name":     f"HTTP {request.method} {request.url.path}",
            "tool_output_json": {"status_code": response.status_code},
            "duration_ms":   duration_ms,
        })

        return response


# =============================================================================
# 2. MCP Tool Call Audit Decorator
# =============================================================================

def audit_tool_call(
    event_type_success: EventType = EventType.TOOL_SUCCEEDED,
    event_type_failure: EventType = EventType.TOOL_FAILED,
    agent_name: AgentName = AgentName.SYSTEM,
):
    """
    Decorator factory that wraps an async MCP tool function to automatically
    capture TOOL_CALLED → TOOL_SUCCEEDED / TOOL_FAILED audit events.

    Usage (apply to MCP tool implementations):
        @mcp_tool("run_volatility_plugin")
        @audit_tool_call(agent_name=AgentName.FORENSICS_AGENT)
        async def run_volatility_plugin(params: VolatilityInput) -> dict:
            ...

    The decorator:
      1. Emits TOOL_CALLED event with redacted input JSON before execution.
      2. Times the tool execution wall-clock.
      3. On success: emits TOOL_SUCCEEDED with output JSON.
      4. On exception: emits TOOL_FAILED with error details, then re-raises
         so the agent's self-correction logic can handle it normally.

    Args:
        event_type_success : EventType to use on clean completion.
        event_type_failure : EventType to use on exception.
        agent_name         : AgentName owning this tool call.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Derive incident/run IDs from input Pydantic model if available
            # (Contextvar-based approach keeps decorator agent-agnostic)
            input_obj = args[0] if args else kwargs.get("params")
            raw_input = input_obj.model_dump() if hasattr(input_obj, "model_dump") else {}
            safe_input = _safe_json(_redact_sensitive(raw_input))

            tool_name = fn.__name__
            incident_id  = _current_incident_id.get("UNKNOWN")
            graph_run_id = _current_graph_run_id.get(str(uuid.uuid4()))

            # ── Pre-call event ──────────────────────────────────────────
            _fire_audit({
                "incident_id":     incident_id,
                "graph_run_id":    graph_run_id,
                "event_type":      EventType.TOOL_CALLED,
                "agent_name":      agent_name,
                "status":          EventStatus.OK,
                "tool_name":       tool_name,
                "tool_input_json": safe_input,
            })

            start_ns = time.perf_counter_ns()
            try:
                result = await fn(*args, **kwargs)
                duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

                safe_output = _safe_json(_redact_sensitive(result) if isinstance(result, dict) else result)

                # ── Success event ───────────────────────────────────────
                _fire_audit({
                    "incident_id":      incident_id,
                    "graph_run_id":     graph_run_id,
                    "event_type":       event_type_success,
                    "agent_name":       agent_name,
                    "status":           EventStatus.OK,
                    "tool_name":        tool_name,
                    "tool_input_json":  safe_input,
                    "tool_output_json": safe_output,
                    "duration_ms":      duration_ms,
                })
                return result

            except Exception as exc:
                duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

                # ── Failure event ───────────────────────────────────────
                _fire_audit({
                    "incident_id":    incident_id,
                    "graph_run_id":   graph_run_id,
                    "event_type":     event_type_failure,
                    "agent_name":     agent_name,
                    "status":         EventStatus.ERROR,
                    "tool_name":      tool_name,
                    "tool_input_json": safe_input,
                    "error_type":     type(exc).__name__,
                    "error_message":  str(exc)[:4096],
                    "duration_ms":    duration_ms,
                })
                raise   # Re-raise so agent self-correction handles it

        return wrapper
    return decorator


# =============================================================================
# 3. Agent Node Event Helper
# =============================================================================

async def audit_agent_event(
    event_type:   EventType,
    agent_name:   AgentName,
    incident_id:  str,
    graph_run_id: str,
    status:       EventStatus = EventStatus.OK,
    tool_name:    Optional[str] = None,
    state_snapshot: Optional[dict] = None,
    duration_ms:  Optional[int] = None,
    token_prompt:     int = 0,
    token_completion: int = 0,
    error_type:    Optional[str] = None,
    error_message: Optional[str] = None,
    retry_attempt: int = 0,
) -> None:
    """
    Emit a structured audit event from an agent node.

    Designed to be called at the start/end of each LangGraph node function:

        await audit_agent_event(
            event_type=EventType.AGENT_STARTED,
            agent_name=AgentName.FORENSICS_AGENT,
            incident_id=state["incident_id"],
            graph_run_id=state["graph_run_id"],
        )

    Args:
        event_type       : EventType — what kind of event this is.
        agent_name       : AgentName — which agent is reporting.
        incident_id      : From IRAgentState.
        graph_run_id     : Unique ID for the current .ainvoke() session.
        status           : EventStatus outcome.
        tool_name        : Optional MCP tool name (for tool-level events).
        state_snapshot   : Optional partial state dict to hash and store.
        duration_ms      : Wall-clock duration in milliseconds.
        token_prompt     : LLM prompt tokens consumed.
        token_completion : LLM completion tokens generated.
        error_type       : Exception class name on failure.
        error_message    : Human-readable error description.
        retry_attempt    : Self-correction attempt number (0 = first try).
    """
    token_total = token_prompt + token_completion

    # Compute state hash if snapshot provided
    safe_snapshot: dict | None = None
    sha256_hash:   str | None  = None
    if state_snapshot:
        safe_snapshot = _safe_json(_redact_sensitive(state_snapshot))
        if safe_snapshot:
            sha256_hash = _compute_state_hash(safe_snapshot)

    _fire_audit({
        "incident_id":         incident_id,
        "graph_run_id":        graph_run_id,
        "event_type":          event_type,
        "agent_name":          agent_name,
        "status":              status,
        "tool_name":           tool_name,
        "duration_ms":         duration_ms,
        "token_prompt":        token_prompt,
        "token_completion":    token_completion,
        "token_total":         token_total,
        "state_snapshot_json": safe_snapshot,
        "sha256_state_hash":   sha256_hash,
        "error_type":          error_type,
        "error_message":       error_message[:4096] if error_message else None,
        "retry_attempt":       retry_attempt,
    })


# =============================================================================
# 4. Context variables for correlation ID propagation
# =============================================================================
# Using stdlib contextvars instead of threading.local — safe in async code.
# Agent nodes set these at the start of each invocation so decorators can
# read incident_id / graph_run_id without needing to pass them explicitly.
# =============================================================================

from contextvars import ContextVar  # noqa: E402 — placed after type hints

_current_incident_id:  ContextVar[str] = ContextVar("incident_id",  default="UNKNOWN")
_current_graph_run_id: ContextVar[str] = ContextVar("graph_run_id", default="UNKNOWN")


def set_audit_context(incident_id: str, graph_run_id: str) -> None:
    """
    Set the current incident and graph run IDs in the async context.

    Call this at the start of each LangGraph .ainvoke() to ensure all
    @audit_tool_call decorators pick up the correct correlation IDs.

        run_id = str(uuid.uuid4())
        set_audit_context(incident_id="IR-2024-0047", graph_run_id=run_id)
        result = await ir_graph.ainvoke(initial_state)
    """
    _current_incident_id.set(incident_id)
    _current_graph_run_id.set(graph_run_id)
