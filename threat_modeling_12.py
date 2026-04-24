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
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import OllamaLLM

# ================ КОНФИГУРАЦИЯ ================

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
    num_predict=50000,
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


# Глава 1: Сведения об основании, заказчике и целях работы
chapter1_prompt = PromptTemplate(
    input_variables=["company_context", "rag_context"],
    template="""Ты эксперт по информационной безопасности. Составь ГЛАВУ 1 отчета по моделированию угроз.

Используй ТОЛЬКО данные предоставленные ниже:




Информация из базы знаний (RAG):
{rag_context}
Пиши на все пункты и вопросы максимально полные ответы
Глава 1. СВЕДЕНИЯ ОБ ОСНОВАНИИ, ЗАКАЗЧИКЕ И ЦЕЛЯХ РАБОТЫ
Цель главы
Определить правовые основания проведения работ, установить цели и задачи анализа защищённости, идентифицировать участников.

Обязательные элементы
Основание для проведения работ (номер и дата документа)

Полное наименование организации-заказчика

Полное наименование организации-исполнителя

Сроки проведения работ (дата начала и окончания)

Цели проведения анализа защищённости

Конкретные задачи (минимум 3)

Структура главы с примерами правильного ответа
text
1. СВЕДЕНИЯ ОБ ОСНОВАНИИ, ЗАКАЗЧИКЕ И ЦЕЛЯХ РАБОТЫ

1.1. Основание для проведения работ
[текст с указанием документа]
Анализ защищённости проведён на основании договора № [номер] от [дата] г., заключенного между Заказчиком и Исполнителем, а также технического задания на оказание услуг по проведению аудита информационной безопасности.

1.2. Сведения о заказчике и исполнителе
[текст с названиями организаций]
Заказчик: [полное наименование организации]
Исполнитель: [полное наименование организации]

1.3. Сроки проведения работ
[текст с датами]
Начало работ: [дата] г.
Окончание работ: [дата] г.

1.4. Цели и задачи анализа защищённости
[текст с целями и задачами]
Цель: оценка текущего уровня защищённости информационной системы и подготовка рекомендаций по повышению защищённости.
Задачи:
- сбор и анализ исходной информации об информационной системе
- инвентаризация сетевых адресов, портов и служб
- выявление уязвимостей информационной системы
- оценка критичности выявленных уязвимостей
- разработка рекомендаций по устранению уязвимостей

СТРОГОЕ ПРАВИЛО ЦИТИРОВАНИЯ:
После КАЖДОГО факта, взятого из текста, ОБЯЗАТЕЛЬНО ставь маркер [Источник: имя_файла] точно так, как он указан в предоставленных данных.
НЕ придумывай свои маркеры - копируй их из текста выше!

Если в данных нет информации - напиши "Информация не предоставлена".
НЕ ВЫДУМЫВАЙ названия инструментов, версии, номера сертификатов!
"""
)

# Глава 4: Краткое описание процесса проведения внешнего и внутреннего тестирования
chapter4_prompt = PromptTemplate(
    input_variables=["company_context", "rag_context"],
    template="""Ты эксперт по информационной безопасности. Составь ГЛАВУ 4 отчета по моделированию угроз.

Используй ТОЛЬКО данные предоставленные ниже:

Информация из базы знаний (RAG):
{rag_context}

Глава 4. КРАТКОЕ ОПИСАНИЕ ПРОЦЕССА ПРОВЕДЕНИЯ ВНЕШНЕГО И ВНУТРЕННЕГО ТЕСТИРОВАНИЯ
Цель главы
Описать методологию, условия и процесс проведения внешнего и внутреннего сканирования информационной системы.

Обязательные элементы
Описание внешнего сканирования (С1)

Описание внутреннего сканирования (С2)

Применяемые методы анализа уязвимостей

Условия проведения сканирования (локально, удаленно, права доступа)

Границы проведения работ

Ограничения при проведении сканирования

Структура главы с примерами правильного ответа
text
4. КРАТКОЕ ОПИСАНИЕ ПРОЦЕССА ПРОВЕДЕНИЯ ВНЕШНЕГО И ВНУТРЕННЕГО ТЕСТИРОВАНИЯ

4.1. Внешнее сканирование (С1)

4.1.1. Границы проведения внешнего сканирования
Внешнее сканирование проводилось удаленно из сети Интернет. В границы работ включены публичные сетевые адреса информационной системы, а также связанные с ними доменные имена.
[описание периметра, перечень публичных адресов и доменных имен]

4.1.2. Методология внешнего сканирования
Внешнее сканирование выполнялось с использованием методов:
- пассивный анализ: сравнение версий ПО с базой данных уязвимостей
- активное сканирование: формирование тестовых запросов к сетевым службам и веб-приложениям
- ручной анализ: проверка конфигураций и уязвимостей кода
[описание методов: пассивные, активные, автоматизированные, ручные]

4.1.3. Результаты внешнего сканирования
В ходе внешнего сканирования выявлены открытые порты и службы на периметре, включая службы доменных имен, веб-серверы, службы удаленного доступа. Выявлены уязвимости веб-приложений и служб.
[краткое описание выявленных объектов и уязвимостей]

4.2. Внутреннее сканирование (С2)

4.2.1. Границы проведения внутреннего сканирования
Внутреннее сканирование проводилось в отношении внутренней инфраструктуры информационной системы, включая серверы, автоматизированные рабочие места, сетевое оборудование и средства защиты информации.
[описание внутренней инфраструктуры, перечень сегментов]

4.2.2. Условия проведения внутреннего сканирования
Сканирование проводилось удаленно с предоставлением защищенного подключения к внутренней инфраструктуре. Для проведения анализа была создана тестовая привилегированная учетная запись с административными правами доступа. Дополнительно проводилось сканирование без аутентификации для анализа прикладного ПО.
[локальное/удаленное подключение, права доступа, учетные записи]

4.2.3. Методология внутреннего сканирования
Внутреннее сканирование включало:
- сканирование интерфейсов внутренней инфраструктуры с использованием средств выявления уязвимостей
- поиск уязвимостей в банках данных угроз
- анализ конфигураций ОС, СУБД, веб-серверов
- проверку парольной политики и устойчивости паролей
[описание методов: сканирование интерфейсов, анализ конфигураций, проверка паролей]

4.2.4. Результаты внутреннего сканирования
В ходе внутреннего сканирования выявлены уязвимости программного обеспечения серверов и АРМ, недостатки конфигурации ОС и СУБД, уязвимости аутентификации.
[краткое описание выявленных объектов и уязвимостей]

4.3. Применяемые методы анализа уязвимостей
| № | Метод | Описание | Применение |
|----|-------|----------|------------|
| 1 | Сравнение версий ПО с БДУ | Пассивный метод в автоматизированном режиме | Выявление известных уязвимостей |
| 2 | Формирование тестовых запросов | Активный метод сканирования | Анализ поведения ПО |
| 3 | Анализ конфигураций и настроек | Ручной метод | Выявление недостатков конфигурации |
[таблица: метод, описание, применение]

4.4. Ограничения при проведении тестирования
При проведении анализа уязвимостей были установлены следующие ограничения:
- запрет на проведение активного сканирования на работающем технологическом оборудовании
- проведение тестирования в согласованные временные окна
- исключение из области тестирования отдельных систем и устройств
[описание ограничений, наложенных заказчиком]

СТРОГОЕ ПРАВИЛО ЦИТИРОВАНИЯ:
После КАЖДОГО факта, взятого из текста, ОБЯЗАТЕЛЬНО ставь маркер [Источник: имя_файла] точно так, как он указан в предоставленных данных.
НЕ придумывай свои маркеры - копируй их из текста выше!

Если в данных нет информации - напиши "Информация не предоставлена".
НЕ ВЫДУМЫВАЙ названия инструментов, версии, номера сертификатов!
"""
)

# ================ ГЕНЕРАЦИЯ ОТДЕЛЬНЫХ ГЛАВ ================

def generate_chapter(chapter_number: int, prompt_template: PromptTemplate, data: Dict, 
                     expected_sources: List[Dict] = None) -> Tuple[str, Dict]:
    """Генерация отдельной главы отчета с валидацией источников"""
    print(f"[INFO] Генерация главы {chapter_number}...")
    start_time = time.time()
    
    chain = create_chain(prompt_template)
    result = chain.invoke(data)
    
    # Валидация источников если переданы ожидаемые источники
    validation = None
    if expected_sources is not None:
        validation = validate_sources_in_chapter(result, expected_sources)
        if validation["validation_passed"]:
            print(f"[INFO] Глава {chapter_number}: найдено маркеров: {validation['markers_count']}")
            if validation['missing_sources']:
                print(f"[WARNING] Глава {chapter_number}: не использованы источники: {validation['missing_sources'][:5]}")
        else:
            print(f"[WARNING] Глава {chapter_number}: маркеры источников не найдены!")
    
    elapsed = time.time() - start_time
    print(f"[INFO] Глава {chapter_number} сгенерирована за {elapsed:.2f} сек")
    
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
    
    # 1. Основание, заказчик, исполнитель, сроки, цели, задачи
    rag_ctx_1, rag_sources_1 = rag.get_context_with_metadata(
    "Договор № г «» г именуемое в дальнейшем Заказчик в лице действующего на основании с одной стороны и именуемое в дальнейшем Исполнитель в лице действующего на основании с другой стороны заключили настоящий договор о нижеследующем Предмет договора Заказчик поручает а Исполнитель принимает на себя обязательство оказать услуги по Права и обязанности сторон Исполнитель обязуется Оказать услуги с надлежащим качеством и в соответствии с требованиями нормативных документов Заказчик обязуется Предоставить Исполнителю доступ Произвести оплату за оказанные услуги в срок Цена и порядок расчетов За выполненные работы оказанные услуги Заказчик выплачивает Исполнителю рублей в том числе НДС Оплата производится путем перечисления денежных средств на расчетный счет Исполнителя в течение банковских дней с даты подписания акта выполненных работ Ответственность сторон В случае неисполнения или ненадлежащего исполнения Договора Стороны несут ответственность в соответствии с действующим законодательством Российской Федерации Срок действия договора Настоящий договор вступает в силу с момента подписания и действует до полного исполнения обязательств Сторонами Конфиденциальность Стороны обязуются сохранять конфиденциальность информации Юридические адреса и реквизиты сторон УТВЕРЖДАЮ ТЕХНИЧЕСКОЕ ЗАДАНИЕ на оказание услуг по проведению аудита информационной безопасности Общие сведения Наименование работы Заказчик Исполнитель Срок выполнения работ Начало с даты подписания договора Окончание не позднее г Цели и задачи работы Целью работы является оценка текущего уровня защищенности и разработка рекомендаций по повышению защищенности Для достижения поставленной цели должны быть решены следующие задачи Границы проведения работ Объекты проведения работ Требования к выполнению работ Работы должны выполняться в соответствии с требованиями следующих нормативных документов Приказ ФСТЭК России от № Методика оценки угроз безопасности информации утв ФСТЭК России Политика информационной безопасности Заказчика Состав и содержание работ Этап Сбор и анализ исходных данных Этап Инструментальный аудит Этап Анализ уязвимостей и оценка рисков Этап Разработка рекомендаций и отчетной документации Требования к отчетной документации По результатам работ Исполнитель представляет Заказчику Отчет содержащий результаты проведенного аудита Требования к Исполнителю Исполнитель должен иметь действующую лицензию ФСТЭК России на деятельность по технической защите конфиденциальной информации Приложения Календарный план выполнения работ",
    k=130
)
    # Запросы к RAG API для глав 1 и 2 (k=15 для большего контекста)
    
   # 4. Описание внешнего и внутреннего тестирования
    rag_ctx_4, rag_sources_4 = rag.get_context_with_metadata(
        "network scan nmap nmap_summary scan_results"
        " open_ports port state service version raw_output metadata source tool scan_type full_port_scan full_network_scan IP address IPv4 subnet network_range scan_time timestamp"
        " cvss: 3.7 full_cve ghsa_id: cve_id: url: html_url: network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version summary network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version  port:  state: service: version summary port:  state: service: version summary"
        "внешнее сканирование external scanning внешний периметр external perimeter анализ из сети Интернет Internet facing assessment тестирование на проникновение penetration testing pen test black box white box grey box разведка reconnaissance footprinting сбор информации из открытых источников OSINT open source intelligence whois nslookup dig dnsenum dnsrecon fierce theHarvester maltego recon ng spiderfoot сканирование портов port scanning nmap masscan zmap unicornscan rustscan naabu сканирование уязвимостей vulnerability scanning определение версий служб service version detection баннер граббинг banner grabbing определение операционной системы OS fingerprinting ttl ip id sequence tcp window size обход межсетевых экранов firewall evasion фрагментация пакетов packet fragmentation decoy scan idle scan zombie scan ftp bounce scan атака на веб приложения web application testing OWASP top ten SQL инъекция sql injection XSS cross site scripting межсайтовый скриптинг CSRF cross site request forgery подделка межсайтовых запросов SSRF server side request forgery подделка запросов на стороне сервера XXE xml external entity injection инъекция внешних сущностей xml LFI local file inclusion включение локальных файлов RFI remote file inclusion включение удалённых файлов RCE remote code execution удалённое выполнение кода command injection инъекция команд directory traversal обход каталогов path traversal file upload уязвимость загрузки файлов broken authentication нарушение аутентификации broken access control нарушение контроля доступа IDOR insecure direct object references небезопасные прямые ссылки на объекты security misconfiguration небезопасная конфигурация sensitive data exposure раскрытие чувствительных данных insufficient logging monitoring недостаточное логирование и мониторинг использование компонентов с известными уязвимостями using components with known vulnerabilities внутреннее сканирование internal scanning внутренняя инфраструктура internal infrastructure анализ изнутри сети insider threat simulation сканирование от имени привилегированного пользователя privileged user scan сканирование без аутентификации unauthenticated scan анализ Active Directory Active Directory assessment enumeration of users groups computers domain trusts group policy enumeration анализ групповых политик GPO Group Policy Object анализ контроллеров домена domain controller assessment анализ серверов server assessment анализ рабочих станций workstation assessment анализ сетевого оборудования network device assessment анализ средств виртуализации virtualization assessment vmware esxi hyper v kvm proxmox xen анализ контейнеризации container security docker kubernetes openshift podman анализ баз данных database assessment анализ промышленных систем ICS SCADA assessment анализ беспроводных сетей wireless network assessment wi fi wpa wpa wpa wpa enterprise wep анализ удалённого доступа remote access assessment vpn ipsec ssl vpn ltp pptp openvpn wireguard анализ терминальных служб terminal services assessment rdp remote desktop protocol vnc citrix vmware horizon",
    k=130
)
    
    rag_elapsed = time.time() - rag_start
    print(f"[INFO] Контекст из RAG API получен за {rag_elapsed:.2f} сек")
    
    # Вывод информации об источниках
    all_sources = []
    for i, sources in enumerate([rag_sources_1, rag_sources_4], 1):
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
        
    # Глава 2
    ch4, val4 = generate_chapter(4, chapter4_prompt, {
        "scan_data": scan_text,
        "rag_context": rag_ctx_4
    }, expected_sources=rag_sources_4)
    chapters["chapter4"] = ch4
    chapters["_validation_chapter4"] = val4
    
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
    for i in range(1, 3):
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