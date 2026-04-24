import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent                    # src/
DOCUMENTS_DIR = BASE_DIR / "docs"                   # src/docs/ (документы здесь!)
DATA_DIR = BASE_DIR / "data"                        # src/data/ (индексы здесь)

# RAG settings
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3:0.6b"
TOP_K = 130

# File paths
FAISS_INDEX_PATH = DATA_DIR / "index.faiss"
CHUNKS_PATH = DATA_DIR / "chunks.pkl"
METADATA_PATH = DATA_DIR / "chunks_with_metadata.pkl"

# Create data directory if it doesn't exist
DATA_DIR.mkdir(exist_ok=True)

print(f"[CONFIG] Documents directory: {DOCUMENTS_DIR}")
print(f"[CONFIG] Data directory: {DATA_DIR}")