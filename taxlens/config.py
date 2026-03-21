"""Central configuration (on-premise defaults; no cloud endpoints)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge_base"
CHROMA_DIR = DATA_DIR / "vector_store"
AUDIT_LOG_DIR = DATA_DIR / "audit_logs"
UPLOAD_DIR = DATA_DIR / "uploads"

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_LLM_MODEL = "llama3"
OLLAMA_EMBED_MODEL = "nomic-embed-text"

# Materiality / risk tuning (example defaults)
RISK_PERCENTILE_HIGH = 0.95  # top 5% flagged as highest risk
