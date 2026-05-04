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

# Пути к данным
RESULTS_DIR = "model_results"
COMPANY_DOCS_PATH = "./company_docs"
SCANS_PATH = ".\\local-rag-mcp\\src\\docs"
RAG_SERVER_URL = "http://localhost:8080"
CHUNKS_PATH = Path("local-rag-mcp/src/data/chunks_with_metadata.pkl")

# Создание папки для результатов
os.makedirs(RESULTS_DIR, exist_ok=True)

# Проверка использованных источников
def validate_sources_in_chapter(chapter_text: str, expected_sources: List[Dict]) -> Dict:
        
    # Ищем все пометки
    source_markers = re.findall(r'\[Источник:\s*([^\]]+)\]', chapter_text)
    
    # Собираем имена файлов из источников
    expected_filenames = set()
    for src in expected_sources:
        filename = src.get('filename', '')
        if filename:
            expected_filenames.add(filename)
    
    # Проверяем, какие источники использованы
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


# Работа с РАГ и его описаниями

class RAGClient:
    
    def __init__(self, server_url: str = RAG_SERVER_URL):
        self.server_url = server_url.rstrip('/')
        self.available = self._check_connection()
        self.local_chunks = self._load_local_chunks()
        
        if self.available:
            print(f" Подключение к РАГ серверу есть.")
        else:
            print(f" РАГ сервер недоступен.")
            if self.local_chunks:
                print(" Используются местные части.")
            else:
                print(" Для работы РАГ нужно запустить сервер")
    
    # Проверка связи с РАГ
    def _check_connection(self) -> bool:
        try:
            response = requests.get(f"{self.server_url}", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    # Загрузка местных частей как запасной источник
    def _load_local_chunks(self):
        if CHUNKS_PATH.exists():
            try:
                with open(CHUNKS_PATH, "rb") as f:
                    chunks = pickle.load(f)
                print(f"Загружено местных частей: {len(chunks)}")
                if chunks:
                    sample = chunks[0].get('metadata', {})
                    print(f"Пример описания: {sample.get('filename', 'Н/Д')}")
                return chunks
            except Exception as e:
                print(f"Ошибка загрузки местных частей: {e}")
        return None
    
    # Поиск по местным частям (по словам)
    def _search_local(self, query: str, k: int = 5) -> List[Dict]:
        if not self.local_chunks:
            return []
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        scored = []
        for chunk in self.local_chunks:
            text = chunk.get('text', '').lower()
            metadata = chunk.get('metadata', {})
            
            # Оценка: сколько слов совпало в тексте
            score = sum(1 for word in query_words if word in text)
            
            # Плюс за совпадение в имени файла
            filename = metadata.get('filename', '').lower()
            score += sum(3 for word in query_words if word in filename)
            
            # Плюс за совпадение в пути
            source = chunk.get('source', '').lower()
            score += sum(2 for word in query_words if word in source)
            
            if score > 0:
                scored.append((score, chunk))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        return [chunk for _, chunk in scored[:k]]
    
    # Приведение ответов от сервера к одному виду
    def _parse_http_results(self, results: List[Dict]) -> List[Dict]:
        parsed = []
        for r in results:
            parsed.append({
                "text": r.get('text', r.get('content', '')),
                "source": r.get('source', r.get('file', 'unknown')),
                "metadata": r.get('metadata', {}),
                "score": r.get('score', r.get('relevance', 0))
            })
        return parsed
    
    # Получение подходящего текста из РАГ с описанием
    def get_context_with_metadata(self, query: str, k: int = 15) -> Tuple[str, List[Dict]]:
        results = []
        
        # Пробуем получить данные через сеть
        if self.available:
            try:
                response = requests.get(
                    f"{self.server_url}/query",
                    params={"q": query, "k": k},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Разные виды ответов
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
                print(f"Ошибка сетевого запроса: {e}")
        
        # Если сеть не дала результатов, используем местные части
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
            
            # Простая пометка источника
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
    
    # Получение подходящего текста из РАГ (только текст)
    def get_context(self, query: str, k: int = 3) -> str:
        context, _ = self.get_context_with_metadata(query, k)
        return context


# Запуск языковой модели

print("Запуск языковой модели...")
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
    num_predict=25000,
    top_k=130,
    top_p=0.9,
)

init_time = time.time() - start_time
print(f"Языковая модель готова за {init_time:.2f} сек")


# Чтение документов компании

class CompanyDocumentReader:
    
    SUPPORTED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.csv', '.json', '.md'}
    
    def __init__(self, docs_path: str):
        self.docs_path = docs_path
    
    # Чтение всех документов с ограничениями
    def read_all_documents(self, max_docs: int = 50, max_size: int = 3000) -> List[Dict]:
        print(f"\nЧтение документов из: {self.docs_path}")
        
        if not os.path.exists(self.docs_path):
            print(f"Папка не найдена: {self.docs_path}")
            return []
        
        # Сбор файлов
        all_files = []
        for ext in self.SUPPORTED_EXTENSIONS:
            all_files.extend(glob.glob(os.path.join(self.docs_path, f"*{ext}")))
        
        print(f"Найдено файлов: {len(all_files)}")
        
        # Чтение файлов
        documents = []
        for i, file_path in enumerate(all_files):
            if i >= max_docs:
                print(f"Достигнут предел документов ({max_docs})")
                break
                            
            print(f"  Чтение: {os.path.basename(file_path)}")
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
        
        print(f"Загружено документов: {len(documents)}")
        return documents
    
    # Чтение файла нужным способом
    def _read_file(self, file_path: str) -> str:
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
            print(f"Ошибка чтения {file_path}: {e}")
            return ""
        
        return ""


# Заготовки запросов

def create_chain(prompt):
    return prompt | llm | StrOutputParser()


# Глава 1: Основание работ
chapter1_prompt = PromptTemplate(
    input_variables=["company_context", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 1 отчета по проверке защищенности системы.

Используй эти данные:

Бумаги компании:
{company_context}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".
НЕ ВЫДУМЫВАЙ номера договоров, даты, названия!

Составь раздел:

1. СВЕДЕНИЯ ОБ ОСНОВАНИИ, ЗАКАЗЧИКЕ И ЦЕЛЯХ РАБОТЫ

В разделе нужно указать:
- Основание для работ (номер и дату договора, задания, приказа)
- Полное название заказчика
- Полное название исполнителя
- Сроки работ (даты начала и конца)
- Цели проверки защищенности
- Задачи, которые нужно решить

Пиши деловым языком.
"""
)


# Глава 2: Используемые средства
chapter2_prompt = PromptTemplate(
    input_variables=["company_context", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 2 отчета по проверке защищенности системы.

Используй эти данные:

Бумаги компании:
{company_context}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".
НЕ ВЫДУМЫВАЙ названия средств, версии, номера!

Составь раздел:

2. СВЕДЕНИЯ ОБ ИСПОЛЬЗУЕМЫХ СРЕДСТВАХ ПРОВЕРКИ

В разделе нужно указать:
- Проверенные средства поиска уязвимостей (название, версия, номер свидетельства)
- Другие средства, которые применялись (с пояснением зачем)
- Дата последнего обновления баз уязвимостей
- Свои программы (если есть)

Поясни выбор каждого средства.
"""
)


# Глава 3: Описи системы
chapter3_prompt = PromptTemplate(
    input_variables=["scan_data", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 3 отчета по проверке защищенности системы.

Используй эти данные сканирования:
{scan_data}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

3. ИТОГИ ОПИСИ СИСТЕМЫ

В разделе нужно показать:
- Список IP-адресов и доменных имен
- Таблицу открытых портов и служб (IP-адрес, порт, протокол, служба)
- Список сетевых служб (DNS, DHCP, Web-серверы и другие)
- Список операционных систем и версий программ
- Найденные неиспользуемые адреса

Покажи сведения в виде таблиц.
"""
)


# Глава 4: Внешнее сканирование
chapter4_prompt = PromptTemplate(
    input_variables=["scan_data", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 4 отчета по проверке защищенности системы.

Используй эти данные сканирования:
{scan_data}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

4. ИТОГИ ВНЕШНЕГО СКАНИРОВАНИЯ

В разделе нужно описать:
- Способ внешней проверки (как будто действует внешний нарушитель)
- Найденные уязвимости на границе сети с указанием:
  * Номера CVE (если есть)
  * IP-адреса и порты
  * Описание уязвимости
  * Затронутая программа
- Итоги проверки настроек сетевых служб
- Итоги проверки способов входа

Для каждой уязвимости укажи как её нашли.
"""
)


# Глава 5: Внутреннее сканирование
chapter5_prompt = PromptTemplate(
    input_variables=["scan_data", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 5 отчета по проверке защищенности системы.

Используй эти данные сканирования:
{scan_data}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

5. ИТОГИ ВНУТРЕННЕГО СКАНИРОВАНИЯ

В разделе нужно описать:
- Способ внутренней проверки (как будто действует свой нарушитель)
- Уязвимости серверов и рабочих мест
- Уязвимости доменной службы (Active Directory)
- Итоги проверки настроек ОС
- Проверка прав пользователей
- Уязвимости баз данных и прикладных программ
- Уязвимости систем виртуализации

Для каждой уязвимости укажи:
  Имя хоста или IP-адрес
  Вид уязвимости
  Описание
  Как нашли
"""
)


# Глава 6: Список уязвимостей
chapter6_prompt = PromptTemplate(
    input_variables=["vulnerabilities_data", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 6 отчета по проверке защищенности системы.

Используй эти данные об уязвимостях:
{vulnerabilities_data}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

6. СПИСОК И ОПИСАНИЕ НАЙДЕННЫХ УЯЗВИМОСТЕЙ

В разделе нужно дать полный список найденных уязвимостей в виде таблицы.
Для каждой уязвимости укажи:

| № | Номер | Хост | Порт | Название уязвимости | Описание | Как нашли |
|---|------|------|------|---------------------|----------|-----------|
| 1 | CVE-XXXX-XXXX | 10.0.0.1 | 443 | ... | ... | ... |

Опиши не менее 10-15 самых важных уязвимостей.
"""
)


# Глава 7: Уровень опасности
chapter7_prompt = PromptTemplate(
    input_variables=["vulnerabilities_list", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 7 отчета по проверке защищенности системы.

Используй этот список уязвимостей:
{vulnerabilities_list}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

7. ОЦЕНКА ОПАСНОСТИ НАЙДЕННЫХ УЯЗВИМОСТЕЙ

В разделе нужно:
- Применить способ оценки опасности (CVSS v3.1)
- Оценить каждую уязвимость по шкале CVSS
- Разложить уязвимости по уровням опасности
- Найти уязвимости, требующие срочного исправления

Покажи итоги оценки в виде таблицы:

| Уязвимость | Хост | Вектор CVSS | Оценка | Уровень опасности | Требуется исправление |
|------------|------|-------------|--------|-------------------|---------------------|
| ... | ... | ... | ... | Критичный/Высокий/Средний/Низкий | Да/Нет |

Распределение:
- Критических уязвимостей: X
- Высокого уровня: Y
- Среднего уровня: Z
- Низкого уровня: W

Поясни каждую оценку.
"""
)


# Глава 8: Самые опасные уязвимости
chapter8_prompt = PromptTemplate(
    input_variables=["all_data", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 8 отчета по проверке защищенности системы.

Используй эти данные:
{all_data}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

8. СПИСОК САМЫХ ОПАСНЫХ УЯЗВИМОСТЕЙ (С ПОЯСНЕНИЕМ)

В разделе нужно:
- Выбрать 5-10 самых опасных уязвимостей (признаки: оценка CVSS, доступность снаружи, важность узла)
- Для каждой уязвимости указать:
  1. Номер и название
  2. Где находится (хост, порт)
  3. Описание уязвимости
  4. Как могут атаковать (сценарий)
  5. Что случится (последствия)
  6. Почему выбрали (обоснование)

Обоснование должно учитывать работу компании и возможный вред.
"""
)


# Глава 9: Советы по исправлению
chapter9_prompt = PromptTemplate(
    input_variables=["risks_data", "rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 9 отчета по проверке защищенности системы.

Используй эти данные об угрозах:
{risks_data}

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

9. СОВЕТЫ ПО ИСПРАВЛЕНИЮ НАЙДЕННЫХ УЯЗВИМОСТЕЙ

В разделе нужно:
- Дать советы для каждой критической уязвимости
- Дать советы для уязвимостей высокого уровня
- Дать советы по изменению настроек
- Предложить улучшения построения системы
- Определить срочность и сроки исправления
- Добавить ссылки на исправления и обновления

Советы должны быть:
- Точными (что именно сделать)
- Выполнимыми (с учетом возможностей)
- По порядку важности (с чего начать)

Примеры: "Обновить Apache до версии 2.4.52", "Отключить SMBv1", "Ввести двухэтапный вход"
"""
)


# Глава 10: Ограничения
chapter10_prompt = PromptTemplate(
    input_variables=["rag_context"],
    template="""Ты специалист по защите информации. Составь ГЛАВУ 10 отчета по проверке защищенности системы.

Сведения из базы знаний:
{rag_context}

СТРОГОЕ ПРАВИЛО ССЫЛОК:
После КАЖДОГО утверждения, взятого из текста, ОБЯЗАТЕЛЬНО ставь пометку [Источник: имя_файла] точно так, как она указана в данных.
НЕ придумывай свои пометки - бери их из текста выше!

Если в данных нет сведений - пиши "Сведения отсутствуют".

Составь раздел:

10. ОГРАНИЧЕНИЯ НА ДЕЙСТВИЯ ИСПОЛНИТЕЛЯ

Укажи:
- Запреты на некоторые виды работ (например, DoS-атаки)
- Что не проверялось (какие части сети)
- Нет доступа к некоторым данным (если не дали)
- Непредоставленные сведения или бумаги
- Временные рамки (если работы велись не всё время)

Этот раздел важен для понимания полноты проверки.
"""
)


# Создание глав

def generate_chapter(chapter_number: int, prompt_template: PromptTemplate, data: Dict, 
                     expected_sources: List[Dict] = None) -> Tuple[str, Dict]:
    print(f"Создание главы {chapter_number}...")
    start_time = time.time()
    
    chain = create_chain(prompt_template)
    result = chain.invoke(data)
    
    # Подтверждение источников
    validation = None
    if expected_sources is not None:
        validation = validate_sources_in_chapter(result, expected_sources)
        if validation["validation_passed"]:
            print(f"Глава {chapter_number}: найдено пометок: {validation['markers_count']}")
            if validation['missing_sources']:
                print(f"Глава {chapter_number}: не использованы источники: {validation['missing_sources'][:5]}")
        else:
            print(f"Глава {chapter_number}: пометки источников не найдены!")
    
    elapsed = time.time() - start_time
    print(f"Глава {chapter_number} создана за {elapsed:.2f} сек")
    
    return result, validation


def generate_all_chapters(scan_files: List[str], company_docs: List[Dict], rag: RAGClient) -> Dict:
    
    print("\n" + "-" * 50)
    print("СОЗДАНИЕ ГЛАВ ОТЧЕТА ПО ПРОВЕРКЕ ЗАЩИЩЕННОСТИ")
    print("-" * 50)
    
    total_start = time.time()
    
    # Готовим данные из бумаг компании
    docs_text = "\n\n---\n\n".join([
        f"Файл: {doc['file']}\n{doc['content']}" 
        for doc in company_docs[:1]
    ])
    
    # Читаем данные сканирования
    scan_data_parts = []
    for file_path in scan_files[:10]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if len(content) > 5000:
                    content = content[:5000] + "...[текст обрезан]"
                scan_data_parts.append(f"Файл: {os.path.basename(file_path)}\n{content}")
        except Exception as e:
            print(f"Ошибка чтения {file_path}: {e}")
    
    scan_text = "\n\n---\n\n".join(scan_data_parts)
    
    # Получаем сведения из РАГ
    print("\nПолучение сведений из РАГ...")
    rag_start = time.time()
    
    # Запросы к РАГ для всех глав
    rag_ctx_1, rag_sources_1 = rag.get_context_with_metadata(
         "Договор № г «» г именуемое в дальнейшем Заказчик в лице действующего на основании с одной стороны и именуемое в дальнейшем Исполнитель в лице действующего на основании с другой стороны заключили настоящий договор о нижеследующем Предмет договора Заказчик поручает а Исполнитель принимает на себя обязательство оказать услуги по Права и обязанности сторон Исполнитель обязуется Оказать услуги с надлежащим качеством и в соответствии с требованиями нормативных документов Заказчик обязуется Предоставить Исполнителю доступ Произвести оплату за оказанные услуги в срок Цена и порядок расчетов За выполненные работы оказанные услуги Заказчик выплачивает Исполнителю рублей в том числе НДС Оплата производится путем перечисления денежных средств на расчетный счет Исполнителя в течение банковских дней с даты подписания акта выполненных работ Ответственность сторон В случае неисполнения или ненадлежащего исполнения Договора Стороны несут ответственность в соответствии с действующим законодательством Российской Федерации Срок действия договора Настоящий договор вступает в силу с момента подписания и действует до полного исполнения обязательств Сторонами Конфиденциальность Стороны обязуются сохранять конфиденциальность информации Юридические адреса и реквизиты сторон УТВЕРЖДАЮ ТЕХНИЧЕСКОЕ ЗАДАНИЕ на оказание услуг по проведению аудита информационной безопасности Общие сведения Наименование работы Заказчик Исполнитель Срок выполнения работ Начало с даты подписания договора Окончание не позднее г Цели и задачи работы Целью работы является оценка текущего уровня защищенности и разработка рекомендаций по повышению защищенности Для достижения поставленной цели должны быть решены следующие задачи Границы проведения работ Объекты проведения работ Требования к выполнению работ Работы должны выполняться в соответствии с требованиями следующих нормативных документов Приказ ФСТЭК России от № Методика оценки угроз безопасности информации утв ФСТЭК России Политика информационной безопасности Заказчика Состав и содержание работ Этап Сбор и анализ исходных данных Этап Инструментальный аудит Этап Анализ уязвимостей и оценка рисков Этап Разработка рекомендаций и отчетной документации Требования к отчетной документации По результатам работ Исполнитель представляет Заказчику Отчет содержащий результаты проведенного аудита Требования к Исполнителю Исполнитель должен иметь действующую лицензию ФСТЭК России на деятельность по технической защите конфиденциальной информации Приложения Календарный план выполнения работ"
        , k=120
    )
    rag_ctx_2, rag_sources_2 = rag.get_context_with_metadata(
        "средства выявления уязвимостей инструментальные средства сканер безопасности network scanner vulnerability scanner nmap nessus openvas xspider maxpatrol анализатор кода source code analyzer static analysis dynamic analysis база уязвимостей vulnerability database CVE common vulnerabilities and exposures CVSS common vulnerability scoring system банк данных угроз безопасности информации БДУ ФСТЭК bdu fstec ru программное обеспечение для анализа защищённости security assessment tool penetration testing tool ethical hacking framework metasploit burp suite wireshark tcpdump snort suricata система обнаружения вторжений IDS intrusion detection system система предотвращения вторжений IPS intrusion prevention system межсетевой экран firewall средство анализа конфигураций configuration assessment tool compliance scanner средство контроля целостности integrity checker средство анализа защищённости веб приложений web application security scanner waf web application firewall средство анализа защищённости баз данных database security scanner средство анализа защищённости беспроводных сетей wireless security scanner aircrack ng kismet средство анализа защищённости облачной инфраструктуры cloud security scanner средство анализа защищённости контейнеров container security scanner docker security kubernetes security средство анализа защищённости исходного кода SAST DAST IAST RASP средство анализа защищённости мобильных приложений mobile application security testing MAST средство анализа защищённости промышленных систем ICS SCADA security scanner промышленный протокол modbus dnp3 opc ua profinet ethernet ip средство анализа защищённости Active Directory ad security assessment tool bloodhound mimikatz responder ntlm relay"
        , k=120
    )
    rag_ctx_3, rag_sources_3 = rag.get_context_with_metadata(
            "network scan nmap nmap_summary scan_results"
            " open_ports port state service version raw_output metadata source tool scan_type full_port_scan full_network_scan IP address IPv4 subnet network_range scan_time timestamp"
            " cvss: 3.7 full_cve ghsa_id: cve_id: url: html_url: network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version summary network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version  port:  state: service: version summary port:  state: service: version summary"
            " инвентаризация Перечень оборудования Инвентаризационная опись Наименование Тип Марка Модель Серийный номер Инвентарный номер Количество Местонахождение Сервер Автоматизированное рабочее место АРМ workstation Коммутатор switch Маршрутизатор router Источник бесперебойного питания ИБП UPS uninterruptible power supply Межсетевой экран firewall Система хранения данных СХД storage area network network attached storage Принтер scanner многофункциональное устройство МФУ IP адрес ip address IPv4 IPv6 маска подсети subnet mask шлюз по умолчанию default gateway MAC адрес mac address физический адрес порт port tcp udp сетевая служба network service сервис протокол"
            " protocol http https ftp sftp ssh telnet rdp smb cifs nfs ldap ldaps kerberos dns dhcp snmp smtp pop3 imap ntp syslog netbios wins"
            " Перечень программного обеспечения Наименование Версия Модель Производитель Разработчик Vendor Microsoft Windows Windows Server Windows XP Windows Vista Windows Seven Windows Eight Windows Ten Windows Eleven Windows Professional Windows Enterprise Windows Standard Windows Datacenter Windows Core Windows Nano Microsoft Office Office Standard Office Professional Plus Office Home and Business Office Enterprise Microsoft Visio Microsoft Project Microsoft Access Microsoft Outlook Microsoft Word Microsoft Excel Microsoft PowerPoint Microsoft OneNote Антивирус Касперского Kaspersky Endpoint Security Kaspersky Anti Targeted Attack Kaspersky Security Center Dr Web ESET NOD Symantec Endpoint Protection"
            " C Бухгалтерия C Управление торговлей C Управление персоналом C Документооборот C Комплексная автоматизация C Управление холдингом C ERP C CRM Adobe Acrobat Reader Adobe Acrobat Pro Adobe Creative Cloud Adobe Photoshop Adobe Illustrator Adobe InDesign Adobe Premiere Pro Adobe After Effects WinRAR WinZip Zip архиватор P Zip архиватор ZIP RAR Архиватор Браузер Google Chrome Mozilla Firefox Microsoft Edge Opera Safari Яндекс Браузер Atom Яндекс Браузер Почтовый клиент Microsoft Outlook Mozilla Thunderbird The Bat Почта Windows Mail Java Runtime Environment JRE Java Development Kit JDK Microsoft NET Framework Visual C Redistributable Python Ruby Perl PHP Perl Interpreter Node js JavaScript Runtime Система управления базами данных СУБД DBMS Microsoft SQL Server MySQL PostgreSQL Oracle Database MariaDB MongoDB Cassandra Redis SQLite IBM DB Apache Derby H Database Firebird Interbase"
            " ЛИРА САПР ЛИРА софт ПК ЛИРА ПК Мономах SCAD Office nanoCAD AutoCAD ArchiCAD Revit Tekla Structures Bentley MicroStation SolidWorks КОМПАС D Solid Edge CATIA NX Unigraphics PTC Creo ProENGINEER Ansys Abaqus Nastran Patran HyperWorks LS DYNA Moldflow Simufact Deform QForm SprutCAM PowerMILL Mastercam ArtCAM FeatureCAM Edgecam GibbsCAM Cimatron Tebis WorkNC HyperMILL Vericut CNC Simulator Matlab Simulink Mathcad Mathematica Maple Statistica SPSS Stata EViews Gretl LabVIEW LabWindows CVI TestStand DIAdem Measurement Studio"
        , k=130
    )
    rag_ctx_4, rag_sources_4 = rag.get_context_with_metadata(
        "network scan nmap nmap_summary scan_results"
        " open_ports port state service version raw_output metadata source tool scan_type full_port_scan full_network_scan IP address IPv4 subnet network_range scan_time timestamp"
        " cvss: 3.7 full_cve ghsa_id: cve_id: url: html_url: network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version summary network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version  port:  state: service: version summary port:  state: service: version summary"
        "внешнее сканирование external scanning внешний периметр external perimeter анализ из сети Интернет Internet facing assessment тестирование на проникновение penetration testing pen test black box white box grey box разведка reconnaissance footprinting сбор информации из открытых источников OSINT open source intelligence whois nslookup dig dnsenum dnsrecon fierce theHarvester maltego recon ng spiderfoot сканирование портов port scanning nmap masscan zmap unicornscan rustscan naabu сканирование уязвимостей vulnerability scanning определение версий служб service version detection баннер граббинг banner grabbing определение операционной системы OS fingerprinting ttl ip id sequence tcp window size обход межсетевых экранов firewall evasion фрагментация пакетов packet fragmentation decoy scan idle scan zombie scan ftp bounce scan атака на веб приложения web application testing OWASP top ten SQL инъекция sql injection XSS cross site scripting межсайтовый скриптинг CSRF cross site request forgery подделка межсайтовых запросов SSRF server side request forgery подделка запросов на стороне сервера XXE xml external entity injection инъекция внешних сущностей xml LFI local file inclusion включение локальных файлов RFI remote file inclusion включение удалённых файлов RCE remote code execution удалённое выполнение кода command injection инъекция команд directory traversal обход каталогов path traversal file upload уязвимость загрузки файлов broken authentication нарушение аутентификации broken access control нарушение контроля доступа IDOR insecure direct object references небезопасные прямые ссылки на объекты security misconfiguration небезопасная конфигурация sensitive data exposure раскрытие чувствительных данных insufficient logging monitoring недостаточное логирование и мониторинг использование компонентов с известными уязвимостями using components with known vulnerabilities внутреннее сканирование internal scanning внутренняя инфраструктура internal infrastructure анализ изнутри сети insider threat simulation сканирование от имени привилегированного пользователя privileged user scan сканирование без аутентификации unauthenticated scan анализ Active Directory Active Directory assessment enumeration of users groups computers domain trusts group policy enumeration анализ групповых политик GPO Group Policy Object анализ контроллеров домена domain controller assessment анализ серверов server assessment анализ рабочих станций workstation assessment анализ сетевого оборудования network device assessment анализ средств виртуализации virtualization assessment vmware esxi hyper v kvm proxmox xen анализ контейнеризации container security docker kubernetes openshift podman анализ баз данных database assessment анализ промышленных систем ICS SCADA assessment анализ беспроводных сетей wireless network assessment wi fi wpa wpa wpa wpa enterprise wep анализ удалённого доступа remote access assessment vpn ipsec ssl vpn ltp pptp openvpn wireguard анализ терминальных служб terminal services assessment rdp remote desktop protocol vnc citrix vmware horizon"
    , k=130
    )
    rag_ctx_5, rag_sources_5 = rag.get_context_with_metadata(
         "Отчет по результатам анализа уязвимостей Vulnerability Assessment Report Перечень выявленных уязвимостей List of Identified Vulnerabilities В ходе анализа были выявлены следующие уязвимости The following vulnerabilities were identified during the assessment Наименование уязвимости Vulnerability Name Уровень критичности Severity Level Высокий High Средний Medium Низкий Low Критический Critical Описание уязвимости Vulnerability Description Рекомендации по устранению Remediation Recommendations Оценка критичности уязвимостей Vulnerability Criticality Assessment Выводы и рекомендации Conclusions and Recommendations CVE Common Vulnerabilities and Exposures идентификатор уязвимости CVE BDU Банк данных угроз безопасности информации ФСТЭК России идентификатор БДУ CVSS Common Vulnerability Scoring System базовая оценка Base Score временная оценка Temporal Score контекстная оценка Environmental Score вектор атаки Attack Vector AV Network Adjacent Local Physical сложность атаки Attack Complexity AC Low High требуемые привилегии Privileges Required PR None Low High взаимодействие с пользователем User Interaction UI None Required влияние на конфиденциальность Confidentiality Impact C None Low High влияние на целостность Integrity Impact I None Low High влияние на доступность Availability Impact A None Low High уязвимость нулевого дня zero day vulnerability уязвимость удалённого выполнения кода remote code execution RCE уязвимость повышения привилегий privilege escalation local privilege escalation LPE уязвимость отказа в обслуживании denial of service DoS distributed denial of service DDoS уязвимость обхода аутентификации authentication bypass уязвимость раскрытия информации information disclosure memory leak уязвимость межсайтового скриптинга cross site scripting XSS reflected XSS stored XSS DOM based XSS blind XSS уязвимость подделки межсайтовых запросов cross site request forgery CSRF уязвимость подделки запросов на стороне сервера server side request forgery SSRF blind SSRF уязвимость инъекции SQL injection error based blind boolean based time based out of band stacked queries second order уязвимость инъекции команд command injection OS command injection уязвимость включения файлов file inclusion local file inclusion LFI remote file inclusion RFI уязвимость обхода каталогов directory traversal path traversal уязвимость загрузки произвольных файлов arbitrary file upload уязвимость небезопасной десериализации insecure deserialization уязвимость использования компонентов с известными уязвимостями using components with known vulnerabilities уязвимость недостаточного логирования и мониторинга insufficient logging and monitoring уязвимость небезопасной конфигурации security misconfiguration default credentials weak passwords default snmp community strings public private"
        , k=130
    )
    rag_ctx_6, rag_sources_6 = rag.get_context_with_metadata(
        "id: CVE"
        "Published:"
        "summary:"
        "cvss: 3.7"
        "full_cve"
        "ghsa_id:"
        "cve_id:"
        "url:"
        "html_url:"
        "summary "
        "network scan nmap nmap_summary scan_results"
        " open_ports port state service version raw_output metadata source tool scan_type full_port_scan full_network_scan IP address IPv4 subnet network_range scan_time timestamp"
        " cvss: 3.7 full_cve ghsa_id: cve_id: url: html_url: network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version summary network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version  port:  state: service: version summary port:  state: service: version summary"
         "Отчет по результатам анализа уязвимостей Vulnerability Assessment Report Перечень выявленных уязвимостей List of Identified Vulnerabilities В ходе анализа были выявлены следующие уязвимости The following vulnerabilities were identified during the assessment Наименование уязвимости Vulnerability Name Уровень критичности Severity Level Высокий High Средний Medium Низкий Low Критический Critical Описание уязвимости Vulnerability Description Рекомендации по устранению Remediation Recommendations Оценка критичности уязвимостей Vulnerability Criticality Assessment Выводы и рекомендации Conclusions and Recommendations CVE Common Vulnerabilities and Exposures идентификатор уязвимости CVE BDU Банк данных угроз безопасности информации ФСТЭК России идентификатор БДУ CVSS Common Vulnerability Scoring System базовая оценка Base Score временная оценка Temporal Score контекстная оценка Environmental Score вектор атаки Attack Vector AV Network Adjacent Local Physical сложность атаки Attack Complexity AC Low High требуемые привилегии Privileges Required PR None Low High взаимодействие с пользователем User Interaction UI None Required влияние на конфиденциальность Confidentiality Impact C None Low High влияние на целостность Integrity Impact I None Low High влияние на доступность Availability Impact A None Low High уязвимость нулевого дня zero day vulnerability уязвимость удалённого выполнения кода remote code execution RCE уязвимость повышения привилегий privilege escalation local privilege escalation LPE уязвимость отказа в обслуживании denial of service DoS distributed denial of service DDoS уязвимость обхода аутентификации authentication bypass уязвимость раскрытия информации information disclosure memory leak уязвимость межсайтового скриптинга cross site scripting XSS reflected XSS stored XSS DOM based XSS blind XSS уязвимость подделки межсайтовых запросов cross site request forgery CSRF уязвимость подделки запросов на стороне сервера server side request forgery SSRF blind SSRF уязвимость инъекции SQL injection error based blind boolean based time based out of band stacked queries second order уязвимость инъекции команд command injection OS command injection уязвимость включения файлов file inclusion local file inclusion LFI remote file inclusion RFI уязвимость обхода каталогов directory traversal path traversal уязвимость загрузки произвольных файлов arbitrary file upload уязвимость небезопасной десериализации insecure deserialization уязвимость использования компонентов с известными уязвимостями using components with known vulnerabilities уязвимость недостаточного логирования и мониторинга insufficient logging and monitoring уязвимость небезопасной конфигурации security misconfiguration default credentials weak passwords default snmp community strings public private"
        , k=130
    )
    rag_ctx_7, rag_sources_7 = rag.get_context_with_metadata(
        "id: CVE"
        "Published:"
        "summary:"
        "cvss: 3.7"
        "full_cve"
        "ghsa_id:"
        "cve_id:"
        "url:"
        "html_url:"
        "summary "
        "network scan nmap nmap_summary scan_results"
        " open_ports port state service version raw_output metadata source tool scan_type full_port_scan full_network_scan IP address IPv4 subnet network_range scan_time timestamp"
        " cvss: 3.7 full_cve ghsa_id: cve_id: url: html_url: network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version summary network: scan_time: total_hosts: results:  ip: timestamp: open_ports: port:  state: service: version  port:  state: service: version summary port:  state: service: version summary"
        "перечень выявленных уязвимостей информационной системы подлежащих устранению в ходе анализа уязвимостей обоснование необходимости устранения уязвимостей для предотвращения реализации угроз безопасности информации векторов атак приводящих к возникновению негативных последствий угроза безопасности информации threat information security threat vector attack vector негативные последствия adverse consequences ущерб damage финансовые потери financial loss репутационные риски reputational risk юридические последствия legal consequences нарушение конфиденциальности confidentiality breach нарушение целостности integrity violation нарушение доступности availability disruption нарушение непрерывности бизнес процессов business continuity disruption выход из строя оборудования equipment failure загрязнение окружающей среды environmental pollution человеческие жертвы human casualties авария accident инцидент incident катастрофа disaster сценарий реализации угрозы threat realization scenario модель нарушителя threat actor model внешний нарушитель external threat actor internal threat actor внутренний нарушитель insider threat привилегированный пользователь privileged user администратор administrator хакер hacker киберпреступник cybercriminal хактивист hacktivist террористическая группа terrorist group спецслужба intelligence agency nation state actor конкурент competitor обиженный сотрудник disgruntled employee неосторожный пользователь careless user мотивация motivation финансовая выгода financial gain шпионаж espionage sabotage саботаж месть revenge любопытство curiosity самоутверждение ego возможности нарушителя threat actor capabilities низкий потенциал low potential средний потенциал medium potential высокий потенциал high potential оснащённость resources доступ к специализированному ПО access to specialized software доступ к уязвимостям нулевого дня access to zero day exploits навыки skills знания knowledge опыт experience вектор атаки attack vector сетевой network локальный local физический physical смежный adjacent целевая система target system компонент component сервер server рабочая станция workstation сетевое оборудование network device средство защиты security control база данных database веб приложение web application мобильное приложение mobile application облачная инфраструктура cloud infrastructure контейнер container промышленная система ICS SCADA PLC RTU IED HMI MES ERP критически важный объект critical infrastructure object потенциально опасный объект hazardous facility объект повышенной опасности high risk facility АСУ ТП automated process control system industrial control system АСУ ТП КВО КИИ значимый объект критической информационной инфраструктуры субъект КИИ"
        , k=130
    )
    rag_ctx_8, rag_sources_8 = rag.get_context_with_metadata(
          "рекомендации исполнителя по устранению выявленных уязвимостей информационной системы рекомендации по устранению уязвимостей remediation recommendations mitigation measures обновление программного обеспечения software update установка обновлений безопасности security update installation установка патча patch installation critical patch security patch hotfix rollup service pack накопительное обновление cumulative update ежемесячное обновление monthly rollup ежеквартальное обновление quarterly update внеплановое обновление out of band update изменение конфигурации configuration change hardening ужесточение системы system hardening отключение неиспользуемых служб disabling unused services закрытие портов port closure фильтрация трафика traffic filtering access control list ACL настройка межсетевого экрана firewall configuration настройка системы обнаружения вторжений IDS configuration настройка системы предотвращения вторжений IPS configuration настройка антивирусной защиты antivirus configuration обновление антивирусных баз antivirus signature update настройка парольной политики password policy configuration длина пароля password length сложность пароля password complexity история паролей password history срок действия пароля password age максимальный срок max age минимальный срок min age блокировка учётной записи account lockout порог блокировки lockout threshold длительность блокировки lockout duration сброс счётчика блокировки lockout reset многофакторная аутентификация multi factor authentication MFA two factor authentication FA двухфакторная аутентификация аппаратный токен hardware token программный токен software token sms token push notification biometrics биометрия отпечаток пальца fingerprint распознавание лица facial recognition голос voice recognition радужная оболочка глаза iris scan настройка аудита audit configuration логирование logging мониторинг monitoring SIEM security information and event management сбор событий event collection корреляция событий event correlation анализ инцидентов incident analysis реагирование на инциденты incident response план реагирования incident response plan группа реагирования incident response team CSIRT CERT ограничение прав доступа privilege restriction принцип минимальных привилегий least privilege principle разделение обязанностей separation of duties контроль доступа на основе ролей role based access control RBAC контроль доступа на основе атрибутов attribute based access control ABAC mandatory access control MAC дискреционный контроль доступа discretionary access control DAC изоляция среды sandboxing контейнеризация containerization виртуализация virtualization сегментация сети network segmentation микросегментация micro segmentation демилитаризованная зона DMZ виртуальная локальная сеть VLAN виртуальная частная сеть VPN шифрование encryption TLS SSL IPsec шифрование данных at rest шифрование данных in transit резервное копирование backup восстановление restore аварийное восстановление disaster recovery план обеспечения непрерывности business continuity plan обучение персонала security awareness training повышение осведомлённости security awareness program фишинг симуляции phishing simulation тестирование на проникновение penetration testing red team blue team purple team управление уязвимостями vulnerability management процесс управления уязвимостями vulnerability management process инвентаризация активов asset inventory сканирование уязвимостей vulnerability scanning оценка рисков risk assessment приоритизация уязвимостей vulnerability prioritization устранение уязвимостей vulnerability remediation verification верификация"
        , k=130
    )
    rag_ctx_9, rag_sources_9 = rag.get_context_with_metadata(
         "результаты повторного анализа уязвимостей информационной системы проводимого с целью подтверждения устранения заказчиком оператором выявленных уязвимостей информационной системы Акт № выполненных работ по устранению уязвимостей г «» г Мы нижеподписавшиеся составили настоящий акт о том что работы по устранению уязвимостей выявленных в ходе анализа выполнены в полном объеме Перечень устраненных уязвимостей Работы выполнены в соответствии с требованиями и в установленные сроки Подписи сторон Заказчик Исполнитель повторный анализ уязвимостей rescan повторное сканирование verification scan подтверждение устранения vulnerability closure verification верификация исправления fix verification закрытие уязвимости vulnerability closure устранённая уязвимость remediated vulnerability mitigated vulnerability ложное срабатывание false positive положительное заключение positive conclusion negative conclusion отрицательное заключение остаточный риск residual risk приемлемый риск acceptable risk неприемлемый риск unacceptable risk исключение exception принятие риска risk acceptance обоснование невозможности эксплуатации exploitation impossibility rationale компенсирующие меры compensating controls заключение о защищённости security posture statement statement of compliance аттестация соответствия security certification accreditation"
         , k=130
    )
    rag_ctx_10, rag_sources_10 = rag.get_context_with_metadata(
         "ограничения которые заказчик оператор накладывает на действия исполнителя в ходе анализа уязвимостей информационной системы ограничения restrictions запреты prohibitions исключения exclusions границы проведения работ scope boundaries scope of work exclusions исключённые объекты excluded assets объекты вне области аудита out of scope items непредставление доступа access denial отсутствие доступа lack of access невозможность подключения inability to connect запрет на активное сканирование active scanning prohibition запрет на тестирование на проникновение penetration testing restriction запрет на эксплуатацию уязвимостей exploitation prohibition запрет на изменение конфигурации configuration change prohibition окно проведения работ maintenance window время проведения работ testing timeframe период останова shutdown period перерыв в работе work interruption приостановка работ work suspension возобновление работ work resumption ограничение по времени time constraint ограничение по ресурсам resource constraint недоступность персонала personnel unavailability отсутствие документации lack of documentation непредоставление исходных данных initial data denial отсутствие учётных записей lack of test accounts использование тестовой среды test environment usage запрет на тестирование продуктивной среды production environment testing restriction ограничения межсетевого экрана firewall restrictions ограничения сетевого доступа network access restrictions изоляция сегмента сети network segment isolation отсутствие сетевой связности lack of network connectivity ограничения пропускной способности bandwidth limitations ограничения на сканирование уязвимостей vulnerability scanning limitations исключение типов уязвимостей vulnerability type exclusion отказ от проверки определённых систем exclusion of specific systems исключение устаревших систем legacy system exclusion исключение промышленных систем ICS exclusion исключение медицинского оборудования medical device exclusion исключение систем жизнеобеспечения life support system exclusion исключение критически важных систем mission critical system exclusion запрет на сканирование в рабочие часы business hours scanning prohibition ограничения на интенсивность сканирования scan intensity limitations ограничения на количество пакетов packet rate limiting задержка сканирования scan delay throttling безопасный режим сканирования safe scan mode безопасные проверки safe checks only отключение деструктивных проверок disruptive checks disabling исключение проверок на отказ в обслуживании DoS check exclusion соглашение о неразглашении non disclosure agreement NDA соглашение о конфиденциальности confidentiality agreement правила безопасного проведения работ rules of engagement RoE"
         , k=130
    )
    
    rag_elapsed = time.time() - rag_start
    print(f"Сведения из РАГ получены за {rag_elapsed:.2f} сек")
    
    # Показываем сведения об источниках
    all_sources = []
    sources_list = [rag_sources_1, rag_sources_2, rag_sources_3, rag_sources_4, rag_sources_5,
                    rag_sources_6, rag_sources_7, rag_sources_8, rag_sources_9, rag_sources_10]
    
    for i, sources in enumerate(sources_list, 1):
        if sources:
            print(f"Глава {i}: найдено источников в РАГ: {len(sources)}")
            for src in sources[:3]:
                print(f"       - {src['filename']} (часть {src['chunk_id']}/{src['chunk_total']}, совпадение: {src['score']:.3f})")
            all_sources.extend(sources)
        else:
            print(f"Глава {i}: источники в РАГ не найдены")
    
    if all_sources:
        unique_sources = set([s['filename'] for s in all_sources])
        print(f"Всего найдено разных источников: {len(unique_sources)}")
    
    # Создаем главы
    chapters = {}
    
    # Глава 1
    ch1, val1 = generate_chapter(1, chapter1_prompt, {
        "company_context": docs_text,
        "rag_context": rag_ctx_1
    }, expected_sources=rag_sources_1)
    chapters["chapter1"] = ch1
    chapters["_validation_chapter1"] = val1
    
    # Глава 2
    ch2, val2 = generate_chapter(2, chapter2_prompt, {
        "company_context": docs_text,
        "rag_context": rag_ctx_2
    }, expected_sources=rag_sources_2)
    chapters["chapter2"] = ch2
    chapters["_validation_chapter2"] = val2
    
    # Глава 3
    ch3, val3 = generate_chapter(3, chapter3_prompt, {
        "scan_data": scan_text,
        "rag_context": rag_ctx_3
    }, expected_sources=rag_sources_3)
    chapters["chapter3"] = ch3
    chapters["_validation_chapter3"] = val3
    
    # Глава 4
    ch4, val4 = generate_chapter(4, chapter4_prompt, {
        "scan_data": scan_text,
        "rag_context": rag_ctx_4
    }, expected_sources=rag_sources_4)
    chapters["chapter4"] = ch4
    chapters["_validation_chapter4"] = val4
    
    # Глава 5
    ch5, val5 = generate_chapter(5, chapter5_prompt, {
        "scan_data": scan_text,
        "rag_context": rag_ctx_5
    }, expected_sources=rag_sources_5)
    chapters["chapter5"] = ch5
    chapters["_validation_chapter5"] = val5
    
    # Глава 6
    vulnerabilities_data = f"{ch4}\n\n{ch5}"
    ch6, val6 = generate_chapter(6, chapter6_prompt, {
        "vulnerabilities_data": vulnerabilities_data,
        "rag_context": rag_ctx_6
    }, expected_sources=rag_sources_6)
    chapters["chapter6"] = ch6
    chapters["_validation_chapter6"] = val6
    
    # Глава 7
    ch7, val7 = generate_chapter(7, chapter7_prompt, {
        "vulnerabilities_list": ch6,
        "rag_context": rag_ctx_7
    }, expected_sources=rag_sources_7)
    chapters["chapter7"] = ch7
    chapters["_validation_chapter7"] = val7
    
    # Глава 8
    all_data = f"{ch6}\n\n{ch7}"
    ch8, val8 = generate_chapter(8, chapter8_prompt, {
        "all_data": all_data,
        "rag_context": rag_ctx_8
    }, expected_sources=rag_sources_8)
    chapters["chapter8"] = ch8
    chapters["_validation_chapter8"] = val8
    
    # Глава 9
    ch9, val9 = generate_chapter(9, chapter9_prompt, {
        "risks_data": ch8,
        "rag_context": rag_ctx_9
    }, expected_sources=rag_sources_9)
    chapters["chapter9"] = ch9
    chapters["_validation_chapter9"] = val9
    
    # Глава 10
    ch10, val10 = generate_chapter(10, chapter10_prompt, {
        "rag_context": rag_ctx_10
    }, expected_sources=rag_sources_10)
    chapters["chapter10"] = ch10
    chapters["_validation_chapter10"] = val10
    
    total_elapsed = time.time() - total_start
    print(f"\nВсе главы созданы. Общее время: {total_elapsed:.2f} сек ({total_elapsed/60:.2f} мин)")
    
    chapters["_rag_sources"] = all_sources
    
    return chapters


# Сохранение итогов

def save_chapters(chapters: Dict, scan_files: List[str]) -> Dict:
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\nСохранение итогов в: {RESULTS_DIR}")
    
    saved_files = {}
    
    # Сохраняем главы 1-10
    for i in range(1, 11):
        chapter_key = f"chapter{i}"
        if chapter_key in chapters:
            chapter_file = os.path.join(RESULTS_DIR, f"chapter_{i:02d}_{timestamp}.txt")
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(chapters[chapter_key])
            
            file_size = os.path.getsize(chapter_file) / 1024
            print(f"Глава {i} сохранена: {os.path.basename(chapter_file)} ({file_size:.1f} КБ)")
            saved_files[f"chapter_{i}"] = chapter_file
    
    # Сохраняем сведения об источниках РАГ
    if "_rag_sources" in chapters and chapters["_rag_sources"]:
        sources_file = os.path.join(RESULTS_DIR, f"rag_sources_{timestamp}.json")
        with open(sources_file, 'w', encoding='utf-8') as f:
            json.dump(chapters["_rag_sources"], f, indent=2, ensure_ascii=False)
        print(f"Источники РАГ сохранены: {os.path.basename(sources_file)}")
        saved_files["rag_sources"] = sources_file
    
    # Сохраняем итоги подтверждения
    validation_results = {}
    for i in range(1, 11):
        val_key = f"_validation_chapter{i}"
        if val_key in chapters and chapters[val_key]:
            validation_results[f"chapter_{i}"] = chapters[val_key]
    
    if validation_results:
        validation_file = os.path.join(RESULTS_DIR, f"validation_{timestamp}.json")
        with open(validation_file, 'w', encoding='utf-8') as f:
            json.dump(validation_results, f, indent=2, ensure_ascii=False)
        print(f"Итоги подтверждения сохранены: {os.path.basename(validation_file)}")
        saved_files["validation"] = validation_file
    
    # Общие сведения
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
            for i in range(1, 11)
            if chapters.get(f"_validation_chapter{i}")
        }
    }
    
    meta_file = os.path.join(RESULTS_DIR, f"metadata_{timestamp}.json")
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"Общие сведения сохранены: {os.path.basename(meta_file)}")
    
    return {
        "chapters": saved_files,
        "metadata": meta_file,
        "timestamp": timestamp
    }


# Главная часть

def main():
    print("СОЗДАНИЕ ОТЧЕТОВ ПО ПРОВЕРКЕ ЗАЩИЩЕННОСТИ")
        
    program_start = time.time()
    
    # Проверка наличия РАГ сервера
    rag = RAGClient()
    
    if not rag.available and not rag.local_chunks:
        print("\nРАГ сервер не запущен и нет местных частей!")
        print(f"  Для получения большего объема сведений запустите:")
        print(f"  cd {os.path.abspath('local-rag-mcp/src')}")
        print(f"  uvicorn main:app --host 0.0.0.0 --port 8080")
        print("\n  Продолжить без РАГ? (y/n): ", end="")
        
        response = input().strip().lower()
        if response != 'y':
            print("Работа программы завершена по запросу пользователя")
            return
    
    # Чтение бумаг компании
    reader = CompanyDocumentReader(COMPANY_DOCS_PATH)
    company_docs = reader.read_all_documents()
    
    # Поиск файлов сканирования
    scan_files = glob.glob(os.path.join(SCANS_PATH, "scan_*.json"))
    scan_files.sort()
    
    if not scan_files:
        print("Файлы сканирования не найдены")
        print(f"       Проверьте наличие файлов scan_*.json в: {SCANS_PATH}")
        return
    
    print(f"\nНайдено файлов сканирования: {len(scan_files)}")
    print(f"Загружено бумаг компании: {len(company_docs)}")
    
    print("\nНастройки создания:")
    print(f"       - Бумаг для проверки: {min(len(company_docs), 1)}")
    print(f"       - Файлов сканирования: {min(len(scan_files), 10)}")
    print(f"       - Создаются главы: 1-10")
    print(f"       - Запрашивается частей из РАГ: 50")
    
    response = input("\nНачать создание отчета? (y/n): ").strip().lower()
    if response != 'y':
        print("Создание отменено пользователем")
        return
    
    try:
        # Создание глав
        chapters = generate_all_chapters(scan_files, company_docs, rag)
        
        # Сохранение
        saved = save_chapters(chapters, scan_files)
        
        total_elapsed = time.time() - program_start
        
        print("\n" + "-" * 50)
        print("СОЗДАНИЕ ОТЧЕТА ЗАВЕРШЕНО")
        print("-" * 50)
        print(f"\nИтоги работы:")
        print(f"       - Создано глав: {len([k for k in chapters.keys() if k.startswith('chapter')])}")
        print(f"       - Общее время: {total_elapsed:.2f} сек ({total_elapsed/60:.2f} мин)")
        print(f"       - Итоги сохранены в: {RESULTS_DIR}")
        print(f"       - Использовано источников РАГ: {len(chapters.get('_rag_sources', []))}")
        print("\nСозданные главы:")
        
        for i in range(1, 11):
            chapter_key = f"chapter{i}"
            if chapter_key in chapters:
                print(f"       - Глава {i}: chapter_{i:02d}_{saved['timestamp']}.txt")
        
        # Показываем сведения о подтверждении
        print("\nИтоги подтверждения источников:")
        for i in range(1, 11):
            val_key = f"_validation_chapter{i}"
            if val_key in chapters and chapters[val_key]:
                val = chapters[val_key]
                status = "ДА" if val.get("validation_passed") else "НЕТ"
                print(f"       {status} Глава {i}: найдено пометок: {val.get('markers_count', 0)}")
                if val.get('missing_sources'):
                    print(f"          Неиспользованные источники: {val['missing_sources'][:3]}")
        
    except KeyboardInterrupt:
        print("\n\nСоздание прервано пользователем")
    except Exception as e:
        print(f"\nСерьезная ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()