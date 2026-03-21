"""Append-only JSONL audit logging."""

from __future__ import annotations

import json
from pathlib import Path

from taxlens.audit.models import AuditRecord
from taxlens.config import AUDIT_LOG_DIR


def _log_path() -> Path:
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return AUDIT_LOG_DIR / "audit.jsonl"


def append_audit(record: AuditRecord) -> None:
    path = _log_path()
    line = record.model_dump_json()
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_recent(max_lines: int = 500) -> list[AuditRecord]:
    path = _log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out: list[AuditRecord] = []
    for line in lines[-max_lines:]:
        try:
            out.append(AuditRecord.model_validate_json(line))
        except Exception:
            continue
    return out
