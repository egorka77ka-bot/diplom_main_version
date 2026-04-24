import tiktoken
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHUNK_SIZE, CHUNK_OVERLAP

encoder = tiktoken.get_encoding("cl100k_base")

# Определение свойств чанкинга
def chunk_text(text: str):
    tokens = encoder.encode(text)
    chunks = []

    step = CHUNK_SIZE - CHUNK_OVERLAP
    for i in range(0, len(tokens), step):
        chunk_tokens = tokens[i:i + CHUNK_SIZE]
        chunks.append(encoder.decode(chunk_tokens))

    return chunks

# Функция разбиения на чанки документов
def chunk_documents(documents):
    all_chunks = []

    for doc in documents:
        chunks = chunk_text(doc["text"])
        base_metadata = doc.get("metadata", {})
        
        for idx, chunk in enumerate(chunks):
            chunk_metadata = base_metadata.copy()
            chunk_metadata.update({
                "chunk_id": idx,
                "chunk_total": len(chunks),
                "chunk_text_length": len(chunk)
            })
            
            all_chunks.append({
                "text": chunk,
                "source": doc["path"],
                "chunk_id": idx,
                "metadata": chunk_metadata
            })

    return all_chunks


if __name__ == "__main__":
    test_doc = {
        "text": "This is a test document. " * 100,
        "path": "test.txt",
        "metadata": {"filename": "test.txt"}
    }
    chunks = chunk_documents([test_doc])
    print(f" Создано {len(chunks)} чанков")
    if chunks:
        print(f" Пример метаданных из документов: {chunks[0].get('metadata', {})}")