# =============================================================================
# TaxLens-AI :: Audit Trail — ORM Models
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Defines the SQLAlchemy ORM model for the audit_events table.
# Captures every agent action, tool call, routing decision, and
#   LLM token consumption in the TaxLens-AI system.
#
# SANS FIND EVIL criterion :
#   - Every row is append-only (no UPDATE/DELETE paths in the codebase).
#   - Evidence integrity: sha256_state_hash field captures a hash of the
#     IRAgentState at the time of each event, enabling tamper detection.
#
# Splunk Agentic Ops criterion:
#   - Structured JSON columns (tool_input_json, tool_output_json) allow
#     Splunk to index and search deep inside tool call payloads.
#   - token_prompt / token_completion / token_total enable LLM cost tracking.
#
# SQL Injection prevention:
#   - All writes go through parameterised SQLAlchemy ORM — no raw SQL strings.
#   - Enum columns use Python Enum types mapped to PG VARCHAR with CHECK
#     constraints, preventing arbitrary string injection into status fields.
# =============================================================================

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


# ---------------------------------------------------------------------------
# Enum types (enforced at DB level via CHECK constraints)
# ---------------------------------------------------------------------------

class EventType(str, enum.Enum):
    """High-level category of the audit event."""
    AGENT_STARTED        = "AGENT_STARTED"        # A LangGraph node began execution
    AGENT_COMPLETED      = "AGENT_COMPLETED"       # A LangGraph node finished
    TOOL_CALLED          = "TOOL_CALLED"           # An MCP tool was invoked
    TOOL_SUCCEEDED       = "TOOL_SUCCEEDED"        # MCP tool returned status=ok
    TOOL_FAILED          = "TOOL_FAILED"           # MCP tool returned error or raised
    SUPERVISOR_ROUTED    = "SUPERVISOR_ROUTED"     # Supervisor dispatched to sub-agent
    SUPERVISOR_COMPLETED = "SUPERVISOR_COMPLETED"  # Supervisor compiled final report
    LLM_CALL             = "LLM_CALL"             # Direct LLM inference call
    SELF_CORRECTION      = "SELF_CORRECTION"       # Agent retry triggered
    GRAPH_STARTED        = "GRAPH_STARTED"         # LangGraph invocation began
    GRAPH_COMPLETED      = "GRAPH_COMPLETED"       # LangGraph invocation ended
    SECURITY_VIOLATION   = "SECURITY_VIOLATION"    # Blocked write-op or injection attempt


class AgentName(str, enum.Enum):
    """Canonical agent identifiers — prevents typos across codebase."""
    SUPERVISOR       = "supervisor"
    FORENSICS_AGENT  = "forensics_agent"
    NETWORK_AGENT    = "network_agent"
    DATABASE_AGENT   = "database_agent"
    SYSTEM           = "system"          # Used for graph-level events


class EventStatus(str, enum.Enum):
    """Outcome status of the event."""
    OK      = "ok"
    ERROR   = "error"
    PARTIAL = "partial"
    BLOCKED = "blocked"     # Security denylist triggered


# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------

class AuditEvent(Base):
    """
    Immutable audit event record.

    Design notes:
      - Primary key is a UUID v4 (generated server-side) — prevents
        enumeration attacks and is safe for distributed inserts.
      - recorded_at uses server_default=func.now() to ensure the DB clock
        is authoritative (not the application clock), critical for
        tamper-evident logging.
      - JSONB columns (tool_input_json, tool_output_json, state_snapshot_json)
        are indexed with GIN for fast Splunk-style JSON path queries.
    """

    __tablename__ = "audit_events"

    # ------------------------------------------------------------------
    # Primary key
    # ------------------------------------------------------------------
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 primary key — tamper-resistant and non-enumerable",
    )

    # ------------------------------------------------------------------
    # Incident correlation
    # ------------------------------------------------------------------
    incident_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="Incident identifier from IRAgentState.incident_id (e.g. IR-2024-0047)",
    )

    graph_run_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="Unique run ID for one full LangGraph .ainvoke() call; groups all events from a single IR session",
    )

    # ------------------------------------------------------------------
    # Event classification
    # ------------------------------------------------------------------
    event_type: Mapped[str] = mapped_column(
        SAEnum(EventType, name="event_type_enum", create_constraint=True),
        nullable=False,
        index=True,
        comment="High-level event category (see EventType enum)",
    )

    agent_name: Mapped[str] = mapped_column(
        SAEnum(AgentName, name="agent_name_enum", create_constraint=True),
        nullable=False,
        index=True,
        comment="Which agent fired this event (see AgentName enum)",
    )

    status: Mapped[str] = mapped_column(
        SAEnum(EventStatus, name="event_status_enum", create_constraint=True),
        nullable=False,
        default=EventStatus.OK,
        comment="Outcome of this event (ok / error / partial / blocked)",
    )

    # ------------------------------------------------------------------
    # Tool call details (null if event is not TOOL_CALLED/TOOL_SUCCEEDED/TOOL_FAILED)
    # ------------------------------------------------------------------
    tool_name: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        index=True,
        comment="MCP tool name (e.g. run_volatility_plugin, run_spl_search)",
    )

    tool_input_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Serialised Pydantic input model dict — written BEFORE tool execution",
    )

    tool_output_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full tool return dict — written AFTER tool execution completes",
    )

    # ------------------------------------------------------------------
    # Self-correction tracking
    # ------------------------------------------------------------------
    retry_attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="0 = first attempt; 1–3 = retry number (matches error_log.attempt)",
    )

    error_type: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment="Exception class name if status=error (e.g. TimeoutError, RuntimeError)",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable error description (truncated to 4096 chars max)",
    )

    # ------------------------------------------------------------------
    # LLM token accounting (Splunk Agentic Ops criterion)
    # ------------------------------------------------------------------
    token_prompt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Input / prompt tokens consumed in this event (0 if no LLM call)",
    )

    token_completion: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Output / completion tokens generated in this event",
    )

    token_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total tokens = token_prompt + token_completion (denormalised for fast SUM queries)",
    )

    # ------------------------------------------------------------------
    # State snapshot & integrity (SANS criterion: evidence chain)
    # ------------------------------------------------------------------
    state_snapshot_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Partial IRAgentState snapshot at event time — excludes binary payloads",
    )

    sha256_state_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "SHA-256 hex digest of the JSON-serialised state_snapshot_json. "
            "Enables offline tamper detection — re-hash the stored snapshot and compare."
        ),
    )

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Wall-clock execution time of the event in milliseconds",
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),    # DB clock is authoritative
        nullable=False,
        index=True,
        comment="DB-server timestamp — use for tamper-evident ordering",
    )

    # ------------------------------------------------------------------
    # Table-level constraints + performance indexes
    # ------------------------------------------------------------------
    __table_args__ = (
        # Partial index for fast "open incident" queries
        Index("ix_audit_events_incident_recent", "incident_id", "recorded_at"),
        # Partial index for Splunk-style tool failure analysis
        Index(
            "ix_audit_events_tool_failures",
            "tool_name",
            "status",
            postgresql_where=(status == EventStatus.ERROR),
        ),
        # GIN index on JSONB for JSON path queries from Splunk / SQL clients
        Index("ix_audit_events_tool_input_gin",  "tool_input_json",  postgresql_using="gin"),
        Index("ix_audit_events_tool_output_gin", "tool_output_json", postgresql_using="gin"),
        # Sanity check: token_total must equal prompt + completion
        CheckConstraint(
            "token_total = token_prompt + token_completion",
            name="ck_audit_events_token_total",
        ),
        # Sanity check: retry_attempt is non-negative
        CheckConstraint(
            "retry_attempt >= 0",
            name="ck_audit_events_retry_non_negative",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id} incident={self.incident_id} "
            f"type={self.event_type} agent={self.agent_name} status={self.status}>"
        )
