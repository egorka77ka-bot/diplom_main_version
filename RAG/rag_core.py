import json
import os
import sys
from sentence_transformers import SentenceTransformer
import faiss
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

# Конфигурация
RAG_PATH = "C:\\Working\\diplom\\rag_sasha"
INDEX_PATH = os.path.join(RAG_PATH, "index", "faiss_index.bin")
CHUNKS_PATH = os.path.join(RAG_PATH, "index", "chunks.json")
TOP_K = 5
MAX_CHUNKS = 3000  # Все чанки

class RAGCore:
    """RAG - загружается один раз и продолжаетработу до отмены"""
    
    def __init__(self):
        print("Загрузка RAGа...")
        
        # Загружаем индекс
        print(f"Чтение индекса: {INDEX_PATH}")
        self.index = faiss.read_index(INDEX_PATH)
        
        # Загружаем чанки
        print(f"Чтение чанков: {CHUNKS_PATH}")
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.chunks = data["chunks"][:MAX_CHUNKS]
            self.sources = data["sources"][:MAX_CHUNKS]
        
        # Загружаем модель эмбеддингов
        print("Загрузка модели эмбеддингов...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
        print(f"RAG готов")
        #print(f"   Источников: {len(set(self.sources))}")
    
    def search(self, query, k=TOP_K, max_chars=2000):
        """Поиск по запросу"""
        query_vec = self.embedder.encode([query])
        distances, indices = self.index.search(query_vec.astype('float32'), k)
        
        results = []
        total_len = 0
        for idx in indices[0]:
            if idx < len(self.chunks):
                text = self.chunks[idx]
                if len(text) > 500:
                    text = text[:500] + "..."
                
                if total_len + len(text) < max_chars:
                    results.append({
                        "source": self.sources[idx],
                        "text": text,
                        "relevance": float(distances[0][list(indices[0]).index(idx)])
                    })
                    total_len += len(text)
        
        return results
    
    def get_context(self, query, k=TOP_K, max_chars=2000):
        """Получить контекст в виде текста"""
        results = self.search(query, k, max_chars)
        if not results:
            return "Релевантные документы не найдены"
        
        parts = []
        for r in results:
            parts.append(f"[ИСТОЧНИК: {r['source']}]\n{r['text']}")
        
        return "\n\n---\n\n".join(parts)

# HTTP Сервер для обработки запросов
class RAGHandler(BaseHTTPRequestHandler):
    rag = None  # Будет установлен при запуске
    
    def do_GET(self):
        """Обработка GET запросов /?q=запрос"""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if parsed.path == '/':
            if 'q' in params:
                query = params['q'][0]
                k = int(params.get('k', [TOP_K])[0])
                
                results = self.rag.search(query, k)
                response = json.dumps(results, ensure_ascii=False)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(response.encode('utf-8'))
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing q parameter")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Отключаем лишние логи
        pass

def run_server(port=8080):
    """Запуск HTTP сервера"""
    server = HTTPServer(('localhost', port), RAGHandler)
    print(f"RAG сервер запущен на http://localhost:{port}")
    #print("   Используйте: http://localhost:8080/?q=ваш запрос")
    print("Нажмите Ctrl+C для остановки")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Остановка RAG сервера")

if __name__ == "__main__":
    # Создаем RAG
    RAGHandler.rag = RAGCore()
    
    # Запускаем сервер
    run_server()