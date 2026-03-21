"""
LlamaIndex RAG pipeline: Ollama (Llama 3) + local embeddings.
Citations required; if retrieval is empty or low score → 'Insufficient legal basis.'
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from taxlens.config import KNOWLEDGE_DIR, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, OLLAMA_LLM_MODEL

try:
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core import PromptTemplate
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
except ImportError:  # pragma: no cover
    Document = None  # type: ignore[misc, assignment]
    Settings = None  # type: ignore[misc, assignment]
    VectorStoreIndex = None  # type: ignore[misc, assignment]
    PromptTemplate = None  # type: ignore[misc, assignment]


@dataclass
class CitedAnswer:
    text: str
    citations: list[str]
    source_nodes: list[dict[str, Any]]
    insufficient_legal_basis: bool


def _load_markdown_docs(folder: Path) -> list[Any]:
    if Document is None:
        return []
    docs: list[Any] = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta = {
            "file": path.name,
            "title": path.stem,
        }
        docs.append(Document(text=text, metadata=meta))
    return docs


def build_index_from_knowledge_dir(
    knowledge_dir: Path | None = None,
    persist_dir: Path | None = None,
) -> Any:
    if VectorStoreIndex is None:
        raise RuntimeError("llama-index packages are not installed. See requirements.txt")
    kd = knowledge_dir or KNOWLEDGE_DIR
    documents = _load_markdown_docs(kd)
    if not documents:
        raise FileNotFoundError(f"No .md documents under {kd}")

    Settings.llm = Ollama(model=OLLAMA_LLM_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=120.0)
    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    index = VectorStoreIndex.from_documents(documents)
    if persist_dir:
        index.storage_context.persist(persist_dir=str(persist_dir))
    return index


def query_with_citations(
    index: Any,
    question: str,
    *,
    similarity_top_k: int = 4,
    score_threshold: float = 0.2,
) -> CitedAnswer:
    """
    Retrieve, then answer with strict citation rules via local Ollama.
    Empty or below-threshold retrieval → no legal conclusion from the model.
    """
    if Settings is None or PromptTemplate is None:
        raise RuntimeError("llama-index packages are not installed. See requirements.txt")

    retriever = index.as_retriever(similarity_top_k=similarity_top_k)
    nodes = retriever.retrieve(question)

    filtered: list[Any] = []
    for n in nodes:
        score = getattr(n, "score", None)
        if score is None:
            filtered.append(n)
        elif float(score) >= score_threshold:
            filtered.append(n)

    citations: list[str] = []
    source_nodes: list[dict[str, Any]] = []
    for n in filtered:
        meta = getattr(n, "metadata", {}) or {}
        ref = meta.get("title") or meta.get("file") or "unknown"
        citations.append(f"Source: {ref}")
        content = n.get_content()
        source_nodes.append(
            {
                "ref": ref,
                "excerpt": (content[:500] + "…") if len(content) > 500 else content,
                "metadata": meta,
            }
        )

    if not filtered:
        return CitedAnswer(
            text="Insufficient legal basis.",
            citations=[],
            source_nodes=[],
            insufficient_legal_basis=True,
        )

    context_str = "\n\n---\n\n".join(n.get_content() for n in filtered)
    tmpl = PromptTemplate(
        "You are a tax and audit assistant. Use ONLY the context below.\n"
        "Every substantive claim MUST cite the instrument (e.g. Circular, Decree, IFRS standard) "
        "and Article/Clause where possible, using the phrasing in the context.\n"
        "If the context does not support an answer, reply exactly: Insufficient legal basis.\n"
        "Do not invent citations.\n\n"
        "Context:\n{context_str}\n\n"
        "Question: {query_str}\n\n"
        "Answer:"
    )
    llm = Settings.llm
    prompt = tmpl.format(context_str=context_str, query_str=question)
    final = llm.complete(prompt)

    return CitedAnswer(
        text=str(final).strip(),
        citations=citations,
        source_nodes=source_nodes,
        insufficient_legal_basis=False,
    )
