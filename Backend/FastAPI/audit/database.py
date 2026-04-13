# =============================================================================
# TaxLens-AI :: Audit Trail — Async Database Connection
# Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Provides a fully async SQLAlchemy 2.x engine and session factory
# connected to PostgreSQL via asyncpg driver.
#
# Key design decisions:
#   - Uses create_async_engine with NullPool for compatibility inside
#     FastAPI's async request lifecycle (avoids greenlet issues).
#   - Pool configuration tuned for a containerised deployment:
#       pool_size=10, max_overflow=20, pool_pre_ping=True
#   - Connection string is sourced exclusively from environment variables
#     — no hard-coded credentials anywhere in this file.
#   - All table DDL is created via Base.metadata.create_all() called once
#     at application startup (models.py defines the schema).
# =============================================================================

from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("taxlens.audit.database")

# ---------------------------------------------------------------------------
# Connection string construction
# ---------------------------------------------------------------------------
# Reads from environment variables injected by Docker / .env file.
# Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
# ---------------------------------------------------------------------------
_PG_USER: str     = os.getenv("POSTGRES_USER",     "taxlens")
_PG_PASSWORD: str = os.getenv("POSTGRES_PASSWORD",  "changeme_in_prod")
_PG_HOST: str     = os.getenv("POSTGRES_HOST",      "db")      # docker-compose service name
_PG_PORT: str     = os.getenv("POSTGRES_PORT",      "5432")
_PG_DB: str       = os.getenv("POSTGRES_DB",        "taxlens_audit")

DATABASE_URL: str = (
    f"postgresql+asyncpg://{_PG_USER}:{_PG_PASSWORD}"
    f"@{_PG_HOST}:{_PG_PORT}/{_PG_DB}"
)

# ---------------------------------------------------------------------------
# SQLAlchemy Async Engine
# ---------------------------------------------------------------------------
# pool_pre_ping=True — validates connections before handing them to a session,
# preventing "stale connection" errors after DB restarts.
# ---------------------------------------------------------------------------
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,              # Set to True for SQL query debugging
    pool_size=10,            # Base connection pool size
    max_overflow=20,         # Additional connections allowed under load
    pool_pre_ping=True,      # Heartbeat check on connection checkout
    pool_recycle=3600,       # Recycle connections every 1 hour
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
# expire_on_commit=False — required in async context: prevents SQLAlchemy
# from attempting lazy loads on expired attributes after a commit.
# ---------------------------------------------------------------------------
AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Declarative base (imported by models.py)
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Shared declarative base for all TaxLens-AI ORM models."""
    pass


# ---------------------------------------------------------------------------
# Lifespan helpers (called from FastAPI startup/shutdown events)
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """
    Create all database tables defined in ORM models.

    Called once at application startup.  Using checkfirst=True semantics
    via create_all — safe to call on a DB that already has the tables.
    """
    from . import models as _models  # noqa: F401 — ensure models are imported
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[AuditDB] Tables created / verified.")


async def close_db() -> None:
    """Dispose the engine connection pool on application shutdown."""
    await engine.dispose()
    logger.info("[AuditDB] Engine disposed.")


# ---------------------------------------------------------------------------
# Dependency injection helper for FastAPI routes
# ---------------------------------------------------------------------------

async def get_audit_session() -> AsyncSession:  # type: ignore[return]
    """
    FastAPI dependency that yields an AsyncSession within a transaction.

    Usage:
        @router.get("/health")
        async def health(db: AsyncSession = Depends(get_audit_session)):
            ...
    """
    async with AsyncSessionFactory() as session:
        async with session.begin():
            yield session
