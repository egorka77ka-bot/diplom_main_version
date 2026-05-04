"""
Модуль для генерации отчетов по моделированию угроз информационной безопасности.
Основан на методических документах ФСТЭК России.
Версия: 3.1 (с поддержкой метаданных RAG и валидацией источников)
"""

import os
import json
import glob
import time
import pickle
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import PyPDF2
import docx2txt
import requests
from pathlib import Path
# Импорты LangChain
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.callbacks.manager import CallbackManager
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import OllamaLLM

# ================ КОНФИГУРАЦИЯ ================
class DetailedCallbackHandler(BaseCallbackHandler):
    """Подробный логгер для цепочек и LLM."""
    def __init__(self):
        self.chain_start_time = None
        self.llm_start_time = None

    def on_chain_start(self, serialized, inputs, **kwargs):
        self.chain_start_time = time.time()
        print(f"[CHAIN] ▶️ Цепочка запущена")

    def on_chain_end(self, outputs, **kwargs):
        elapsed = time.time() - self.chain_start_time if self.chain_start_time else 0
        output_len = len(str(outputs)) if outputs else 0
        print(f"[CHAIN] ⏹️ Цепочка завершена за {elapsed:.2f} сек, длина ответа: {output_len} символов")

    def on_llm_start(self, serialized, prompts, **kwargs):
        self.llm_start_time = time.time()
        print(f"[LLM] 🧠 Запрос к модели...")

    def on_llm_end(self, response, **kwargs):
        elapsed = time.time() - self.llm_start_time if self.llm_start_time else 0
        # Пробуем извлечь информацию о токенах из llm_output
        token_info = None
        if hasattr(response, 'llm_output') and response.llm_output:
            token_info = response.llm_output.get('token_usage', None)
        if token_info:
            print(f"[LLM] ⏱️ Модель ответила за {elapsed:.2f} сек. Токенов: {token_info}")
        else:
            print(f"[LLM] ⏱️ Модель ответила за {elapsed:.2f} сек")

    def on_chain_error(self, error, **kwargs):
        print(f"[ERROR] ❌ Ошибка в цепочке: {error}")

    def on_llm_error(self, error, **kwargs):
        print(f"[ERROR] ❌ Ошибка модели: {error}")

class LoggingCallbackHandler(BaseCallbackHandler):
    def __init__(self):
        self.start_time = None
        self.token_count = 0

    def on_llm_start(self, serialized, prompts, **kwargs):
        print(f"\nНачало генерации...")
        self.start_time = time.time()

    def on_llm_end(self, response, **kwargs):
        elapsed = time.time() - self.start_time if self.start_time else 0
        if hasattr(response, 'llm_output') and response.llm_output:
            token_info = response.llm_output.get('token_usage', {})
            print(f"Генерация завершена за {elapsed:.2f} сек")
            if token_info:
                print(f"Использовано токенов: {token_info}")
        else:
            print(f"Генерация завершена за {elapsed:.2f} сек (метаданные не предоставлены)")

    def on_llm_new_token(self, token: str, **kwargs):
        # Печатает токены в реальном времени (может замедлить вывод, оставляем закомментированным)
        print(token, end='', flush=True)
        pass

    def on_chain_start(self, serialized, inputs, **kwargs):
        print(f"[CHAIN] Цепочка запущена с входами: {str(inputs)[:200]}...")

    def on_chain_end(self, outputs, **kwargs):
        print(f"[CHAIN] Цепочка завершена. Длина выхода: {len(str(outputs))} символов")
# Пути к данным
RESULTS_DIR = "model_results"
COMPANY_DOCS_PATH = "./company_docs"
SCANS_PATH = ".\\local-rag-mcp\\src\\docs"
RAG_SERVER_URL = "http://localhost:8080"
CHUNKS_PATH = Path("local-rag-mcp/src/data/chunks_with_metadata.pkl")

# Создание директории для результатов
os.makedirs(RESULTS_DIR, exist_ok=True)


# ================ ФУНКЦИЯ ВАЛИДАЦИИ ИСТОЧНИКОВ ================

def validate_sources_in_chapter(chapter_text: str, expected_sources: List[Dict]) -> Dict:
    """Проверяет наличие маркеров источников в сгенерированной главе"""
    
    # Ищем все маркеры [Источник: ...]
    source_markers = re.findall(r'\[Источник:\s*([^\]]+)\]', chapter_text)
    
    # Извлекаем имена файлов из ожидаемых источников
    expected_filenames = set()
    for src in expected_sources:
        filename = src.get('filename', '')
        if filename:
            expected_filenames.add(filename)
    
    # Проверяем, использованы ли ожидаемые источники
    used_files = set(marker.strip() for marker in source_markers)
    missing_sources = expected_filenames - used_files
    
    return {
        "has_markers": len(source_markers) > 0,
        "markers_count": len(source_markers),
        "used_files": list(used_files),
        "expected_files": list(expected_filenames),
        "missing_sources": list(missing_sources),
        "validation_passed": len(source_markers) > 0
    }


# ================ КЛАСС ДЛЯ РАБОТЫ С RAG (С МЕТАДАННЫМИ) ================

class RAGClient:
    """
    Клиент для подключения к RAG-серверу.
    Поддерживает HTTP-запросы и локальные чанки как fallback.
    Возвращает контекст с метаданными источников.
    """
    
    def __init__(self, server_url: str = RAG_SERVER_URL):
        self.server_url = server_url.rstrip('/')
        self.available = self._check_connection()
        self.local_chunks = self._load_local_chunks()
        
        if self.available:
            print(f"[INFO] Подключение к RAG серверу установлено: {self.server_url}")
        else:
            print(f"[WARNING] RAG сервер не доступен по адресу: {self.server_url}")
            if self.local_chunks:
                print("[INFO] Используются локальные чанки как резервный источник")
            else:
                print("[INFO] Для работы RAG требуется запустить: cd local-rag-mcp/src && uvicorn main:app --host 0.0.0.0 --port 8080")
    
    def _check_connection(self) -> bool:
        """Проверка доступности RAG сервера"""
        try:
            response = requests.get(f"{self.server_url}", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def _load_local_chunks(self):
        """Загрузка локальных чанков как резервный источник"""
        if CHUNKS_PATH.exists():
            try:
                with open(CHUNKS_PATH, "rb") as f:
                    chunks = pickle.load(f)
                print(f"[INFO] Загружено локальных чанков: {len(chunks)}")
                if chunks:
                    sample = chunks[0].get('metadata', {})
                    print(f"[INFO] Пример метаданных: {sample.get('filename', 'N/A')}")
                return chunks
            except Exception as e:
                print(f"[WARNING] Ошибка загрузки локальных чанков: {e}")
        return None
    
    def _search_local(self, query: str, k: int = 5) -> List[Dict]:
        """Поиск по локальным чанкам (keyword-based)"""
        if not self.local_chunks:
            return []
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        scored = []
        for chunk in self.local_chunks:
            text = chunk.get('text', '').lower()
            metadata = chunk.get('metadata', {})
            
            # Базовая оценка: количество совпадений слов в тексте
            score = sum(1 for word in query_words if word in text)
            
            # Бонус за совпадение в имени файла
            filename = metadata.get('filename', '').lower()
            score += sum(3 for word in query_words if word in filename)
            
            # Бонус за совпадение в пути
            source = chunk.get('source', '').lower()
            score += sum(2 for word in query_words if word in source)
            
            if score > 0:
                scored.append((score, chunk))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        return [chunk for _, chunk in scored[:k]]
    
    def _parse_http_results(self, results: List[Dict]) -> List[Dict]:
        """Парсинг результатов HTTP-запроса в единый формат"""
        parsed = []
        for r in results:
            parsed.append({
                "text": r.get('text', r.get('content', '')),
                "source": r.get('source', r.get('file', 'unknown')),
                "metadata": r.get('metadata', {}),
                "score": r.get('score', r.get('relevance', 0))
            })
        return parsed
    
    def get_context_with_metadata(self, query: str, k: int = 200) -> Tuple[str, List[Dict]]:
        """
        Получение релевантного контекста из RAG с метаданными.
        Возвращает (контекст_как_строку, список_источников_с_метаданными)
        """
        results = []
        
        # Пытаемся получить данные через HTTP
        if self.available:
            try:
                response = requests.get(
                    f"{self.server_url}/query",
                    params={"q": query, "k": k},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Обрабатываем разные форматы ответа
                    if isinstance(data, dict):
                        if "results" in data:
                            results = self._parse_http_results(data["results"])
                        elif "documents" in data:
                            results = self._parse_http_results(data["documents"])
                        elif "chunks" in data:
                            results = self._parse_http_results(data["chunks"])
                    elif isinstance(data, list):
                        results = self._parse_http_results(data)
                        
            except Exception as e:
                print(f"[WARNING] Ошибка HTTP-запроса: {e}")
        
        # Если HTTP не вернул результатов, используем локальные чанки
        if not results and self.local_chunks:
            results = self._search_local(query, k)
        
        if not results:
            return "", []
        
        context_parts = []
        sources = []
        
        for r in results:
            text = r.get('text', '')
            metadata = r.get('metadata', {})
            source = metadata.get('source', r.get('source', 'unknown'))
            filename = metadata.get('filename', source.split('/')[-1] if '/' in source else source)
            chunk_id = metadata.get('chunk_id', '?')
            chunk_total = metadata.get('chunk_total', '?')
            score = r.get('score', 0)
            
            # Упрощенный маркер источника - легче для копирования LLM
            metadata_str = f"[Источник: {filename}]"
            context_parts.append(f"{metadata_str}\n{text}")
            
            # Сохраняем источник для отчёта
            sources.append({
                "filename": filename,
                "source": source,
                "chunk_id": chunk_id,
                "chunk_total": chunk_total,
                "score": score,
                "text_preview": text[:200] + "..." if len(text) > 200 else text
            })
        
        return "\n\n---\n\n".join(context_parts), sources
    
    def get_context(self, query: str, k: int = 3) -> str:
        """
        Получение релевантного контекста из RAG (только текст, без метаданных).
        Сохраняется для обратной совместимости.
        """
        context, _ = self.get_context_with_metadata(query, k)
        return context


# ================ ИНИЦИАЛИЗАЦИЯ LLM ================
    
print("[INFO] Инициализация языковой модели...")
start_time = time.time()

llm = OllamaLLM(
    #model="qwen3:4b-q8_0",
    #model="qwen2.5-coder:7b-instruct-q4_k_m",
    model="qwen3.5:4b-q8_0",
    #model="hf.co/Mungert/Qwen3-8B-abliterated-GGUF:q3_k_s",
    #model="qwen3:8b",
    base_url="http://localhost:11434",
    temperature=0.2,
    num_ctx=50000,
    num_predict=20000,
    top_k=130,
    top_p=0.9,
)

init_time = time.time() - start_time
print(f"[INFO] Языковая модель инициализирована за {init_time:.2f} сек")


# ================ КЛАСС ДЛЯ ЧТЕНИЯ ДОКУМЕНТОВ ================

class CompanyDocumentReader:
    """Класс для чтения документов компании различных форматов"""
    
    SUPPORTED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.csv', '.json', '.md'}
    
    def __init__(self, docs_path: str):
        self.docs_path = docs_path
        
    def read_all_documents(self, max_docs: int = 100, max_size: int = 3000) -> List[Dict]:
        """Чтение всех документов с ограничениями"""
        print(f"\n[INFO] Чтение документов из: {self.docs_path}")
        
        if not os.path.exists(self.docs_path):
            print(f"[ERROR] Директория не найдена: {self.docs_path}")
            return []
        
        # Сбор файлов
        all_files = []
        for ext in self.SUPPORTED_EXTENSIONS:
            all_files.extend(glob.glob(os.path.join(self.docs_path, f"*{ext}")))
        
        print(f"[INFO] Найдено файлов: {len(all_files)}")
        
        # Чтение файлов
        documents = []
        for i, file_path in enumerate(all_files):
            if i >= max_docs:
                print(f"[INFO] Достигнут лимит документов ({max_docs})")
                break
                            
            print(f"  [INFO] Чтение: {os.path.basename(file_path)}")
            content = self._read_file(file_path)
            
            if content and len(content.strip()) > 0:
                # Ограничиваем размер
                if len(content) > max_size:
                    content = content[:max_size] + "\n...[текст обрезан]"
                
                documents.append({
                    "file": os.path.basename(file_path),
                    "content": content,
                    "type": os.path.splitext(file_path)[1].lower(),
                    "full_path": file_path
                })
        
        print(f"[INFO] Загружено документов: {len(documents)}")
        return documents
    
    def _read_file(self, file_path: str) -> str:
        """Чтение файла в зависимости от расширения"""
        ext = os.path.splitext(file_path)[1].lower()
        
        try:           
            if ext in ['.txt', '.md', '.csv']:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            elif ext == '.pdf':
                text = []
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    for page in pdf_reader.pages[:20]:
                        page_text = page.extract_text()
                        if page_text:
                            text.append(page_text)
                return '\n'.join(text)
            
            elif ext == '.docx':
                return docx2txt.process(file_path)
            
            elif ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return json.dumps(data, ensure_ascii=False, indent=2)
            
        except Exception as e:
            print(f"[ERROR] Ошибка чтения {file_path}: {e}")
            return ""
        
        return ""


# ================ ПРОМПТЫ С ЦЕПОЧКАМИ РАССУЖДЕНИЙ ================

def create_chain(prompt):
    """Создание цепочки LangChain"""
    return prompt | llm | StrOutputParser()
    # Примечание: передача колбэков в цепочку может потребоваться при вызове invoke, см. ниже

# Глава 4: Краткое описание процесса проведения внешнего и внутреннего тестирования
chapter1_prompt = PromptTemplate(
    input_variables=["company_context", "rag_context"],
    template="""Ты эксперт по информационной безопасности. Составь ГЛАВУ 5 отчета по моделированию угроз.

Используй ТОЛЬКО данные предоставленные ниже:

Информация из базы знаний (RAG):
{rag_context}

Инструкции по формированию отчета:
В ответе должны быть перечислены уязвимости только с показателем CVSS от 6.0 до 10.0.

Укажи максимум по 10 уязвимостей

Название главы:
Глава 5. ПЕРЕЧЕНЬ ВЫЯВЛЕННЫХ УЯЗВИМОСТЕЙ ИНФОРМАЦИОННОЙ СИСТЕМЫ
Цель главы
Представить полный перечень выявленных уязвимостей с детальным описанием каждой уязвимости.

Обязательные элементы
Перечень уязвимостей периметра информационной системы

Перечень уязвимостей внутренней инфраструктуры

Описание каждой уязвимости (идентификатор CVE/BDU, компонент, версия, тип)

Приложение отчетов, сформированных средствами выявления уязвимостей

Структура главы
text
5. ПЕРЕЧЕНЬ ВЫЯВЛЕННЫХ УЯЗВИМОСТЕЙ ИНФОРМАЦИОННОЙ СИСТЕМЫ

5.1. Уязвимости периметра информационной системы
5.1.1. Уязвимости телекоммуникационного оборудования и межсетевых экранов
[таблица: идентификатор, компонент, описание]
5.1.2. Уязвимости сетевых служб и сервисов
[таблица: идентификатор, компонент, описание]
5.1.3. Уязвимости веб-приложений
[таблица: идентификатор, компонент, описание]

5.2. Уязвимости внутренней инфраструктуры
5.2.1. Уязвимости операционных систем
[таблица: идентификатор, компонент, описание]
5.2.2. Уязвимости систем управления базами данных
[таблица: идентификатор, компонент, описание]
5.2.3. Уязвимости прикладного программного обеспечения
[таблица: идентификатор, компонент, описание]
5.2.4. Уязвимости средств виртуализации и контейнеризации
[таблица: идентификатор, компонент, описание]
5.2.5. Уязвимости конфигурации сетевой инфраструктуры
[таблица: идентификатор, компонент, описание]

5.3. Сводный перечень выявленных уязвимостей
[таблица: №, идентификатор, компонент, уровень опасности, описание]

СТРОГОЕ ПРАВИЛО ЦИТИРОВАНИЯ:
После КАЖДОГО факта, взятого из текста, ОБЯЗАТЕЛЬНО ставь маркер [Источник: имя_файла] точно так, как он указан в предоставленных данных.
НЕ придумывай свои маркеры - копируй их из текста выше!

Если в данных нет информации - напиши "Информация не предоставлена".
НЕ ВЫДУМЫВАЙ названия инструментов, версии, номера сертификатов!
"""
)

# ================ ГЕНЕРАЦИЯ ОТДЕЛЬНЫХ ГЛАВ ================

def generate_chapter(chapter_number, prompt_template, data, expected_sources=None):
    print(f"\n[INFO] 🚀 Генерация главы {chapter_number}...")
    start_time = time.time()

    chain = create_chain(prompt_template)

    # Создаём колбэк для этого запуска
    callback_handler = DetailedCallbackHandler()
    
    result = None
    validation = None

    try:
        # Прямая передача колбэков (работает в актуальных версиях LangChain)
        result = chain.invoke(
            data,
            callbacks=[callback_handler]
        )
        
        # Выводим начало ответа для быстрой проверки
        if result:
            print(f"[INFO] Глава {chapter_number}: получен ответ длиной {len(result)} символов.")
            print(f"[DEBUG] Первые 300 символов ответа:\n{result[:300]}...")
        else:
            print(f"[WARNING] Глава {chapter_number}: ответ пуст!")

        # Валидация источников, если нужно
        if expected_sources is not None:
            validation = validate_sources_in_chapter(result, expected_sources)
            if validation["validation_passed"]:
                print(f"[INFO] Глава {chapter_number}: найдено маркеров: {validation['markers_count']}")
                if validation['missing_sources']:
                    print(f"[WARNING] Не использованы источники: {validation['missing_sources'][:5]}")
            else:
                print(f"[WARNING] Глава {chapter_number}: маркеры источников не найдены!")
                
    except Exception as e:
        print(f"[ERROR] ❌ Ошибка при генерации главы {chapter_number}: {e}")
        import traceback
        traceback.print_exc()
        # Возвращаем пустой результат и метаданные об ошибке
        result = f"Ошибка генерации: {e}"
        validation = {"error": str(e)}

    elapsed = time.time() - start_time
    print(f"[INFO] ⏱️ Обработка главы {chapter_number} завершена за {elapsed:.2f} сек")
    
    return result, validation


def generate_all_chapters(scan_files: List[str], company_docs: List[Dict], rag: RAGClient) -> Dict:
    """Генерация первых двух глав отчета"""
    
    print("\n" + "=" * 70)
    print("ГЕНЕРАЦИЯ ГЛАВ ОТЧЕТА ПО МОДЕЛИРОВАНИЮ УГРОЗ")
    print("=" * 70)
    
    total_start = time.time()
    
    # Подготовка данных из документов компании
    docs_text = "\n\n---\n\n".join([
        f"Файл: {doc['file']}\n{doc['content']}" 
        for doc in company_docs[:1]
    ])
    
    # Чтение данных сканирования
    scan_data_parts = []
    for file_path in scan_files[:130]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if len(content) > 3000:
                    content = content[:3000] + "...[текст обрезан]"
                scan_data_parts.append(f"Файл: {os.path.basename(file_path)}\n{content}")
        except Exception as e:
            print(f"[ERROR] Ошибка чтения {file_path}: {e}")
    
    scan_text = "\n\n---\n\n".join(scan_data_parts)
    
    # Получение RAG контекста через API для глав 1 и 2
    print("\n[INFO] Получение контекста из RAG через API...")
    rag_start = time.time()
    # Запросы к RAG API для глав 1 и 2 (k=15 для большего контекста)
    
   # 4. Описание внешнего и внутреннего тестирования
    rag_ctx_1, rag_sources_1 = rag.get_context_with_metadata(
         "network scan nmap nmap_summary scan_results"
             " open_ports port state service version raw_output metadata source tool scan_type full_port_scan full_network_scan IP address IPv4 subnet network_range scan_time timestamp"
            " cvss: 3.7 full_cve ghsa_id: cve_id: url: html_url: network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version summary network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version  port:  state: service: version summary port:  state: service: version summary"
            " protocol http https ftp sftp ssh telnet rdp smb cifs nfs ldap ldaps kerberos dns dhcp snmp smtp pop3 imap ntp syslog netbios wins"
         "уязвимость позволяющая нарушителю связанная с чтением за границами буфера связанная с записью за границами буфера связанная с использованием памяти после освобождения связанная с разыменованием нулевого указателя связанная с непринятием мер по нейтрализации связанная с непринятием мер по защите структуры связанная с недостаточной проверкой входных данных связанная с недостатками разграничения доступа связанная с ошибками синхронизации связанная с неверным ограничением имени пути вызвать отказ в обслуживании повысить свои привилегии выполнить произвольный код раскрыть защищаемую информацию получить несанкционированный доступ оказать воздействие на конфиденциальность оказать воздействие на целостность оказать воздействие на доступность скомпрометировать уязвимую систему получить полный контроль над устройством программного обеспечения для управления программного обеспечения для обработки программного обеспечения для взаимодействия программной платформы для разработки набора служебных утилит командной строки ядра операционной системы linux микропрограммного обеспечения маршрутизаторов микропрограммного обеспечения беспроводных микропрограммного обеспечения межсетевых экранов драйвера поддержки сетевых адаптеров пакета программ сетевого взаимодействия системы управления базами данных интерпретатора языка программирования библиотеки для работы с данными компонента операционной системы модуля безопасности ядра инструмента для мониторинга средства криптографической защиты сервера приложений веб интерфейса управления службы управления сетевыми соединениями нарушителю действующему удаленно нарушителю действующему локально копированием буфера без проверки размера переполнением буфера в динамической памяти отсутствием проверки подлинности данных использованием жестко закодированных данных возможностью обхода существующих ограничений недостатками процедуры аутентификации недостатками контроля доступа к ресурсам ошибками при управлении привилегиями недостаточной защитой служебных данных нарушением механизма защиты информации"
         , k=130
)
    
    rag_elapsed = time.time() - rag_start
    print(f"[INFO] Контекст из RAG API получен за {rag_elapsed:.2f} сек")
    
    # Вывод информации об источниках
    all_sources = []
    for i, sources in enumerate([rag_sources_1], 1):
        if sources:
            print(f"[INFO] Глава {i}: найдено источников в RAG: {len(sources)}")
            for src in sources[:130]:
                print(f"       - {src['filename']} (чанк {src['chunk_id']}/{src['chunk_total']}, релевантность: {src['score']:.3f})")
            all_sources.extend(sources)
        else:
            print(f"[WARNING] Глава {i}: источники в RAG не найдены")
    
    if all_sources:
        unique_sources = set([s['filename'] for s in all_sources])
        print(f"[INFO] Всего найдено уникальных источников: {len(unique_sources)}")
    
    # Генерация глав
    chapters = {}
    
    ch1, val1 = generate_chapter(1, chapter1_prompt, {
        "company_context": docs_text,
        "rag_context": rag_ctx_1
    }, expected_sources=rag_sources_1)
    chapters["chapter1"] = ch1
    chapters["_validation_chapter1"] = val1
        
        
    total_elapsed = time.time() - total_start
    print(f"\nВсе главы созданы. Общее время: {total_elapsed:.2f} сек ({total_elapsed/60:.2f} мин)")
    
    chapters["_rag_sources"] = all_sources
    
    return chapters


# ================ СОХРАНЕНИЕ РЕЗУЛЬТАТОВ ================

def save_chapters(chapters: Dict, scan_files: List[str]) -> Dict:
    """Сохранение глав отчета в отдельные файлы"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n[INFO] Сохранение результатов в: {RESULTS_DIR}")
    
    saved_files = {}
    
    # Сохраняем только главы 1 и 2
    for i in range(1, 4):
        chapter_key = f"chapter{i}"
        if chapter_key in chapters:
            chapter_file = os.path.join(RESULTS_DIR, f"chapter_{i:02d}_{timestamp}.txt")
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(chapters[chapter_key])
            
            file_size = os.path.getsize(chapter_file) / 1024
            print(f"[INFO] Глава {i} сохранена: {os.path.basename(chapter_file)} ({file_size:.1f} KB)")
            saved_files[f"chapter_{i}"] = chapter_file
    
    # Сохраняем информацию об источниках RAG
    if "_rag_sources" in chapters and chapters["_rag_sources"]:
        sources_file = os.path.join(RESULTS_DIR, f"rag_sources_{timestamp}.json")
        with open(sources_file, 'w', encoding='utf-8') as f:
            json.dump(chapters["_rag_sources"], f, indent=2, ensure_ascii=False)
        print(f"[INFO] Источники RAG сохранены: {os.path.basename(sources_file)}")
        saved_files["rag_sources"] = sources_file
    
    # Сохраняем результаты валидации
    validation_results = {}
    for i in range(1, 4):
        val_key = f"_validation_chapter{i}"
        if val_key in chapters and chapters[val_key]:
            validation_results[f"chapter_{i}"] = chapters[val_key]
    
    if validation_results:
        validation_file = os.path.join(RESULTS_DIR, f"validation_{timestamp}.json")
        with open(validation_file, 'w', encoding='utf-8') as f:
            json.dump(validation_results, f, indent=2, ensure_ascii=False)
        print(f"[INFO] Результаты валидации сохранены: {os.path.basename(validation_file)}")
        saved_files["validation"] = validation_file
    
    # Метаданные
    metadata = {
        "generation_timestamp": timestamp,
        "generation_time": datetime.now().isoformat(),
        "chapters": saved_files,
        "scan_files_used": [os.path.basename(f) for f in scan_files[:10]],
        "rag_sources_count": len(chapters.get("_rag_sources", [])),
        "validation_summary": {
            f"chapter_{i}": {
                "passed": chapters.get(f"_validation_chapter{i}", {}).get("validation_passed", False) if chapters.get(f"_validation_chapter{i}") else None,
                "markers": chapters.get(f"_validation_chapter{i}", {}).get("markers_count", 0) if chapters.get(f"_validation_chapter{i}") else 0
            }
            for i in range(1, 3)
            if chapters.get(f"_validation_chapter{i}")
        }
    }
    
    meta_file = os.path.join(RESULTS_DIR, f"metadata_{timestamp}.json")
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"[INFO] Метаданные сохранены: {os.path.basename(meta_file)}")
    
    return {
        "chapters": saved_files,
        "metadata": meta_file,
        "timestamp": timestamp
    }


# ================ ОСНОВНАЯ ФУНКЦИЯ ================

def main():
    """Основная функция программы"""
    
    print("=" * 70)
    print("ГЕНЕРАТОР ОТЧЕТОВ ПО МОДЕЛИРОВАНИЮ УГРОЗ")
    print("Версия 3.1 | С поддержкой метаданных RAG и валидацией источников")
    print("=" * 70)
    
    program_start = time.time()
    
    # Проверка наличия RAG сервера
    rag = RAGClient()
    
    if not rag.available and not rag.local_chunks:
        print("\n[WARNING] RAG сервер не запущен и нет локальных чанков!")
        print(f"  Для получения расширенного контекста запустите:")
        print(f"  cd {os.path.abspath('local-rag-mcp/src')}")
        print(f"  uvicorn main:app --host 0.0.0.0 --port 8080")
        print("\n  Продолжить без RAG? (y/n): ", end="")
        
        response = input().strip().lower()
        if response != 'y':
            print("[INFO] Работа программы завершена по запросу пользователя")
            return
    
    # Чтение документов компании
    reader = CompanyDocumentReader(COMPANY_DOCS_PATH)
    company_docs = reader.read_all_documents()
    
    # Поиск файлов сканирования
    scan_files = glob.glob(os.path.join(SCANS_PATH, "*.json"))
    scan_files.sort()
    
    if not scan_files:
        print("[ERROR] Файлы сканирования не найдены")
        print(f"       Проверьте наличие файлов *.json в: {SCANS_PATH}")
        return
    
    print(f"\n[INFO] Найдено файлов сканирования: {len(scan_files)}")
    print(f"[INFO] Загружено документов компании: {len(company_docs)}")
    
    print("\n[INFO] Параметры генерации:")
    print(f"       - Документов для анализа: {min(len(company_docs), 1)}")
    print(f"       - Файлов сканирования: {min(len(scan_files), 10)}")
    print(f"       - Генерируются главы: 1-2")
    print(f"       - Запрашивается чанков из RAG: 15")
    
    response = input("\nНачать генерацию отчета? (y/n): ").strip().lower()
    if response != 'y':
        print("[INFO] Генерация отменена пользователем")
        return
    
    try:
        # Генерация глав
        chapters = generate_all_chapters(scan_files, company_docs, rag)
        
        # Сохранение
        saved = save_chapters(chapters, scan_files)
        
        total_elapsed = time.time() - program_start
        
        print("\n" + "=" * 70)
        print("ГЕНЕРАЦИЯ ОТЧЕТА ЗАВЕРШЕНА")
        print("=" * 70)
        print(f"\n[INFO] Статистика выполнения:")
        print(f"       - Сгенерировано глав: {len([k for k in chapters.keys() if k.startswith('chapter')])}")
        print(f"       - Общее время: {total_elapsed:.2f} сек ({total_elapsed/60:.2f} мин)")
        print(f"       - Результаты сохранены в: {RESULTS_DIR}")
        print(f"       - Использовано RAG источников: {len(chapters.get('_rag_sources', []))}")
        print("\n[INFO] Сгенерированные главы:")
        
        for i in range(1, 3):
            chapter_key = f"chapter{i}"
            if chapter_key in chapters:
                print(f"       - Глава {i}: chapter_{i:02d}_{saved['timestamp']}.txt")
        
        # Вывод информации о валидации
        print("\n[INFO] Результаты валидации источников:")
        for i in range(1, 3):
            val_key = f"_validation_chapter{i}"
            if val_key in chapters and chapters[val_key]:
                val = chapters[val_key]
                status = "✅" if val.get("validation_passed") else "❌"
                print(f"       {status} Глава {i}: найдено маркеров: {val.get('markers_count', 0)}")
                if val.get('missing_sources'):
                    print(f"          Неиспользованные источники: {val['missing_sources'][:3]}")
        
    except KeyboardInterrupt:
        print("\n\n[INFO] Генерация прервана пользователем")
    except Exception as e:
        print(f"\n[ERROR] Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()