# =============================================================================
# TaxLens-AI :: Audit Trail Package
# =============================================================================
from .database import Base, AsyncSessionFactory, engine, init_db, close_db, get_audit_session
from .models import AuditEvent, EventType, AgentName, EventStatus
from .middleware import (
    AuditMiddleware,
    audit_tool_call,
    audit_agent_event,
    set_audit_context,
)

__all__ = [
    # Database
    "Base", "AsyncSessionFactory", "engine", "init_db", "close_db", "get_audit_session",
    # Models
    "AuditEvent", "EventType", "AgentName", "EventStatus",
    # Middleware & helpers
    "AuditMiddleware", "audit_tool_call", "audit_agent_event", "set_audit_context",
]
