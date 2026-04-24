import os
import sys
import faiss
import pickle
import requests
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
# Исправление для Python 3.14

os.environ['HF_HUB_DISABLE_SSL_VERIFY'] = '1'

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    FAISS_INDEX_PATH,
    CHUNKS_PATH,
    METADATA_PATH,
    EMBEDDING_MODEL,
    OLLAMA_URL,
    OLLAMA_MODEL,
    TOP_K
)

model = SentenceTransformer(EMBEDDING_MODEL)

index = None
chunks_with_metadata = []


def _ensure_index_exists():
    """Ensure FAISS index exists, build it if it doesn't."""
    global index, chunks_with_metadata
    
    src_dir = Path(__file__).parent.parent
    index_path = src_dir / FAISS_INDEX_PATH
    metadata_path = src_dir / METADATA_PATH
    
    if index_path.exists() and metadata_path.exists():
        try:
            index = faiss.read_index(str(index_path))
            with open(metadata_path, "rb") as f:
                chunks_with_metadata = pickle.load(f)
            print(f" Loaded {len(chunks_with_metadata)} chunks with metadata")
            return True
        except Exception as e:
            print(f" Warning: Error loading existing index: {e}")
            print("Rebuilding index...")
    
    print(" Index not found. Building index from documents...")
    try:
        from rag.build_index import build_index
        build_index()
        
        if index_path.exists() and metadata_path.exists():
            index = faiss.read_index(str(index_path))
            with open(metadata_path, "rb") as f:
                chunks_with_metadata = pickle.load(f)
            print(" Index built and loaded successfully")
            return True
        else:
            print(" Failed to build index.")
            return False
    except Exception as e:
        print(f" Error building index: {e}")
        import traceback
        traceback.print_exc()
        return False


_ensure_index_exists()


def normalize_score(score: float) -> float:
    """Normalize FAISS inner product score to 0-1 range."""
    return (score + 1.0) / 2.0


def retrieve_with_metadata(query: str, k: int = TOP_K):
    """Retrieve relevant chunks for a query with full metadata."""
    if index is None or len(chunks_with_metadata) == 0:
        return []
    
    q_emb = model.encode([query])
    faiss.normalize_L2(q_emb)
    
    scores, ids = index.search(q_emb, k)
    
    results = []
    for idx, score in zip(ids[0], scores[0]):
        if 0 <= idx < len(chunks_with_metadata):
            chunk = chunks_with_metadata[idx].copy()
            chunk["score"] = float(normalize_score(score))
            if "metadata" not in chunk:
                chunk["metadata"] = {}
            chunk["metadata"]["chunk_id"] = chunk.get("chunk_id", idx)
            results.append(chunk)
    
    return results


def retrieve(query: str):
    """Retrieve relevant chunks for a query with metadata (legacy format)."""
    results = retrieve_with_metadata(query)
    legacy_results = []
    for r in results:
        legacy_results.append({
            "text": r.get("text", ""),
            "source": r.get("source", "unknown"),
            "metadata": r.get("metadata", {}),
            "score": r.get("score", 0)
        })
    return legacy_results


def build_prompt(query, contexts):
    """Build prompt with retrieved context and metadata."""
    if not contexts:
        return f"""
<role>You are a helpful assistant that answers questions about company information.</role>
<instructions>Answer the question based on your general knowledge. If you don't know, say so.</instructions>

<query>
{query}
</query>

<assistant>
"""

    context_parts = []
    for c in contexts:
        metadata = c.get("metadata", {})
        filename = metadata.get("filename", c.get("source", "unknown"))
        chunk_id = metadata.get("chunk_id", "?")
        chunk_total = metadata.get("chunk_total", "?")
        score = c.get("score", 0)
        
        metadata_str = f"[RAG: {filename} | чанк {chunk_id}/{chunk_total} | релевантность: {score:.3f}]"
        context_parts.append(f"{metadata_str}\n{c['text']}")

    context_text = "\n\n".join(context_parts)

    return f"""
<role>You are a helpful assistant that answers questions about company information.</role>
<instructions>Answer the question ONLY based on the context provided below. If the answer is not in the context, say "I don't have that information in the knowledge base."</instructions>

<context>
{context_text}
</context>

<query>
{query}
</query>

<assistant>
"""


def ask_llm(prompt):
    """Query Ollama LLM."""
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }
    )
    return response.json()["response"]


def ask(query: str):
    """Answer a question using RAG."""
    contexts = retrieve(query)
    prompt = build_prompt(query, contexts)
    return ask_llm(prompt), contexts


if __name__ == "__main__":
    while True:
        q = input("\n Question: ")
        if q.lower() in {"exit", "quit"}:
            break
        print("\n Answer:\n")
        answer, sources = ask(q)
        print(answer)
        if sources:
            print("\n Sources:")
            for src in sources:
                metadata = src.get("metadata", {})
                filename = metadata.get("filename", src.get("source", "unknown"))
                chunk_id = metadata.get("chunk_id", "?")
                score = src.get("score", 0)
                print(f"  - {filename} (chunk {chunk_id}, score: {score:.3f})")