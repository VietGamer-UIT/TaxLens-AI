import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from taxlens.api.database import Base


class AuditReport(Base):
    __tablename__ = "audit_reports"

    id = Column(Integer, primary_key=True, index=True)
    tenant_firm = Column(String(255), index=True, nullable=True, default="Unknown Firm")
    client_name = Column(String(255), index=True, nullable=True, default="Unknown Client")

    # Store aggregated JSON payload string
    working_papers = Column(Text, nullable=True)

    # Store Markdown Final Report
    management_letter = Column(Text, nullable=True)

    # Idempotency — prevents duplicate submissions (X-Idempotency-Key header)
    idempotency_key = Column(String(128), nullable=True, index=True, unique=True)

    # LangGraph thread_id — used for HitL resume endpoint
    thread_id = Column(String(64), nullable=True, index=True)

    # Auditing timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
