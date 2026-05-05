# Модель угроз с помощью LLM

Система автоматизированного моделирования угроз информационной безопасности предприятия на основе методических документов ФСТЭК России с использованием Retrieval-Augmented Generation (RAG) и больших языковых моделей (LLM).

## НАЧАЛО РАБОТЫ

Создайте в главной папке проекта папку для сохранения результатов:

powershell
mkdir model_results

## 1. Установка и настройка окружения

### 1.1. Установка Python

Скачайте и установите Python 3.12 с [официального сайта](https://www.python.org/downloads/). При установке отметьте галочку **"Add Python to PATH"**.

### 1.2. Создание виртуального окружения

powershell
cd C:\Working\diplom_main_version
python -m venv venv
venv\Scripts\activate

### 1.3. Установка Python-зависимостей

powershell
pip install langchain langchain-ollama langchain-core
pip install sentence-transformers faiss-cpu
pip install fastapi uvicorn requests
pip install pypdf2 python-docx docx2txt openpyxl pandas
pip install ollama rich tiktoken numpy

## 2. Установка внешних компонентов

### 2.1. Ollama (сервер языковых моделей)

Скачайте и установите с [ollama.com] (https://ollama.com/download/windows).

Для Linux:
bash
curl -fsSL https://ollama.com/install.sh | sh

Загрузите модель:

powershell
ollama pull qwen3.5:4b-q8_0

### 2.2. ЗАГРУЗКА сетевого сканера Nmap

Скачайте и установите с [nmap.org](https://nmap.org/download.html). Проверьте установку:

powershell
nmap --version

### 2.3. UV (менеджер пакетов для CVE-сканера)

powershell
pip install uv

## 3. Настройка локальной модели эмбеддингов
### 3.1. Скачать и сохранить модель (одноразово)

powershell
cd C:\Working\diplom_main_version\local-rag-mcp\src
mkdir models
python -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('all-MiniLM-L6-v2'); 
model.save('models/all-MiniLM-L6-v2'); 

### 3.2. Проверка наличия модели

powershell
dir models\all-MiniLM-L6-v2

Должны быть файлы: `config.json`, `model.safetensors`, `tokenizer.json`, `vocab.txt` и другие.

## 4. Загрузка документов компании

Скопируйте все документы компании в соответствии с требуемым перечнем в папку:

C:\Working\diplom_main_version\local-rag-mcp\src\docs\

**Поддерживаемые форматы:** `.pdf`, `.docx`, `.xlsx`, `.xls`, `.json`, `.txt`, `.md`, `.csv`

**Рекомендуемый перечень документов:**
- Договор на проведение аудита ИБ
- Техническое задание
- Политика информационной безопасности
- Модель угроз
- Матрица доступа
- Перечень программного обеспечения
- Перечень оборудования
- Регламенты ИБ и др.

## 5. Запуск сканеров

### 5.1. Nmap сканер

**Настройка сети для сканирования** — в файле `mcp-vulnerability-scanner/SCRIPT.py`:

python
NETWORK = "192.168.10.0/24"  # Заменить на свою подсеть
PORT_RANGE = "1-65535"       # Все порты (или "1-1000" для быстрого сканирования)
MAX_WORKERS = 5              # Количество потоков


**Запуск:**

powershell
cd C:\Working\diplom_main_version\mcp-vulnerability-scanner
python SCRIPT.py

Результаты сохраняются в `local-rag-mcp/src/docs/`:
- `scan_full_<IP>_<timestamp>.json` — результаты по каждому хосту
- `nmap_summary_<timestamp>.json` — сводный отчет

### 5.2. CVE сканер (CVE-Search-MCP)

CVE-Search-MCP — автономный инструмент для инвентаризации программного обеспечения и поиска уязвимостей без подключения к сети Интернет. Поддерживает международную базу CVE (через AppThreat VDB) и российскую базу БДУ ФСТЭК (через bdu-fstec-mirror).

#### 5.2.1. Установка зависимостей CVE-сканера

powershell
cd C:\Working\diplom_main_version\CVE-Search-MCP
uv sync
uv add "appthreat-vulnerability-db[all]"
uv add paramiko

#### 5.2.2. Загрузка локальных баз данных

**База CVE (AppThreat VDB):**
powershell
uv run python -c "from cve_db_manager import CVEDatabaseManager; CVEDatabaseManager().download_database()"


**База БДУ ФСТЭК:**
powershell
uv run python -c "from cve_db_manager import BDUDatabaseManager; BDUDatabaseManager().download_database(force=True)"

Обе базы сохраняются в папку `CVE-Search-MCP/data/`.

#### 5.2.3. Проверка поиска

powershell
# Пример поиска по NVD
uv run python -c "from cve_search_engine import search_cve_local; print(search_cve_local('log4j', 2))"

# Пример поиска по БДУ ФСТЭК
uv run python -c "from bdu_search_engine import search_bdu_local; print(search_bdu_local('Apache', 2))"

#### 5.2.4. Обновление баз данных

Рекомендуется выполнять раз в день или по расписанию.

powershell
# Обновление CVE
uv run python -c "from cve_db_manager import CVEDatabaseManager; CVEDatabaseManager().download_database(force=True)"

# Обновление БДУ ФСТЭК
uv run python -c "from cve_db_manager import BDUDatabaseManager; BDUDatabaseManager().download_database(force=True)"

#### 5.2.5. Настройка `hosts.json`

Файл находится в `C:\Working\diplom_main_version\CVE-Search-MCP\hosts.json`:

json
[
    {
        "ip": "XXX.XXX.XXX.XXX",
        "os": "windows",
        "username": "логин",
        "password": "пароль",
        "port": 5985
    },
    {
        "ip": "XXX.XXX.XXX.XXX",
        "os": "linux",
        "username": "логин",
        "password": "пароль",
        "port": 22
    }
]

**Windows Server 2003 и старше** могут не поддерживаться. Для них можно подготовить JSON-файл со списком ПО и указать его через ключ `"software_file"` в `hosts.json`.

#### 5.2.6. Запуск CVE-сканера

powershell
cd C:\Working\diplom_main_version\CVE-Search-MCP

# Проверить все программы, установленные на хостах
uv run python scan_hosts.py --max-per-host 0

# Проверить первые 3 программы на каждом хосте для проверки работоспособности
uv run python scan_hosts.py --max-per-host 3

Результаты сохраняются в `local-rag-mcp/src/docs/`:
- `bdu_scan_report_<timestamp>.json` — отчёт по БДУ ФСТЭК
- `cve_scan_report_<timestamp>.json` — отчёт по CVE

#### 5.2.7. Переключение источника уязвимостей

По умолчанию `scan_hosts.py` работает с **БДУ ФСТЭК**. Чтобы переключить на международную **CVE**, откройте `scan_hosts.py` и замените:

python
# Для БДУ:
result = search_bdu_local(keyword, limit=3)

# Для NVD:
result = search_cve_local(keyword, limit=3)

## 6. Запуск RAG-системы

### 6.1. Перейти в папку RAG и активировать окружение

powershell
cd C:\Working\diplom_main_version\local-rag-mcp\src
venv\Scripts\activate

### 6.2. Построить индекс (при первом запуске или обновлении документов)

powershell
python main.py build-index

### 6.3. Запустить RAG-сервер

powershell
uvicorn main:app --host 0.0.0.0 --port 8080

**Не закрывайте это окно!** Сервер должен работать во время генерации отчета.

### 6.4. Проверить работу сервера

powershell
# В другом терминале
curl http://localhost:8080/health

## 7. Запуск генератора отчета

### 7.1. Открыть новый терминал

powershell
cd C:\Working\diplom_main_version
venv\Scripts\activate

### 7.2. Запустить генерацию

powershell
python threat_modeling.py

### 7.3. Следовать инструкциям в консоли

Программа запросит подтверждение на генерацию отчета.
Убедитесь, что все в работе исправно и введите `y` и нажмите Enter для запуска.

### 7.4. Результаты

Сгенерированные главы сохраняются в папку `model_results/`:
- `chapter_01.txt` — `chapter_10.txt` (тексты глав)
- `rag_sources.json` (использованные источники)
- `validation.json` (результаты проверки маркеров)
- `metadata.json` (метаданные генерации)
- `calculation_details.txt` (расчеты критичности уязвимостей)

## 8. Автоматический запуск всего программного продукта

Для автоматического выполнения всего пайплайна:

powershell
cd C:\Working\diplom_main_version
venv\Scripts\activate
python run_all.py

**run_all.py выполняет последовательно:**
1. Nmap сканирование сети
2. CVE сканирование уязвимостей
3. Копирование результатов в папку RAG
4. Построение FAISS индекса
5. Запуск RAG сервера в отдельном окне
6. Генерацию отчета
7. Автоматическую остановку RAG сервера при завершении

## 9. Настройка параметров системы под собственные требования по мощности используемого оборудования

### Изменение модели LLM

В файле `threat_modeling.py`:

python
llm = OllamaLLM(
    model="qwen3.5:4b-q8_0",  # ← Изменить модель
    temperature=0.2,           # 0.1 — строже, 0.5 — творчески
    num_ctx=50000,             # Размер контекстного окна
    num_predict=50000,         # Максимальная длина ответа
)

### Изменение количества чанков из RAG

В файле `threat_modeling.py`:

python
rag_ctx_1, rag_sources_1 = rag.get_context_with_metadata(
    "поисковый запрос",
    k=50  # ← Изменить (50, 100, 200)
)

### Настройка RAG индексирования

В файле `local-rag-mcp/src/config.py`:

python
CHUNK_SIZE = 700        # Размер чанка в токенах
CHUNK_OVERLAP = 100     # Перекрытие между чанками
TOP_K = 50              # Количество возвращаемых чанков
