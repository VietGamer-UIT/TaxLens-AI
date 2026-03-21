"""
TaxLens-AI FastAPI entrypoint — local-only; no cloud APIs.
Run: uvicorn taxlens.api.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from taxlens import __version__
from taxlens.agents.registry import (
    AuditReportDraftAgent,
    BankReconciliationAgent,
    TransferPricingAgent,
)
from taxlens.agents.tax_compliance import TaxComplianceAgent
from taxlens.api.deps import Role, role_dependency
from taxlens.audit.logger import load_recent
from taxlens.config import UPLOAD_DIR
from taxlens.ingestion.excel_csv import load_general_ledger, normalize_gl_columns
from taxlens.masking import mask_sensitive_text
from taxlens.risk.scoring import score_transactions, top_risk_percentile
from taxlens.services.flagging import flag_transaction_ledger_mismatch

app = FastAPI(title="TaxLens-AI", version=__version__, description="Local-first tax & audit intelligence API")

dep_staff_admin = role_dependency({Role.staff, Role.admin})
dep_manager_admin = role_dependency({Role.manager, Role.admin})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "TaxLens-AI", "version": __version__}


class TaxComplianceRequest(BaseModel):
    question: str = Field(..., description="Tax/audit question (will be masked before RAG)")


@app.post("/api/v1/staff/tax-compliance-check")
async def staff_tax_compliance_check(
    body: TaxComplianceRequest,
    _: Role = Depends(dep_staff_admin),
) -> dict[str, Any]:
    """Staff: run Tax Compliance Agent (RAG + citations); human must validate."""
    agent = TaxComplianceAgent()
    result = agent.run({"question": body.question})
    return {
        "agent": result.agent_name,
        "steps": result.steps,
        "output": result.structured_output,
        "citations": result.citations,
        "confidence": result.confidence,
        "requires_human_review": result.requires_human_review,
        "editable": True,
    }


class UploadGLResponse(BaseModel):
    rows_preview: int
    columns: list[str]
    message: str


@app.post("/api/v1/staff/upload-gl", response_model=UploadGLResponse)
async def staff_upload_gl(
    file: UploadFile = File(...),
    _: Role = Depends(dep_staff_admin),
) -> UploadGLResponse:
    """Staff: upload GL Excel/CSV (stored on-premise under data/uploads)."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / (file.filename or "upload.dat")
    content = await file.read()
    dest.write_bytes(content)
    try:
        df = normalize_gl_columns(load_general_ledger(dest))
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}") from e
    return UploadGLResponse(
        rows_preview=min(10, len(df)),
        columns=[str(c) for c in df.columns],
        message=f"Stored at {dest}",
    )


class RiskDashboardResponse(BaseModel):
    total_scored: int
    top_risk_count: int
    top_risk: list[dict[str, Any]]


@app.get("/api/v1/manager/risk-dashboard", response_model=RiskDashboardResponse)
async def manager_risk_dashboard(
    _: Role = Depends(dep_manager_admin),
) -> RiskDashboardResponse:
    """Manager: materiality-style ranked risks (example uses in-memory demo rows)."""
    demo_rows = [
        {
            "id": "V-1001",
            "amount": 12_500_000.0,
            "vat_expected": 1_250_000.0,
            "vat_actual": 900_000.0,
            "ledger_amount_match": 0.0,
            "invoice_duplicate_signal": 0.2,
        },
        {
            "id": "V-1002",
            "amount": 50_000_000.0,
            "vat_expected": 0.0,
            "vat_actual": 0.0,
            "ledger_amount_match": 1.0,
            "invoice_duplicate_signal": 0.0,
        },
    ]
    gl_stats = {"amount_mean": 20_000_000.0, "amount_std": 15_000_000.0}
    scored = score_transactions(demo_rows, gl_stats)
    top = top_risk_percentile(scored)
    return RiskDashboardResponse(
        total_scored=len(scored),
        top_risk_count=len(top),
        top_risk=[
            {
                "transaction_id": s.transaction_id,
                "risk_score": s.risk_score,
                "attribution": s.attribution_summary,
            }
            for s in top
        ],
    )


class MaskRequest(BaseModel):
    text: str


@app.post("/api/v1/staff/mask-preview")
async def staff_mask_preview(
    body: MaskRequest,
    _: Role = Depends(dep_staff_admin),
) -> dict[str, str]:
    m = mask_sensitive_text(body.text)
    return {"masked": m.masked_text}


class CompareRequest(BaseModel):
    invoice_amount: float
    ledger_amount: float


@app.post("/api/v1/staff/flag-compare")
async def staff_flag_compare(
    body: CompareRequest,
    _: Role = Depends(dep_staff_admin),
) -> dict[str, Any]:
    return flag_transaction_ledger_mismatch(body.invoice_amount, body.ledger_amount)


@app.get("/api/v1/manager/audit-log")
async def manager_audit_log(
    _: Role = Depends(dep_manager_admin),
    limit: int = 100,
) -> list[dict[str, Any]]:
    recs = load_recent(limit)
    return [r.model_dump(mode="json") for r in recs]


@app.post("/api/v1/agents/bank-reconciliation")
async def agent_bank_recon(
    context: dict[str, Any],
    _: Role = Depends(dep_staff_admin),
) -> dict[str, Any]:
    r = BankReconciliationAgent().run(context)
    return r.model_dump()


@app.post("/api/v1/agents/transfer-pricing")
async def agent_tp(
    context: dict[str, Any],
    _: Role = Depends(dep_manager_admin),
) -> dict[str, Any]:
    r = TransferPricingAgent().run(context)
    return r.model_dump()


@app.post("/api/v1/agents/audit-report-draft")
async def agent_audit_draft(
    context: dict[str, Any],
    _: Role = Depends(dep_manager_admin),
) -> dict[str, Any]:
    r = AuditReportDraftAgent().run(context)
    return r.model_dump()
