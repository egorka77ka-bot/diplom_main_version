import faiss
import pickle
import sys
from pathlib import Path
import os
sys.path.insert(0, str(Path(__file__).parent.parent))
from rag.ingest import ingest_documents
from rag.chunk import chunk_documents
from rag.embed import embed_chunks
from config import FAISS_INDEX_PATH, CHUNKS_PATH, METADATA_PATH, DATA_DIR

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

def build_index():
    print("BUILDING FAISS INDEX WITH METADATA")
    
    # Create data directory if needed
    DATA_DIR.mkdir(exist_ok=True)
    
    print("\n[1/5] Loading documents...")
    documents = ingest_documents()

    if not documents:
        print("No documents found.")
        return

    print(f"   Loaded {len(documents)} documents")

    print("\n[2/5] Chunking documents...")
    chunks = chunk_documents(documents)
    print(f"   Created {len(chunks)} chunks")

    print("\n[3/5] Generating embeddings...")
    embeddings = embed_chunks(chunks)
    print(f"   Embeddings shape: {embeddings.shape}")

    print("\n[4/5] Creating FAISS index...")
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    print(f"   Index contains {index.ntotal} vectors")

    print("\n[5/5] Saving files...")
    
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    print(f"   FAISS index saved: {FAISS_INDEX_PATH}")
    
    with open(METADATA_PATH, "wb") as f:
        pickle.dump(chunks, f)
    print(f"   Chunks with metadata saved: {METADATA_PATH}")
    
    simple_chunks = [{"text": c["text"], "source": c["source"]} for c in chunks]
    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(simple_chunks, f)
    print(f"   Legacy chunks saved: {CHUNKS_PATH}")

    print("INDEXING COMPLETE")
    print(f"   Total chunks: {len(chunks)}")
    
    if chunks:
        sample = chunks[0].get("metadata", {})
        print(f"\n   Sample metadata:")
        print(f"   - filename: {sample.get('filename', 'N/A')}")
        print(f"   - chunk_id: {sample.get('chunk_id', 'N/A')}")
        print(f"   - source: {sample.get('source', 'N/A')}")

if __name__ == "__main__":
    build_index()