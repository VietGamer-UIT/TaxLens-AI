# Kiến trúc Tổng thể TaxLens-AI (Enterprise SaaS)

TaxLens-AI B2B Architecture được thiết kế theo tư duy Multi-Agent Cloud Native, tách bạch hoàn toàn Controller (FastAPI) và View (SPA Tailwind), kết nối với AI Brain (LangGraph + Gemini 1.5 Flash).

## Sơ đồ Dòng Chảy Hệ Thống (ASCII Architecture)

```text
                                                [ THE USER/TENANT ]
                                                         │
                                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   FRONTEND (Single Page Application)                            │
│ 1. HTML / TailwindCSS (CDN-based for Zero-Nodejs setup)                                         │
│ 2. Vanilla JS Fetch API State Management                                                        │
│ 3. Enterprise Dashboard + Dynamic Metrics + SVG Icons                                           │
└────────────────────────────────────┬───────────────────────────────────▲────────────────────────┘
                                     │ (1) POST /api/v1/audit            │ (6) JSON Response
                                     │     + Upload CSV/XML              │     working_papers
                                     │     + Tenant Configs              │     management_letter
                                     ▼                                   │
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       FASTAPI BACKEND CORE                                      │
│ - Security: CORS Middleware             - Temp File Handler: temp_uploads/                      │
│ - Endpoints:                            - Background Tasks Cleanup                              │
│   GET /api/v1/reports -> Fetch History                                                          │
│   POST /api/v1/audit -> Trigger Agent                                                           │
└────────────────────────────────────┬───────────────────────────────────▲────────────────────────┘
                                     │ (2) trigger graph.invoke()        │ (5) return GraphState
                                     │     with initial state            │
                                     ▼                                   │
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                LANGGRAPH ORCHESTRATOR (Multi-Agent System)                      │
│                                                                                                 │
│  [ START ] ──▶ (Node 1: DATA PIPELINE)                      (Node 2: THE LEGAL ORACLE)          │
│                    Hunter_Agent           ──────────▶           Oracle_Agent                    │
│                 - Pandas DataFrame                          - DuckDuckGo RAG Web Search         │
│                 - Read 5000+ rows                           - Exception Handling (404/429)      │
│                 - Multi-class Filtering                     - Try/Catch Bulletproof Core        │
│                         │                                               │                       │
│                         │                                               ▼                       │
│                         │                                 (Node 3: HUMAN-IN-THE-LOOP)           │
│                         │                                     Manager_Review_Node               │
│                         │                                  (Interrupts Graph / API Bypass)      │
│                         │                                               │                       │
│                         ▲                                               ▼                       │
│                         │      [ NO ]                      (Router: Feedback Check)             │
│                         └─────────────────────────────────── Bắt lỗi làm lại?                   │
│                                                            [ YES ]                              │
│                                                                 │                               │
│                                                                 ▼                               │
│                                                       (Node 4: REPORT WRITER)                   │
│                                                            Report_Agent ───────────▶ [ END ]    │
│                                                       - Generate Management Letter              │
└────────────────────────────────────┬───────────────────────────────────▲────────────────────────┘
                                     │ (3) db.add(Report)                │ (4) db.commit()
                                     ▼                                   │
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    DATABASE & PERSISTENCE LAYER                                 │
│                                     [ SQLite / SQLAlchemy ]                                     │
│ - Table: `audit_reports`                                                                        │
│   (id, tenant_firm, client_name, working_papers [JSON], management_letter [Markdown], timestamp)│
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Các Thành phần Yếu lược

### 1. The Database Layer (`taxlens/api/database.py`, `models.py`)
Mọi phiên kiểm toán qua API đều được bất tử hóa xuống SQLite (nhỏ gọn, không cài cắm). Bóc tách toàn bộ findings JSON JSON stringified và kết nối tới lịch sử qua `GET /api/v1/reports`.

### 2. The Data Layer (`scripts/generate_test_data.py`)
Sử dụng Numpy/Pandas logic ngẫu nhiên để sinh ra hàng ngàn Transaction hợp lệ. Độn 15% rủi ro cố định (`CLASS_1_VAT_LEAK`, `CLASS_2_FAKE_INVOICE`, `CLASS_3_CIT_REJECT`) phục vụ huấn luyện máy học Machine Learning AI Agent.

### 3. The Backend Node (`taxlens/api/main.py`)
Tiếp tân nhận file. Xả file gốc lưu tạm vào `temp_uploads/`. Gửi thẻ `file_path` sang Graph và đứng canh, nhận JSON trả về thì bắn sang DB. Hủy chứng cứ sau khi kết thúc.

### 4. The Edge Intelligence (`taxlens/agents/agent_router.py`)
Linh hồn dự án. Thay vì dùng Prompt mông lung, Hunter Agent dùng `pd.read_csv()` trực tiếp gạn đục khơi trong, kết hợp Oracle RAG Search với đòn Prompt pháp lý cứng 100% chuẩn Việt Nam.
