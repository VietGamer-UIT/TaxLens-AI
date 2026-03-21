# TaxLens-AI

**TaxLens-AI** is a **local-first, on-premise** foundation for tax advisory support, audit assistance, and financial risk detection. It is **not** a chatbot: it combines deterministic checks, retrieval-grounded generation, agent workflows, explainability, and **mandatory human review**.

Design principles:

- **Trust** — No cloud LLM in the default stack; data stays on your network.
- **Precision** — RAG answers must cite the knowledge base or return **Insufficient legal basis.**
- **Governance** — AI does **not** make final compliance or audit conclusions.

> **Disclaimer:** Demo legal excerpts in `data/knowledge_base/` are placeholders. Load official Vietnam tax law and IFRS texts approved for your organization. This software does not provide legal advice.

---

## Architecture

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for a module diagram and trust boundaries.

### Stack

| Component | Role |
|-----------|------|
| **FastAPI** | API layer, role-aware routes |
| **LlamaIndex** | RAG over local markdown knowledge files |
| **Ollama** | **Llama 3** + local embeddings (`nomic-embed-text` recommended) |
| **Pandas** | GL / CSV / Excel ingestion |

---

## Quick start

### 1. Python environment

```bash
cd TaxLens-AI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Ollama (on-premise)

Install [Ollama](https://ollama.com/) and pull models (no cloud API calls from the app):

```bash
ollama pull llama3
ollama pull nomic-embed-text
```

Ensure `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`) is reachable.

### 3. Run the API

```bash
uvicorn taxlens.api.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for interactive OpenAPI.

**Role header:** send `X-Role: staff` or `X-Role: manager` (placeholder until JWT/IdP is wired).

Example — tax compliance agent (masked → RAG):

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/staff/tax-compliance-check" ^
  -H "Content-Type: application/json" -H "X-Role: staff" ^
  -d "{\"question\":\"When can we deduct VAT on purchases?\"}"
```

Example — flag invoice vs ledger mismatch (deterministic explainability):

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/staff/flag-compare" ^
  -H "Content-Type: application/json" -H "X-Role: staff" ^
  -d "{\"invoice_amount\":12500000,\"ledger_amount\":12499900}"
```

---

## Repository layout

```
TaxLens-AI/
├── taxlens/                 # Core Python package
│   ├── api/                 # FastAPI
│   ├── agents/              # Agent workflows (Tax Compliance, Bank Rec, TP, Report draft)
│   ├── audit/               # Audit models + JSONL logger
│   ├── ingestion/           # Excel/CSV, PDF/OCR outline, ERP connector mocks
│   ├── rag/                 # LlamaIndex + Ollama
│   ├── explainability/      # Linear attribution (SHAP-like proxy)
│   ├── risk/                # Risk scoring + top 5% selection
│   ├── masking.py           # PII masking before LLM
│   └── services/            # Flagging helpers
├── data/knowledge_base/     # Vietnam tax + IFRS markdown chunks (replace with licensed text)
├── samples/                 # Example GL + audit JSON
├── docs/ARCHITECTURE.md
├── SQL-Scripts/TaxLens-AI.sql
├── legacy/                  # Archived EntradeX Advisor (C++)
└── requirements.txt
```

---

## Features implemented (foundation)

| Requirement | Implementation |
|-------------|----------------|
| On-premise LLM | Ollama + Llama 3 in `taxlens/rag/pipeline.py` |
| Masking | `taxlens/masking.py` |
| RAG + citations | LlamaIndex; empty/low retrieval → **Insufficient legal basis.** |
| Explainability | `taxlens/explainability/attribution.py` + risk drivers |
| Audit trail | `taxlens/audit/logger.py` → `data/audit_logs/audit.jsonl` |
| Ingestion | `taxlens/ingestion/` (Excel/CSV GL; OCR as outline) |
| ERP connectors | SAP / Oracle / MISA mocks in `connectors.py` |
| Agents | `taxlens/agents/` |
| Human-in-the-loop | `requires_human_review`, `confidence`, editable JSON in API |
| Roles | Staff vs Manager routes + `X-Role` |
| Top 5% risk | `taxlens/risk/scoring.py` (`RISK_PERCENTILE_HIGH=0.95`) |

---

## Sample audit output

See **[samples/audit_output_sample.json](samples/audit_output_sample.json)** for reasoning steps, drivers, citation shape, and human approval placeholder.

---

## OCR (optional)

On-premise OCR typically uses **Tesseract** + **PyMuPDF** or **pdfplumber**. See `taxlens/ingestion/pdf_ocr.py` for the integration contract; uncomment optional dependencies in `requirements.txt` when ready.

---

## Legacy project

The previous **EntradeX Advisor** C++ stock advisor lives under **`legacy/entrade_x_advisor/`** and is not part of the TaxLens-AI runtime.

---

## License

Add your license. IFRS excerpts require compliance with the IFRS Foundation’s terms; Vietnam legal texts must be used per applicable copyright and official distribution rules.

---

**TaxLens-AI** — private, explainable audit intelligence for enterprise deployment.
