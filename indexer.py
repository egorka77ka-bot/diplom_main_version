import os
import glob
import json
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import PyPDF2
import docx2txt

# Конфигурация для RAG Саши
BASE_PATH = "./RAG"
DOCS_PATH = os.path.join(BASE_PATH, "data")
INDEX_PATH = os.path.join(BASE_PATH, "index", "faiss_index.bin")
CHUNKS_PATH = os.path.join(BASE_PATH, "index", "chunks.json")

CHUNK_SIZE = 700
CHUNK_OVERLAP = 100
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

def load_and_chunk_documents():
    chunks = []
    sources = []
    file_patterns = ["*.txt", "*.pdf", "*.docx", "*.md"]
    
    if not os.path.exists(DOCS_PATH):
        print(f"Папка не найдена: {DOCS_PATH}")
        return chunks, sources
    
    files_found = 0
    for pattern in file_patterns:
        for file_path in glob.glob(os.path.join(DOCS_PATH, pattern)):
            files_found += 1
            print(f"Обработка: {os.path.basename(file_path)}")
            text = ""
            try:
                if file_path.endswith('.pdf'):
                    with open(file_path, 'rb') as f:
                        for page in PyPDF2.PdfReader(f).pages:
                            text += page.extract_text() or ""
                elif file_path.endswith('.docx'):
                    text = docx2txt.process(file_path)
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                
                if not text.strip():
                    print(f"  Пустой файл")
                    continue
                    
            except Exception as e:
                print(f"  Ошибка чтения: {e}")
                continue
            
            words = text.split()
            for i in range(0, len(words), CHUNK_SIZE - CHUNK_OVERLAP):
                chunk = " ".join(words[i:i+CHUNK_SIZE])
                if len(chunk) > 50:
                    chunks.append(chunk)
                    sources.append(os.path.basename(file_path))
    
    if files_found == 0:
        print(f"В папке {DOCS_PATH} нет поддерживаемых файлов")
    else:
        print(f"Обработано файлов: {files_found}")
    
    return chunks, sources

def build_index(chunks):
    print(f"Загружаем эмбеддинг модель: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    
    print("Создаем эмбеддинги для чанков...")
    embeddings = model.encode(chunks, show_progress_bar=True)
    
    print("Строим FAISS индекс...")
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings.astype('float32'))
    
    return index, embeddings

if __name__ == "__main__":
    print("RAG - ИНДЕКСАЦИЯ ДОКУМЕНТОВ")
    print(f"Папка с документами: {DOCS_PATH}")
    print(f"Индекс будет сохранен: {INDEX_PATH}")

    
    os.makedirs(os.path.join(BASE_PATH, "index"), exist_ok=True)
    
    chunks, sources = load_and_chunk_documents()
    
    if not chunks:
        print("\nНет документов для индексации")
        print("   Добавьте файлы (.txt, .pdf, .docx, .md) в папку:")
        print(f"   {DOCS_PATH}")
        exit(1)
    
    print(f"\nСтатистика:")
    print(f"   - Всего чанков: {len(chunks)}")
    print(f"   - Уникальных файлов: {len(set(sources))}")
    
    index, _ = build_index(chunks)
    
    faiss.write_index(index, INDEX_PATH)
    with open(CHUNKS_PATH, 'w', encoding='utf-8') as f:
        json.dump({"chunks": chunks, "sources": sources}, f, ensure_ascii=False)
    
    print(f"Индекс сохранен: {INDEX_PATH}")
    print(f"Чанки сохранены: {CHUNKS_PATH}")
    print(f"Размер индекса: {os.path.getsize(INDEX_PATH) / 1024:.0f} KB")