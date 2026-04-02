# TaxLens-AI: Enterprise Agentic Tax Workspace

**TaxLens-AI** is a 100% on-premise, Big 4 standard Agentic Workspace built for enterprise tax and audit compliance in Vietnam. It orchestrates local Large Language Models (LLMs) via LangGraph, enabling strict Human-In-The-Loop approvals and automated multi-agent fieldwork.

## Core Pillars
1. **Local-First Privacy:** Data never leaves your network. Operates natively with Ollama (`llama3` & `llama3.1`).
2. **LangGraph Orchestration:** Utilizes isolated Agents (`VAT_Recon`, `CIT_Adjustments`, `Compliance`, `FCT_TP`) simulating a true audit team.
3. **Strict Human-In-The-Loop:** The orchestrator halts (`interrupt_before`) prior to generating a Management Letter. Audit Managers must manually review immutable working papers to approve.
4. **Dynamic Legal RAG:** Automatically vectorizes newly uploaded PDF/Word legal texts, extracting mandatory file/page citations against hallucinations.

## Quick Start
```bash
# Setup Environment
pip install -r requirements.txt

# Start Enterprise UI Workspace
streamlit run frontend/app.py
```

## Data Ingestion
1. **Legal Frameworks:** Drop PDFs into `data/knowledge_base/official_docs/` and run `python scripts/ingest_laws.py`.
2. **Audit Evidence:** Upload Trial Balances (Excel/CSV) and E-Invoices (XML) directly through the Streamlit UI.
