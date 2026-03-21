# TaxLens-AI — System Architecture

## Text-based diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT / UI (future)                             │
│  Staff: upload · quick checks    │    Manager: risk · approval · logs    │
└───────────────────────┬───────────────────────────────┬───────────────────┘
                        │ HTTPS (local)                 │
                        ▼                               ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ API Layer (FastAPI)                                                        │
│  Role headers (→ JWT/IdP) · validation · no final decisions in responses    │
└───────┬───────────────────────────────┬──────────────────────┬──────────────┘
        │                               │                      │
        ▼                               ▼                      ▼
┌───────────────┐              ┌──────────────────┐    ┌─────────────────┐
│ Ingestion     │              │ Agent Workflow    │    │ Audit Logger     │
│ Excel/CSV/PDF │              │ Bank / Tax / TP   │    │ JSONL append-only│
│ OCR outline   │              │ Report draft      │    │                  │
└───────┬───────┘              └─────────┬────────┘    └────────┬─────────┘
        │                                │                      │
        ▼                                ▼                      │
┌───────────────┐              ┌──────────────────┐             │
│ Preprocess &  │              │ RAG Engine        │             │
│ Mask PII      │──────────────│ LlamaIndex +      │             │
│               │              │ Ollama Llama 3    │             │
└───────────────┘              │ Vector KB: VN+IFRS             │
                               └─────────┬────────┘             │
                                         │                      │
        ┌────────────────────────────────┼────────────────────┘
        ▼                                ▼
┌───────────────┐              ┌──────────────────┐
│ Explainability │              │ Risk scoring    │
│ Linear attribution            │ Top 5% filter   │
│ (SHAP-like proxy)             │                 │
└───────────────┘              └──────────────────┘

External (on-premise only): **Ollama** @ 127.0.0.1:11434 — **Llama 3**, embeddings.
No cloud LLM or embedding APIs in the default configuration.
```

## Module map

| Layer | Package / path |
|--------|----------------|
| API | `taxlens/api/main.py` |
| Masking | `taxlens/masking.py` |
| Ingestion | `taxlens/ingestion/` |
| RAG | `taxlens/rag/pipeline.py` |
| Agents | `taxlens/agents/` |
| Explainability | `taxlens/explainability/` |
| Risk | `taxlens/risk/scoring.py` |
| Audit | `taxlens/audit/` |

## Trust boundaries

1. Sensitive fields are masked **before** LLM calls.
2. Legal answers must cite retrieved sources or state **Insufficient legal basis.**
3. All agent runs append to **audit logs**; outputs are **editable** and **require human review** by design.
