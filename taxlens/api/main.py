import os
import shutil
import json
import warnings
from fastapi import FastAPI, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

# Dập tắt các warnings của Pydantic / thư viện để console sạch sẽ tuyệt đối
warnings.filterwarnings("ignore")
load_dotenv()

# Database Setup
from taxlens.api.database import engine, Base, get_db
from taxlens.api.models import AuditReport

# Tạo Schema DB thực thi ngay lập tức
Base.metadata.create_all(bind=engine)

# Khởi tạo Graph (LangGraph)
from taxlens.agents.agent_router import build_tax_audit_graph
graph = build_tax_audit_graph()

app = FastAPI(title="TaxLens Enterprise API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/v1/reports")
def get_reports(db: Session = Depends(get_db)):
    """API Fetch Lịch Sử Audit (SaaS History)"""
    reports = db.query(AuditReport).order_by(AuditReport.created_at.desc()).all()
    # Serialize results
    results = []
    for r in reports:
        results.append({
            "id": r.id,
            "tenant_firm": r.tenant_firm,
            "client_name": r.client_name,
            "created_at": r.created_at.strftime("%d/%m/%Y %H:%M"),
            "working_papers": json.loads(r.working_papers) if r.working_papers else [],
            "management_letter": r.management_letter
        })
    return {"status": "success", "data": results}

@app.post("/api/v1/audit")
async def process_audit(
    files: list[UploadFile] = File(...),
    audit_firm_name: str = Form(default="Independent Audit Firm"),
    client_name: str = Form(default="Client Corporation"),
    db: Session = Depends(get_db)
):
    """API cốt lõi: Phân tích File & Lưu Trữ Data Xuống SQLite"""
    
    # 1. Tạo thư mục tạm và lưu file (Robust Temp Storage)
    TEMP_DIR = "temp_uploads"
    os.makedirs(TEMP_DIR, exist_ok=True)
    saved_file_paths = []
    
    for file in files:
        file_path = os.path.join(TEMP_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_file_paths.append(file_path)

    # 2. Xây dựng State và kích hoạt Graph
    thread_id = "api_thread_" + os.urandom(4).hex()
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "messages": [HumanMessage(content="Start Audit")],
        "raw_data": {"uploaded_paths": saved_file_paths},
        "audit_firm_name": audit_firm_name,
        "client_name": client_name,
        "is_approved": True, # Auto-approve for API Full Flow
        "review_note": ""
    }
    
    try:
        # Chạy Graph đục thẳng vào file thật
        res = graph.invoke(initial_state, config)
        
        # 3. Trích xuất Payload báo cáo
        working_papers = res.get("working_papers", {}).get("standardized_findings", [])
        legal_context = res.get("working_papers", {}).get("Legal_Context", "")
        management_letter = res.get("messages", [])[-1].content if res.get("messages") else "Lỗi sinh báo cáo"
        
        # 4. LƯU DATABASE (PERSISTENCE LAYER)
        new_report = AuditReport(
            tenant_firm=audit_firm_name,
            client_name=client_name,
            working_papers=json.dumps(working_papers, ensure_ascii=False),
            management_letter=management_letter
        )
        db.add(new_report)
        db.commit()
        db.refresh(new_report)
        
        response_payload = {
            "status": "success",
            "audit_firm": audit_firm_name,
            "client": client_name,
            "data": {
                "id": new_report.id,
                "working_papers": working_papers,
                "legal_context": legal_context,
                "management_letter": management_letter
            }
        }
    except Exception as e:
        response_payload = {"status": "error", "message": f"Graph Execution Failed: {str(e)}"}
    finally:
        # 5. HỦY TÀI LIỆU TẠM (ZERO-FOOTPRINT CLEANUP)
        for path in saved_file_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
                
    return JSONResponse(status_code=200, content=response_payload)
