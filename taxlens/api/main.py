"""
TaxLens-AI v3.1 — FastAPI Backend
BackgroundTask pipeline + Status polling + Idempotency + WAL SQLite
Phát triển bởi Đoàn Hoàng Việt (Việt Gamer)
"""
import json, os, shutil, warnings
from typing import Dict
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

from taxlens.api.database import Base, engine, get_db
from taxlens.api.models import AuditReport
Base.metadata.create_all(bind=engine)
with engine.connect() as conn:
    conn.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL"))

from taxlens.agents.agent_router import build_tax_audit_graph
graph = build_tax_audit_graph()

# In-memory status store: { thread_id: { stage, progress_pct, message, status, result? } }
AUDIT_STATUS: Dict[str, Dict] = {}

def _set_status(tid: str, stage: str, pct: int, msg: str, status: str = "running"):
    AUDIT_STATUS[tid] = {"stage": stage, "progress_pct": pct, "message": msg, "status": status}

app = FastAPI(title="TaxLens Enterprise API v3.1", version="3.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/v1/reports")
def get_reports(db: Session = Depends(get_db)):
    reports = db.query(AuditReport).order_by(AuditReport.created_at.desc()).all()
    return {"status": "success", "data": [
        {"id": r.id, "tenant_firm": r.tenant_firm, "client_name": r.client_name,
         "created_at": r.created_at.strftime("%d/%m/%Y %H:%M"),
         "working_papers": json.loads(r.working_papers) if r.working_papers else [],
         "management_letter": r.management_letter}
        for r in reports
    ]}


@app.get("/api/v1/audit/{thread_id}/status")
def get_audit_status(thread_id: str):
    """Polling endpoint — frontend calls every 1.5s."""
    if thread_id not in AUDIT_STATUS:
        return JSONResponse(status_code=404, content={"error": "thread not found"})
    return AUDIT_STATUS[thread_id]


def _run_pipeline(thread_id, paths, temp_dir, api_key, firm, client, idem_key, db_factory):
    """Background task: runs LangGraph, streams status updates."""
    file_types = list({p.rsplit(".", 1)[-1].upper() for p in paths})
    _set_status(thread_id, "ingest", 10,
                f"📂 Đang xử lý {len(paths)} file ({', '.join(file_types)})...")

    initial_state = {
        "messages": [HumanMessage(content="Start v3.1")],
        "raw_data": {"uploaded_paths": paths, "api_key": api_key, "thread_id": thread_id},
        "audit_firm_name": firm, "client_name": client,
        "is_approved": True, "review_note": "", "working_papers": {},
    }
    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = initial_state
        for step in graph.stream(initial_state, config, stream_mode="values"):
            final_state = step
            msgs = step.get("messages", [])
            last = msgs[-1].content if msgs else ""
            if "[Ingestor]" in last:
                _set_status(thread_id, "ingest", 35, f"✅ {last[:100]}")
            elif "[Validator]" in last:
                _set_status(thread_id, "validate", 55, f"⚡ {last[:100]}")
            elif "Oracle" in last:
                _set_status(thread_id, "oracle", 75, f"🧠 {last[:100]}")
            elif "HitL" in last:
                _set_status(thread_id, "hitl", 85, "⏸️ Auto-approve HitL...")
            elif "MANAGEMENT LETTER" in last:
                _set_status(thread_id, "report", 95, "📄 Đang sinh Management Letter...")

        wp   = final_state.get("working_papers", {}).get("standardized_findings", [])
        lc   = final_state.get("working_papers", {}).get("Legal_Context", "")
        letter = final_state.get("messages", [])[-1].content if final_state.get("messages") else "Lỗi"

        db = next(db_factory())
        try:
            rec = AuditReport(tenant_firm=firm, client_name=client,
                              working_papers=json.dumps(wp, ensure_ascii=False),
                              management_letter=letter,
                              idempotency_key=idem_key or None, thread_id=thread_id)
            db.add(rec); db.commit(); db.refresh(rec)
            rid = rec.id
        finally:
            db.close()

        _set_status(thread_id, "done", 100, "✅ Hoàn tất!", status="done")
        AUDIT_STATUS[thread_id]["result"] = {
            "id": rid, "working_papers": wp, "legal_context": lc, "management_letter": letter
        }
    except Exception as e:
        _set_status(thread_id, "error", 0, f"❌ {e}", status="error")
        AUDIT_STATUS[thread_id]["error_detail"] = str(e)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        for junk in ["debug_out.txt", "audit.jsonl"]:
            try: os.remove(junk)
            except: pass


@app.post("/api/v1/audit", status_code=202)
async def process_audit(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    audit_firm_name: str = Form(default="TaxLens-AI B2B Partner"),
    client_name: str = Form(default="Client Corporation"),
    api_key: str = Form(default=""),
    x_idempotency_key: str = Header(default=""),
    db: Session = Depends(get_db),
):
    # Idempotency check
    if x_idempotency_key:
        ex = db.query(AuditReport).filter(AuditReport.idempotency_key == x_idempotency_key).first()
        if ex:
            return JSONResponse(200, {"status": "success", "idempotency": "cached",
                                      "thread_id": ex.thread_id,
                                      "data": {"id": ex.id,
                                               "working_papers": json.loads(ex.working_papers) if ex.working_papers else [],
                                               "management_letter": ex.management_letter}})

    # Save files to UUID temp dir
    uid = uuid4().hex
    temp_dir = os.path.join("temp_uploads", uid)
    os.makedirs(temp_dir, exist_ok=True)
    paths = []
    for f in files:
        safe = os.path.basename(f.filename or f"upload_{uid}.csv")
        fp = os.path.join(temp_dir, safe)
        with open(fp, "wb") as buf: shutil.copyfileobj(f.file, buf)
        paths.append(fp)

    thread_id = f"audit_{uid}"
    _set_status(thread_id, "queued", 0, "🔄 Đang khởi động pipeline...")

    background_tasks.add_task(
        _run_pipeline, thread_id, paths, temp_dir, api_key,
        audit_firm_name, client_name, x_idempotency_key, get_db
    )
    return {"status": "accepted", "thread_id": thread_id,
            "message": "Pipeline đang chạy nền. Poll /status để theo dõi."}


class ReviewPayload(BaseModel):
    is_approved: bool = True
    review_note: str = ""


@app.post("/api/v1/audit/{thread_id}/review")
async def resume_review(thread_id: str, payload: ReviewPayload, db: Session = Depends(get_db)):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        graph.update_state(config, {"is_approved": payload.is_approved, "review_note": payload.review_note})
        res = graph.invoke(None, config)
        letter = res.get("messages", [])[-1].content if res.get("messages") else "Lỗi"
        wp = res.get("working_papers", {}).get("standardized_findings", [])
        ex = db.query(AuditReport).filter(AuditReport.thread_id == thread_id).first()
        if ex:
            ex.working_papers = json.dumps(wp, ensure_ascii=False)
            ex.management_letter = letter
            db.commit()
        return {"status": "success", "thread_id": thread_id,
                "action": "approved" if payload.is_approved else "rejected_rerun",
                "data": {"working_papers": wp, "management_letter": letter}}
    except Exception as e:
        raise HTTPException(500, f"Resume failed: {e}")
