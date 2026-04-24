import os
# Принудительный офлайн режим
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

import numpy as np
from sentence_transformers import SentenceTransformer
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EMBEDDING_MODEL

# Загрузка модели только из локального кэша
model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)

def embed_chunks(chunks):
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True)
    return np.array(embeddings)

if __name__ == "__main__":
    test_chunks = [{"text": "This is a test chunk."}]
    embeddings = embed_chunks(test_chunks)
    print(f"Embedding shape: {embeddings.shape}")