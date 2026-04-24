# Модель угроз с помощью LLM
ПЕРЕД РАБОТОЙ СОЗДАЙТЕ В ГЛАВОЙ ПАПКЕ ПРОЕКТА ПАПКУ ДЛЯ СОХРАНЕНИЯ РЕЗУЛЬТАТОВ под названием ./model_results
1. Установка Ollama

Установите на Windows Ollama по седующей ссылке:
https://ollama.com/download/windows
Скачать и запустить OllamaSetup.exel

На  Linux
curl -fsSL https://ollama.com/install.sh | sh

2. Установим нужную нам модель

Открываем терминал на хосте и вводим команду:
ollama pull qwen3:4b

3. Загрузка документов компании

Откройте папку .\RAG\data
И вложите туда запрашиваемые документы компании

4. Запуск сканеров

Переходим в директорию, где хранятся скрипты
cd .\diplom_main_version

Запускаем Nmap сканер с помощью команды
python scan_hosts_NMAP.py

Запускаем CVE сканер с помощью команды
uv run --directory CVE-Search-MCP python scan_hosts.py --hosts hosts.json
Либо так
cd CVE-Search-MCP 
uv run python scan_hosts.py --hosts hosts.json

5. Запсук RAG

Для начала переместимся в нужную папку
cd C:\Working\diplom_main_version\local-rag-mcp\src

Активируем окружение
venv\Scripts\activate

Теперь делам запуск индексации базы данных в случае обновления документов или работы с новым объектом
python main.py build-index

Далее запускаем сам RAG
uvicorn main:app --host 0.0.0.0 --port 8080
И не останавливаем до конца работы основной программы

6. Запуск основной команды

В новом окне терминала откроем директорию, где хранится код основной программы
cd .\diplom_main_version

Запускаем Модель угроз с ЛЛМ
python threat_modeling.py

