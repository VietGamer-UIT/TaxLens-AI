"""
LlamaIndex Dynamic Legal RAG Ingestion Pipeline.
Reads PDF/Word documents from official_docs/, builds vector index, attaches metadata.
"""
import os
from pathlib import Path
from taxlens.config import KNOWLEDGE_DIR, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL
try:
    from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Settings
    from llama_index.embeddings.ollama import OllamaEmbedding
except ImportError as e:
    print(f"Missing packages for LlamaIndex: {e}")
    exit(1)

def ingest():
    doc_dir = KNOWLEDGE_DIR / "official_docs"
    doc_dir.mkdir(parents=True, exist_ok=True)
    persist_dir = KNOWLEDGE_DIR.parent / "vector_store"
    
    # Configure embed model
    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    Settings.llm = None # We do not need LLM at ingestion time

    files = list(doc_dir.glob("*.*"))
    if not files:
        print(f"No documents found in {doc_dir}. Pls add PDF/Word files.")
        return

    print("Loading documents metadata (filename, page)...")
    reader = SimpleDirectoryReader(input_dir=str(doc_dir), extract_hidden=False)
    documents = reader.load_data()
    
    print(f"Loaded {len(documents)} document fragments. Building Vector Index...")
    index = VectorStoreIndex.from_documents(documents)
    
    persist_dir.mkdir(parents=True, exist_ok=True)
    index.storage_context.persist(persist_dir=str(persist_dir))
    print(f"Ingestion successful! Stored locally at {persist_dir}.")

if __name__ == "__main__":
    ingest()
