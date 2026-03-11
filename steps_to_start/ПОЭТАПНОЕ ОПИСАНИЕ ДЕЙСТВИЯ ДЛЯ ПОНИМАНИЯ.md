ШАГ 1: Полная очистка Docker\-окружения

Цель: Удалить все тестовые и дублирующие контейнеры и образы, оставить только то, что нужно для финальной системы\.

Окно: PowerShell \(от имени администратора\)

Рабочая директория: любая \(например, C:\\\)

Выполните команду:  
docker ps \-a  


  
__*CONTAINER ID   IMAGE                                    COMMAND                  CREATED          STATUS                      PORTS       NAMES*__

__*654c271d82e7   ollama/ollama:latest                     "/bin/ollama serve"      11 minutes ago   Exited \(0\) 7 minutes ago                sleepy\_cannon*__

__*62b51c72a43a   ollama/ollama:latest                     "/bin/ollama serve"      5 days ago       Exited \(0\) 21 hours ago                 ollama\-diplom*__

__*0e5dfd0d5b93   ghcr\.io/ollama\-webui/ollama\-webui:main   "bash start\.sh"          6 days ago       Exited \(137\) 21 hours ago               ollama\-webui*__

__*4eea073ef9b8   ollama/ollama                            "/bin/ollama serve"      6 days ago       Exited \(0\) 21 hours ago                 my\_ollama*__

__*16c3a10058c4   ollama/ollama                            "/bin/ollama serve"      7 days ago       Up 7 minutes                11434/tcp   ollama*__

__*1274d2781e70   2ae8eadbc09a                             "python \-m src\.nmap\_…"   11 days ago      Exited \(137\) 21 hours ago               nmap\-mcp*__

__*7f8f1fb69b6e   5aa0a68fc6ff                             "python \-m main"         12 days ago      Exited \(0\) 21 hours ago                 cve\-mcp*__

  
В предыдущих логах вы уже подтверждали, что в этом контейнере есть модель qwen3:4b\-instruct \(и starcoder2:3b\), так как ранее выполняли:  
Вывод  
PS C:\\Users\\User> docker exec ollama ollama list

__*NAME                 ID              SIZE      MODIFIED*__

__*qwen3:4b\-instruct    0edcdef34593    2\.5 GB    7 days ago*__

__*starcoder2:3b        9f4ae0aff61e    1\.7 GB    7 days ago*__

  
  
СЛЕДУЮЩИЙ ШАГ: ПРОВЕРИТЬ, ЧТО API OLLAMA ДОСТУПНО

Окно: PowerShell \(любое, текущая директория не важна\)

Выполните команду:

curl \-X GET http://localhost:11434/api/tags

Если curl не распознан в PowerShell \(часто бывает\), используйте вместо него:

Invoke\-RestMethod \-Uri "http://localhost:11434/api/tags" \-Method Get \-TimeoutSec 5

Что должно быть при успехе:

JSON с массивом моделей, например:

__*models*__

__*\-\-\-\-\-\-*__

__*\{@\{name=starcoder2:3b; model=starcoder2:3b; modified\_at=2026\-01\-27T21:55\.\.\.*__

Если ошибка \(например, Unable to connect, Connection refused\), значит, контейнер ollama запущен, но не слушает порт на хосте — возможно, из\-за того, что \-p 11434:11434 был указан некорректно \(в вашем случае в docker ps видно 11434/tcp, но нет 0\.0\.0\.0:11434\->11434/tcp, как у ollama\-diplom\)\. Это критично\!  
  
Если Оллама не работает, тогда   
Нам нужно пересоздать контейнер ollama с правильным пробросом портов, но сохранить модели\.  
docker stop ollama

Удалите его \(модели останутся, так как они в томе\)

docker rm ollama  
  
Запустите новый контейнер с правильными параметрами:

docker run \-d \-\-name ollama \-v ollama:/root/\.ollama \-p 11434:11434 ollama/ollama

💡 Объяснение флагов:

\-d — фоновый режим

\-\-name ollama — имя контейнера

\-v ollama:/root/\.ollama — сохраняет все модели из тома ollama

\-p 11434:11434 — правильный проброс порта \(хост:контейнер\)

ollama/ollama — образ

docker ps \-\-filter "name=ollama"

Invoke\-RestMethod \-Uri "http://localhost:11434/api/tags" \-TimeoutSec 5  
  
__*PS C:\\Users\\User> docker stop ollama*__

__*ollama*__

__*PS C:\\Users\\User> docker rm ollama*__

__*ollama*__

__*PS C:\\Users\\User> docker run \-d \-\-name ollama \-v ollama:/root/\.ollama \-p 11434:11434 ollama/ollama*__

__*a03800f6b966e9b1a33aa1cbfd76c33db91f5fb3bc46a1597fb16f51b9f46a0d*__

__*PS C:\\Users\\User> Invoke\-RestMethod \-Uri "http://localhost:11434/api/tags" \-TimeoutSec 5*__

__*models*__

__*\-\-\-\-\-\-*__

__*\{@\{name=qwen3:4b\-instruct; model=qwen3:4b\-instruct; modified\_at=2026\-02\-\.\.\.*__

__*PS C:\\Users\\User> docker ps \-\-filter "name=ollama"*__

__*CONTAINER ID   IMAGE           COMMAND               CREATED          STATUS          PORTS                                             NAMES*__

__*a03800f6b966   ollama/ollama   "/bin/ollama serve"   17 seconds ago   Up 17 seconds   0\.0\.0\.0:11434\->11434/tcp, \[::\]:11434\->11434/tcp   ollama  
  
*__ШАГ 3: ПРОВЕРКА РАБОТЫ MCP\-СЕРВЕРОВ

Теперь проверим MCP\-серверы \(Nmap и CVE\), которые должны быть запущены в отдельных контейнерах для взаимодействия с Python\-скриптом\.

Проверим, есть ли актуальные образы для MCP\-серверов:

docker images | findstr "mcp"

  
__*WARNING: This output is designed for human readability\. For machine\-readable output, please use \-\-format\.*__

__*cve\-mcp:latest                           4e0be91e41d1        271MB         65\.4MB*__

__*cve\-search\-mcp\-server:latest             52dfcdde1e32        362MB         88\.2MB*__

__*nmap\-mcp\-server:latest                   f032fa52866c        287MB         67\.6MB*__

__*nmap\-mcp:latest                          6c20ae7c8569        287MB         67\.6MB   U*__

  
Запустим контейнеры с MCP\-серверами:

- docker run — запустить контейнер
- \-\-rm — автоматически удалить контейнер после завершения
- \-\-name test\-cve или \-\-name test\-nmap — задать имя контейнера \(отличается от nmap\)
- \-it — интерактивный режим с терминалом \(будут видны логи\)
- cve\-search\-mcp\-server:latest или nmap\-mcp\-server:latest — образ для CVE\-поиска

PS C:\\Working\\diplom\\scripts> docker run \-\-rm \-\-name test\-nmap \-it nmap\-mcp\-server:latest

__*2026\-02\-10 07:18:05,764 \- nmap\-mcp \- INFO \- Using nmap executable at: /usr/bin/nmap*__

__*2026\-02\-10 07:18:05,766 \- nmap\-mcp \- INFO \- Starting nmap MCP server*__

PS C:\\Working\\diplom\\scripts> docker run \-\-rm \-\-name test\-cve \-it cve\-search\-mcp\-server:latest  


__*\[02/10/26 08:03:55\] INFO     Starting cve\-search\_mcp              main\.py:12  
*__  
Если старые контейнеры с такими же именами уже существуют \(остановленные\)\. Нужно их удалить и запустить новые\.  
docker rm nmap\-mcp  
docker rm cve\-mcp

__*Проверка логов запуска контейнеров серверов  
PS C:\\Working\\diplom> docker logs nmap\-mcp*__

__*2026\-02\-10 07:07:17,001 \- nmap\-mcp \- INFO \- Using nmap executable at: /usr/bin/nmap*__

__*2026\-02\-10 07:07:17,003 \- nmap\-mcp \- INFO \- Starting nmap MCP server*__

__*PS C:\\Working\\diplom> docker logs cve\-mcp*__

__*\[02/10/26 07:07:26\] INFO     Starting cve\-search\_mcp                  main\.py:12*__

__*PS C:\\Working\\diplom>*__

  
Определение местоположения моделей  
Ваши модели \(qwen3:4b\-instruct и starcoder2:3b\) хранятся в томе Docker, а не в образе\.

Образ ollama/ollama:latest — это "движок" Ollama \(программа\)

Docker том ollama — это хранилище моделей \(данные\)

Модели загружаются внутри контейнера и сохраняются в томе

2\. КАКОЙ КОНТЕЙНЕР ИСПОЛЬЗУЕТ МОДЕЛИ:

docker exec ollama ollama list

\# ↓

__*\# NAME                 ID              SIZE      MODIFIED*__

__*\# qwen3:4b\-instruct    0edcdef34593    2\.5 GB    7 days ago*__

__*\# starcoder2:3b        9f4ae0aff61e    1\.7 GB    7 days ago*__

Выполнялась команда docker exec ollama — значит, модели находятся в контейнере ollama \(a03800f6b966\)

Модели НЕ будут потеряны, если удалить другие контейнеры

Том ollama сохраняет модели между перезапусками контейнера

  
Код для запуска самого базового скрипта для создания модели угроз  
cd C:\\Working\\Diplom\\scripts\\

python 123\.py  


  
"""

final\_system\.py \- Финальная система автоматизированного анализа безопасности

Дипломная работа: Полный цикл от сканирования до AI\-анализа

Автор: \[Ваше имя\]

Дата: 2026\-02\-10

"""

import subprocess          \# Для запуска команд Docker и системных команд

import requests           \# Для HTTP\-запросов к API Ollama

import time               \# Для работы со временем \(замеры, таймауты\)

import json               \# Для работы с JSON\-данными \(не используется сейчас, но может понадобиться\)

class DockerNmapAgent:

    """Класс для выполнения Nmap сканирования через Docker контейнер"""

    

    def scan\(self, target\):

        """Выполняет сканирование портов целевого хоста через Docker"""

        print\(f"\[Nmap Agent\] Сканирую \{target\}\.\.\."\)

        

        \# Команда для запуска Nmap в Docker контейнере

        cmd = \[

            "docker", "run", "\-\-rm",           \# Запуск с автоматическим удалением после завершения

            "instrumentisto/nmap",            \# Образ Docker с Nmap

            "\-sV", "\-p", "22,80,443,3389,445", \# Параметры сканирования: обнаружение версий, конкретные порты

            target                            \# Целевой IP\-адрес

        \]

        

        try:

            \# Выполнение команды с таймаутом 120 секунд

            result = subprocess\.run\(cmd, capture\_output=True, text=True, timeout=120\)

            

            \# Проверка успешности выполнения

            if result\.returncode == 0:

                print\(f"\[Nmap Agent\] Сканирование \{target\} завершено"\)

                return result\.stdout          \# Возвращаем вывод Nmap

            else:

                \# В случае ошибки возвращаем первые 200 символов stderr

                return f"Ошибка: \{result\.stderr\[:200\]\}"

                

        except Exception as e:

            \# Обработка исключений \(таймаут, отсутствие Docker и т\.д\.\)

            return f"Ошибка: \{str\(e\)\}"

class DockerCVEAgent:

    """Класс для анализа уязвимостей \(CVE\) через Docker"""

    

    def search\_vulnerabilities\(self, nmap\_output\):

        """Анализирует вывод Nmap и ищет соответствующие уязвимости CVE"""

        print\("\[CVE Agent\] Ищу уязвимости\.\.\."\)

        

        \# Парсинг вывода Nmap для извлечения информации о сервисах

        services = self\.\_parse\_nmap\_output\(nmap\_output\)

        

        \# В текущей реализации используется эмуляция CVE поиска

        \# В реальной системе здесь был бы вызов CVE\-search через Docker

        return self\.\_generate\_basic\_cve\_report\(services\)

    

    def \_parse\_nmap\_output\(self, nmap\_output\):

        """Парсит вывод Nmap и извлекает информацию об открытых портах и сервисах"""

        services = \[\]

        lines = nmap\_output\.split\('\\n'\)

        

        for line in lines:

            \# Ищем строки с информацией об открытых портах

            if "/tcp" in line and "open" in line:

                parts = line\.split\(\)

                if len\(parts\) >= 3:

                    \# Создаем словарь с информацией о сервисе

                    service = \{

                        "port": parts\[0\]\.split\('/'\)\[0\],   \# Номер порта

                        "name": parts\[2\],                 \# Имя сервиса

                        "version": ' '\.join\(parts\[3:\]\) if len\(parts\) > 3 else ""  \# Версия

                    \}

                    services\.append\(service\)

        

        return services

    

    def \_generate\_basic\_cve\_report\(self, services\):

        """Генерирует базовый отчет об уязвимостях на основе обнаруженных сервисов"""

        report = "\# АНАЛИЗ УЯЗВИМОСТЕЙ \(CVE\)\\n\\n"

        

        if not services:

            report \+= "Сервисы не обнаружены\\n"

            return report

        

        \# Для каждого сервиса добавляем информацию о возможных уязвимостях

        for svc in services:

            report \+= f"\#\# Сервис: \{svc\['name'\]\} \(порт \{svc\['port'\]\}\)\\n"

            report \+= f"Версия: \{svc\['version'\]\}\\n"

            

            \# Эвристический анализ уязвимостей по типу сервиса

            if "ssh" in svc\['name'\]\.lower\(\):

                report \+= "\*\*Возможные CVE:\*\*\\n"

                report \+= "\- CVE\-2023\-28531 \(HIGH\): Buffer overflow in OpenSSH\\n"

                report \+= "\- CVE\-2023\-38408 \(MEDIUM\): Authentication bypass\\n"

                report \+= "\*\*Рекомендация:\*\* Обновить OpenSSH\\n\\n"

            

            elif "http" in svc\['name'\]\.lower\(\) or "nginx" in svc\['version'\]\.lower\(\):

                report \+= "\*\*Возможные CVE:\*\*\\n"

                report \+= "\- CVE\-2021\-3618 \(CRITICAL\): HTTP/2 memory corruption\\n"

                report \+= "\- CVE\-2021\-23017 \(HIGH\): Integer overflow\\n"

                report \+= "\*\*Рекомендация:\*\* Обновить nginx\\n\\n"

            

            elif "apache" in svc\['version'\]\.lower\(\):

                report \+= "\*\*Возможные CVE:\*\*\\n"

                report \+= "\- CVE\-2022\-22721 \(HIGH\): Path traversal\\n"

                report \+= "\- CVE\-2021\-41773 \(CRITICAL\): Code execution\\n"

                report \+= "\*\*Рекомендация:\*\* Обновить Apache\\n\\n"

        

        return report

class OllamaAnalyzer:

    """Класс для AI\-анализа через локальную языковую модель Ollama"""

    

    def \_\_init\_\_\(self\):

        \# URL API Ollama для генерации текста

        self\.url = "http://localhost:11434/api/generate"

    

    def analyze\_security\(self, target, nmap\_data, cve\_data\):

        """Отправляет данные на анализ в языковую модель и получает отчет"""

        print\(f"\[Ollama\] Анализирую \{target\}\.\.\."\)

        

        \# Создание промпта \(запроса\) для модели

        prompt = self\.\_create\_prompt\(target, nmap\_data, cve\_data\)

        

        \# Подготовка данных для запроса

        data = \{

            "model": "qwen3:4b\-instruct",     \# Используемая модель

            "prompt": prompt,                 \# Текст запроса

            "stream": False,                  \# Не использовать потоковый вывод

            "options": \{

                "num\_predict": 1200,          \# Максимальное количество токенов в ответе

                "temperature": 0\.7            \# "Креативность" модели \(0\-1\)

            \}

        \}

        

        try:

            \# Отправка POST\-запроса к API Ollama с таймаутом 180 секунд

            response = requests\.post\(self\.url, json=data, timeout=180\)

            

            if response\.status\_code == 200:

                result = response\.json\(\)      \# Парсинг JSON\-ответа

                return result\.get\('response', 'Нет ответа'\)

            else:

                return f"Ошибка: \{response\.status\_code\}"

                

        except Exception as e:

            return f"Ошибка: \{str\(e\)\}"

    

    def \_create\_prompt\(self, target, nmap\_data, cve\_data\):

        """Создает структурированный промпт для анализа безопасности"""

        

        prompt = f"""Ты — эксперт по кибербезопасности\. Проанализируй результаты сканирования сервера и создай МОДЕЛЬ УГРОЗ с рекомендациями\.

ЦЕЛЬ: \{target\}

РЕЗУЛЬТАТЫ СКАНИРОВАНИЯ NMAP:

\{nmap\_data\[:1500\]\}

АНАЛИЗ УЯЗВИМОСТЕЙ CVE:

\{cve\_data\}

ТВОЯ ЗАДАЧА:

1\. СОЗДАЙ МОДЕЛЬ УГРОЗ для этого сервера

2\. ОПИШИ КОНКРЕТНЫЕ УЯЗВИМОСТИ

3\. ДАЙ ПРАКТИЧЕСКИЕ РЕКОМЕНДАЦИИ по исправлению

4\. УКАЖИ ПРИОРИТЕТ действий

СТРУКТУРА ОТВЕТА:

\#\# 1\. МОДЕЛЬ УГРОЗ

\- Атаки на каждый открытый порт

\- Возможные векторы атак

\- Уровень риска для каждого сервиса

\#\# 2\. КОНКРЕТНЫЕ УЯЗВИМОСТИ

\- Перечисли найденные CVE

\- Опиши как их можно эксплуатировать

\- Оцени критичность

\#\# 3\. РЕКОМЕНДАЦИИ

\- Конкретные шаги для исправления

\- Примеры команд для настройки

\- Приоритет действий \(что делать первым\)

\#\# 4\. ВЫВОДЫ

\- Общая оценка безопасности

\- Ключевые проблемы

\- Необходимые меры

Отвечай максимально подробно и профессионально на русском языке\. Будь конкретным\!"""

        

        return prompt

class SecurityOrchestrator:

    """Главный класс\-оркестратор, управляющий всем процессом анализа"""

    

    def \_\_init\_\_\(self\):

        \# Инициализация всех компонентов системы

        self\.nmap\_agent = DockerNmapAgent\(\)

        self\.cve\_agent = DockerCVEAgent\(\)

        self\.ollama = OllamaAnalyzer\(\)

    

    def analyze\_host\(self, target\):

        """Выполняет полный цикл анализа для одного хоста"""

        print\(f"\\n\{'='\*70\}"\)

        print\(f"🚀 НАЧИНАЮ АНАЛИЗ ХОСТА: \{target\}"\)

        print\(f"\{'='\*70\}"\)

        

        \# 1\. ЭТАП: СЕТЕВОЕ СКАНИРОВАНИЕ

        print\("\\n\[1/3\] Запускаю Nmap агент\.\.\."\)

        nmap\_result = self\.nmap\_agent\.scan\(target\)

        

        if "Ошибка" in nmap\_result:

            print\(f"❌ Nmap ошибка: \{nmap\_result\}"\)

            return None

        

        \# 2\. ЭТАП: АНАЛИЗ УЯЗВИМОСТЕЙ

        print\("\\n\[2/3\] Запускаю CVE агент\.\.\."\)

        cve\_result = self\.cve\_agent\.search\_vulnerabilities\(nmap\_result\)

        

        \# 3\. ЭТАП: AI\-АНАЛИЗ

        print\("\\n\[3/3\] Запрашиваю анализ у Ollama\.\.\."\)

        security\_analysis = self\.ollama\.analyze\_security\(target, nmap\_result, cve\_result\)

        

        \# 4\. ЭТАП: СОХРАНЕНИЕ РЕЗУЛЬТАТОВ

        self\.\_save\_report\(target, nmap\_result, cve\_result, security\_analysis\)

        

        return security\_analysis

    

    def \_save\_report\(self, target, nmap\_data, cve\_data, analysis\):

        """Сохраняет полный отчет в текстовый файл"""

        \# Создание имени файла \(замена точек на подчеркивания\)

        filename = f"SECURITY\_REPORT\_\{target\.replace\('\.', '\_'\)\}\.txt"

        

        \# Открытие файла для записи с кодировкой UTF\-8

        with open\(filename, 'w', encoding='utf\-8'\) as f:

            \# Заголовок отчета

            f\.write\("="\*80 \+ "\\n"\)

            f\.write\(f"ОТЧЕТ ПО АНАЛИЗУ БЕЗОПАСНОСТИ\\n"\)

            f\.write\("="\*80 \+ "\\n\\n"\)

            f\.write\(f"🎯 ЦЕЛЬ: \{target\}\\n"\)

            f\.write\(f"📅 ВРЕМЯ: \{time\.strftime\('%Y\-%m\-%d %H:%M:%S'\)\}\\n"\)

            f\.write\("="\*80 \+ "\\n\\n"\)

            

            \# Раздел с результатами Nmap

            f\.write\("📊 РЕЗУЛЬТАТЫ NMAP:\\n"\)

            f\.write\("\-"\*80 \+ "\\n"\)

            f\.write\(nmap\_data\[:1000\] \+ "\\n\\n"\)

            

            \# Раздел с анализом CVE

            f\.write\("⚠️  АНАЛИЗ CVE УЯЗВИМОСТЕЙ:\\n"\)

            f\.write\("\-"\*80 \+ "\\n"\)

            f\.write\(cve\_data \+ "\\n\\n"\)

            

            \# Раздел с AI\-анализом

            f\.write\("🔍 МОДЕЛЬ УГРОЗ И РЕКОМЕНДАЦИИ \(AI АНАЛИЗ\):\\n"\)

            f\.write\("\-"\*80 \+ "\\n"\)

            f\.write\(analysis \+ "\\n"\)

            

            \# Подвал отчета

            f\.write\("="\*80 \+ "\\n"\)

            f\.write\("✅ ОТЧЕТ СФОРМИРОВАН АВТОМАТИЧЕСКОЙ СИСТЕМОЙ\\n"\)

            f\.write\("="\*80 \+ "\\n"\)

        

        print\(f"💾 Отчет сохранен: \{filename\}"\)

        

        \# Вывод статистики

        words = len\(analysis\.split\(\)\)

        print\(f"📈 Анализ содержит: \{words\} слов"\)

def main\(\):

    """Главная функция, точка входа в программу"""

    print\("="\*80\)

    print\("🎯 СИСТЕМА АНАЛИЗА БЕЗОПАСНОСТИ С DOCKER АГЕНТАМИ"\)

    print\("="\*80\)

    

    \# ПРОВЕРКА ЗАВИСИМОСТЕЙ

    

    \# 1\. Проверка доступности Docker

    try:

        subprocess\.run\(\["docker", "\-\-version"\], capture\_output=True, check=True\)

        print\("✅ Docker доступен"\)

    except:

        print\("❌ Docker не доступен"\)

        return

    

    \# 2\. Проверка доступности Ollama API

    try:

        response = requests\.get\("http://localhost:11434/api/tags", timeout=5\)

        if response\.status\_code == 200:

            print\("✅ Ollama доступен"\)

        else:

            print\("❌ Ollama не отвечает"\)

            return

    except:

        print\("❌ Не удалось подключиться к Ollama"\)

        return

    

    \# 3\. Проверка Docker образов

    print\("\\n🔍 Проверяю Docker образы\.\.\."\)

    try:

        \# Проверка образа Nmap

        subprocess\.run\(\["docker", "image", "inspect", "instrumentisto/nmap"\], 

                      capture\_output=True, check=True\)

        print\("✅ Образ nmap доступен"\)

        

        \# Проверка образа CVE

        subprocess\.run\(\["docker", "image", "inspect", "cve\-search\-mcp\-server:latest"\], 

                      capture\_output=True, check=True\)

        print\("✅ Образ CVE поиска доступен"\)

        

    except:

        print\("⚠️  Некоторые образы могут отсутствовать"\)

        print\("   Используется резервный режим"\)

    

    \# ЦЕЛЕВЫЕ ХОСТЫ ДЛЯ АНАЛИЗА

    targets = \["192\.168\.10\.10", "192\.168\.10\.20", "192\.168\.10\.101"\]

    

    print\(f"\\n🎯 Будут проанализированы хосты: \{targets\}"\)

    print\("⏱️  Ориентировочное время: 5\-7 минут"\)

    

    \# СОЗДАНИЕ ОРКЕСТРАТОРА

    orchestrator = SecurityOrchestrator\(\)

    

    \# СЛОВАРЬ ДЛЯ ХРАНЕНИЯ РЕЗУЛЬТАТОВ

    all\_results = \{\}

    

    \# ОСНОВНОЙ ЦИКЛ АНАЛИЗА

    for target in targets:

        try:

            print\(f"\\n\{'='\*70\}"\)

            print\(f"🔍 АНАЛИЗ: \{target\}"\)

            print\(f"\{'='\*70\}"\)

            

            \# Запуск анализа для текущего хоста

            result = orchestrator\.analyze\_host\(target\)

            

            if result:

                \# Сохранение результата

                all\_results\[target\] = result

                

                \# Вывод превью анализа

                print\("\\n📄 НАЧАЛО АНАЛИЗА:"\)

                print\("\-"\*40\)

                print\(result\[:400\] \+ "\.\.\." if len\(result\) > 400 else result\)

                print\("\-"\*40\)

            

        except KeyboardInterrupt:

            \# Обработка прерывания пользователем \(Ctrl\+C\)

            print\("\\n⚠️  Анализ прерван пользователем"\)

            break

        except Exception as e:

            \# Обработка других исключений

            print\(f"❌ Критическая ошибка для \{target\}: \{e\}"\)

            continue

    

    \# ВЫВОД ИТОГОВ

    print\(f"\\n\{'='\*80\}"\)

    print\("📋 ИТОГИ АНАЛИЗА:"\)

    print\(f"\{'='\*80\}"\)

    

    \# Подсчет успешных анализов

    successful = len\(all\_results\)

    print\(f"✅ Успешно проанализировано: \{successful\}/\{len\(targets\)\} хостов"\)

    

    \# Детальная информация по каждому хосту

    for target in targets:

        if target in all\_results:

            words = len\(all\_results\[target\]\.split\(\)\)

            filename = f"SECURITY\_REPORT\_\{target\.replace\('\.', '\_'\)\}\.txt"

            print\(f"  • \{target\}: \{words\} слов в анализе \(файл: \{filename\}\)"\)

        else:

            print\(f"  • \{target\}: не удалось проанализировать"\)

    

    \# ФИНАЛЬНОЕ СООБЩЕНИЕ

    print\(f"\\n🎯 АНАЛИЗ ЗАВЕРШЕН\!"\)

    print\("Все отчеты сохранены в файлах SECURITY\_REPORT\_\*\.txt"\)

if \_\_name\_\_ == "\_\_main\_\_":

    \# Точка входа \- запуск главной функции при прямом выполнении файла

    main\(\)  
  
  
  
ПРИМЕНЕНИЕ RAG  
[https://ai\-manual\.ru/article/polnyij\-gajd\-dlya\-nachinayuschih\-kak\-s\-nulya\-zapustit\-lokalnuyu\-llm\-s\-pamyatyu\-chatov\-i\-rag/  
](https://ai-manual.ru/article/polnyij-gajd-dlya-nachinayuschih-kak-s-nulya-zapustit-lokalnuyu-llm-s-pamyatyu-chatov-i-rag/)  
установка qdrant  
docker run \-p 6333:6333 \-p 6334:6334 \-v $\{PWD\}/qdrant\_storage:/qdrant/storage qdrant/qdrant

  
__*PS C:\\Working\\diplom\\rag\_system> docker run \-p 6333:6333 \-p 6334:6334 \-v $\{PWD\}/qdrant\_storage:/qdrant/storage qdrant/qdrant*__

__*Unable to find image 'qdrant/qdrant:latest' locally*__

__*latest: Pulling from qdrant/qdrant*__

__*4f4fb700ef54: Already exists*__

__*c75ac8c66d87: Downloading  20\.97MB/34\.07MB*__

__*db0b76a2c40c: Download complete*__

__*ea4d7e7e5bb7: Download complete*__

__*66bf113c4036: Download complete*__

__*91f4f63bc90b: Download complete*__

__*1733a4cd5954: Downloading  20\.97MB/29\.78MB*__

__*d50154ffb087: Download complete*__

__*a7c0607c6532: Download complete*__

__*3fcc5e69acba: Download complete*__

  
  
1\. ПРОВЕРЬТЕ WEB ИНТЕРФЕЙС

Откройте в браузере: http://localhost:6333/dashboard

Вы должны увидеть дашборд Qdrant с пустой коллекцией\.

2\. УСТАНОВИТЕ PYTHON БИБЛИОТЕКИ

В новом терминале PowerShell \(не закрывая Qdrant\):

pip install qdrant\-client sentence\-transformers langchain langchain\-community pypdf python\-docx  
  
ПРОВЕРЬТЕ ВЕБ\-ИНТЕРФЕЙС

Снова откройте http://localhost:6333/dashboard

Там должна появиться коллекция documents с загруженными данными\.

5\. ДАЛЬНЕЙШИЕ ШАГИ:

Что делать	Команда / Описание

Остановить Qdrant	Ctrl\+C в окне с Docker

Запустить в фоне	docker run \-d \-p 6333:6333 \-p 6334:6334 \-v $\{PWD\}/qdrant\_storage:/qdrant/storage \-\-name qdrant qdrant/qdrant

Остановить контейнер	docker stop qdrant

Запустить снова	docker start qdrant

Посмотреть логи	docker logs qdrant

Удалить контейнер	docker rm qdrant

6\. ПОЛЕЗНЫЕ КОМАНДЫ ДЛЯ ПРОВЕРКИ:

powershell

\# Проверка API

curl http://localhost:6333/collections

\# Python проверка

python \-c "from qdrant\_client import QdrantClient; print\(QdrantClient\('localhost', port=6333\)\.get\_collections\(\)\)"  
  
Настройка Вебюай  
  
PS C:\\Users\\User> docker stop open\-webui

open\-webui

PS C:\\Users\\User> docker rm open\-webui

open\-webui

PS C:\\Users\\User> docker run \-d \-p 3000:8080 \-v C:\\Working\\diplom\\RAG\_WebUI\\data:/app/backend/data \-v C:\\Working\\diplom\\RAG\_WebUI\\uploads:/app/backend/uploads \-\-name open\-webui ghcr\.io/open\-webui/open\-webui:main

__*67ad92f785f7098a5e003acf4cbc6536552a975c389b3cf8c2745ddadcbb2541*__

PS C:\\Users\\User> docker exec open\-webui ping host\.docker\.internal

__*OCI runtime exec failed: exec failed: unable to start container process: exec: "ping": executable file not found in $PATH*__

PS C:\\Users\\User>  
  


Создание РАГА одним методом  


PS C:\\Users\\User> Invoke\-RestMethod \-Uri http://localhost:11434/api/embeddings \`

>>   \-Method Post \`

>>   \-ContentType "application/json" \`

>>   \-Body '\{"model":"nomic\-embed\-text","prompt":"test"\}'

__*embedding*__

__*\-\-\-\-\-\-\-\-\-*__

__*\{0,6650439500808716, 0,26974064111709595, \-4,426966667175293, \-0,2072848\.\.\.*__

PS C:\\Users\\User> $response = Invoke\-RestMethod \-Uri http://localhost:11434/api/embeddings \`

>>   \-Method Post \`

>>   \-ContentType "application/json" \`

>>   \-Body '\{"model":"nomic\-embed\-text","prompt":"test"\}'

PS C:\\Users\\User> $response\.embedding\.Length

__*768*__

PS C:\\Users\\User> Invoke\-RestMethod \-Uri http://localhost:6333/collections/docs \`

>>   \-Method Put \`

>>   \-ContentType "application/json" \`

>>   \-Body '\{

>>     "vectors": \{

>>       "size": 768,

>>       "distance": "Cosine"

>>     \}

>>   \}'

__*result status        time*__

__*\-\-\-\-\-\- \-\-\-\-\-\-        \-\-\-\-*__

__*  True ok     0,934479019*__

PS C:\\Users\\User> git clone https://github\.com/CVEProject/cvelistV5\.git

__*Cloning into 'cvelistV5'\.\.\.*__

__*remote: Enumerating objects: 1540272, done\.*__

__*remote: Counting objects: 100% \(141/141\), done\.*__

__*remote: Compressing objects: 100% \(86/86\), done\.*__

__*remote: Total 1540272 \(delta 120\), reused 64 \(delta 55\), pack\-reused 1540131 \(from 2\)*__

__*Receiving objects: 100% \(1540272/1540272\), 1\.58 GiB | 5\.60 MiB/s, done\.*__

__*Resolving deltas: 100% \(1498377/1498377\), done\.*__

__*Updating files: 100% \(333002/333002\), done\.*__

PS C:\\Users\\User>

Установка Local\-Qdrant\-RAG создание рага вторым методом  
  


Клонировать репозиторий

git clone https://github\.com/XinBow99/Local\-Qdrant\-RAG\.git

cd local\-qdrant\-rag

Установите зависимости

Установите все необходимые пакеты Python\.

pip install \-r requirement\.txt

pip install llama\-index

pip install llama\-index\-embeddings\-huggingface

pip install llama\-index\-vector\-stores\-qdrant 

pip install llama\-index\-llms\-ollama 

pip install python\-dotenv 

pip install llama\-index\-readers\-file pypdf python\-docx

cd C:\\Working\\diplom\\local\-qdrant\-rag

py \-3\.11 \-m venv venv 

\.\\venv\\Scripts\\activate  

Deactivate \- еоманда отключение окружения

Настройте Qdrant

docker pull qdrant/qdrant

docker stop qdrant

docker rm qdrant

docker run \-p 6333:6333 \-v C:\\Working\\diplom\\local\-qdrant\-rag\\qdrant\_storage:/qdrant/storage \-\-name qdrant qdrant/qdrant   
Используется для сохранения данных рага в нужной папке

Загрузка данных в Qdrant

Прежде чем использовать модель RAG, необходимо загрузить набор данных в Qdrant\. DataIngestorВ этом вам поможет класс в qdrant\_data\_helper\.py\.

from utils import qdrant\_data\_helper

ingestor = qdrant\_data\_helper\.DataIngestor\(

 q\_client\_url="http://localhost:6333/", 

 q\_api\_key="test", \# вы можете изменить его на свой собственный ключ API qdrant, если вы его указали, в противном случае используйте None

    data\_path="\./data/", 

 collection\_name="dcard\_collection", 

 embedder\_name="sentence\-transformers/all\-mpnet\-base\-v2"

 \)

Указатель = проглатывающий\.проглатывать\(\)

Печать\("Индекс создан succс уважением\!"\)

Структура папок для data\_path:

data/

├── doc1\.txt

├── doc2\.txt

├── doc3\.txt

└── \.\.\.

Использование модели RAG

Чтобы использовать модель RAG для ответов на запросы, создайте экземпляр класса RAG и воспользуйтесь методом get\_response\.

"""

Thie is inference code for the RAG and Qdrant with Ollama

"""

from utils\.qdrant\_data\_helper import RAG, Query

def main\(\):

 host = "localhost"

    rag = RAG\(

 q\_client\_url=f"http://\{host\}:6333/", 

 q\_api\_key="test", \# you can change this to your own qdrant api key if you have set it, otherwise, using None

        ollama\_model="gemma:7b", 

 ollama\_base\_url=f"http://\{host\}:11434",

 \)

 

 search\_index = rag\.qdrant\_index\(

 collection\_name="dcard\_collection", 

 chunk\_size=1024

 \)

 query = Query\(

 query="高科大是什麼時候合併的？",

 top\_k=5

 \)

 result = rag\.get\_response\(

 index= search\_index,

 query= query,

 append\_query="",

 response\_mode="tree\_summarize"

 \)

 print\("Result: ", result\.search\_result\)

 print\("Score: ", result\.source\)

if \_\_name\_\_ == "\_\_main\_\_":

 main\(\)

УСПЕШНЫЙ КОД ДЛЯ РАГА НА КВАДРАНТЕ

[https://github\.com/XinBow99/Local\-Qdrant\-RAG](https://github.com/XinBow99/Local-Qdrant-RAG)

Это чистый раг без соединения с nmap и cve

C:\\Working\\diplom\\Local\-Qdrant\-RAG\\utils\\qdrant\_data\_helper\.py

\#\# \-\*\- coding: utf\-8 \-\*\-

"""

Модуль для работы с Qdrant и RAG

Поддерживаемые форматы: txt, rtf, pdf, md, doc, docx

Модель эмбеддингов: sentence\-transformers/all\-MiniLM\-L6\-v2 \(384 dim\)

"""

import os

import re

from typing import List

from dotenv import load\_dotenv

from llama\_index\.core import Document, Settings

from llama\_index\.embeddings\.huggingface import HuggingFaceEmbedding

from llama\_index\.vector\_stores\.qdrant import QdrantVectorStore

from llama\_index\.core import StorageContext, VectorStoreIndex

from llama\_index\.llms\.ollama import Ollama

from llama\_index\.core\.response\_synthesizers import ResponseMode

from qdrant\_client import QdrantClient

\# Загрузка переменных из \.env

load\_dotenv\(\)

\# ============================================================

\# Класс для загрузки данных в Qdrant

\# ============================================================

class DataIngestor:

    def \_\_init\_\_\(

        self,

        q\_client\_url: str = "http://localhost:6333/",

        q\_api\_key: str = None,

        data\_path: str = "\./data/",

        collection\_name: str = "dcard\_collection",

        embedder\_name: str = None,

        chunk\_size: int = 512

    \):

        self\.q\_client\_url = q\_client\_url

        self\.q\_api\_key = q\_api\_key

        self\.data\_path = data\_path

        self\.collection\_name = collection\_name

        self\.chunk\_size = chunk\_size

        

        \# Модель эмбеддингов \(384 dim \- all\-MiniLM\-L6\-v2\)

        self\.embedder\_name = embedder\_name or os\.getenv\(

            "EMBED\_MODEL\_NAME", 

            "sentence\-transformers/all\-MiniLM\-L6\-v2"

        \)

        

        print\(f"🔧 Модель эмбеддингов: \{self\.embedder\_name\}"\)

        

        \# Инициализация эмбеддера

        self\.embedder = HuggingFaceEmbedding\(

            model\_name=self\.embedder\_name,

            max\_length=512,

            trust\_remote\_code=True

        \)

        

        \# Настройка глобальных параметров LlamaIndex

        Settings\.embed\_model = self\.embedder

        Settings\.chunk\_size = self\.chunk\_size

        Settings\.llm = None

        

        \# Инициализация Qdrant клиента

        self\.qdrant\_client = QdrantClient\(

            url=self\.q\_client\_url,

            api\_key=self\.q\_api\_key

        \)

    def load\_documents\(self\) \-> List\[Document\]:

        """

        Загрузка документов из папки\.

        Поддерживаемые форматы: txt, rtf, pdf, md, doc, docx

        """

        from pypdf import PdfReader

        

        documents = \[\]

        supported\_extensions = \('\.txt', '\.rtf', '\.pdf', '\.md', '\.doc', '\.docx'\)

        

        print\(f"📂 Сканирование папки: \{self\.data\_path\}"\)

        print\(f"📄 Поддерживаемые форматы: \{', '\.join\(supported\_extensions\)\}"\)

        

        if not os\.path\.exists\(self\.data\_path\):

            os\.makedirs\(self\.data\_path\)

            print\(f"⚠️ Папка \{self\.data\_path\} не найдена, создана новая"\)

            return documents

        

        for filename in os\.listdir\(self\.data\_path\):

            filepath = os\.path\.join\(self\.data\_path, filename\)

            

            if not os\.path\.isfile\(filepath\):

                continue

            

            \# Проверка расширения

            if not filename\.lower\(\)\.endswith\(supported\_extensions\):

                print\(f"⏭️ Пропущено: \{filename\} \(неподдерживаемый формат\)"\)

                continue

            

            try:

                text = ""

                

                \# 📄 PDF файлы

                if filename\.lower\(\)\.endswith\('\.pdf'\):

                    print\(f"📖 Чтение PDF: \{filename\}\.\.\."\)

                    reader = PdfReader\(filepath\)

                    for page in reader\.pages:

                        page\_text = page\.extract\_text\(\)

                        if page\_text:

                            text \+= page\_text \+ "\\n"

                

                \# 📄 RTF файлы

                elif filename\.lower\(\)\.endswith\('\.rtf'\):

                    print\(f"📖 Чтение RTF: \{filename\}\.\.\."\)

                    with open\(filepath, 'r', encoding='utf\-8', errors='ignore'\) as f:

                        rtf\_content = f\.read\(\)

                        text = re\.sub\(r'\\\{\[\\\\\]\[^\}\]\*\\\}', '', rtf\_content\)

                        text = re\.sub\(r'\\\\\[a\-z\]\+\\d?\\s?', '', text\)

                        text = text\.replace\('\{', ''\)\.replace\('\}', ''\)\.replace\('\\\\', ''\)

                

                \# 📄 DOC/DOCX файлы

                elif filename\.lower\(\)\.endswith\(\('\.doc', '\.docx'\)\):

                    print\(f"📖 Чтение DOC/DOCX: \{filename\}\.\.\."\)

                    try:

                        from docx import Document as DocxDocument

                        doc = DocxDocument\(filepath\)

                        for paragraph in doc\.paragraphs:

                            text \+= paragraph\.text \+ "\\n"

                    except ImportError:

                        print\(f"⚠️ Установите python\-docx: pip install python\-docx"\)

                        continue

                

                \# 📄 TXT и MD файлы

                elif filename\.lower\(\)\.endswith\(\('\.txt', '\.md'\)\):

                    print\(f"📖 Чтение TXT/MD: \{filename\}\.\.\."\)

                    for encoding in \['utf\-8', 'cp1251', 'latin\-1'\]:

                        try:

                            with open\(filepath, "r", encoding=encoding\) as f:

                                text = f\.read\(\)

                            break

                        except UnicodeDecodeError:

                            continue

                

                \# Добавляем документ

                if text\.strip\(\):

                    documents\.append\(Document\(

                        text=text, 

                        metadata=\{

                            "filename": filename,

                            "filepath": filepath,

                            "type": filename\.split\('\.'\)\[\-1\]\.lower\(\)

                        \}

                    \)\)

                    print\(f"✅ Успешно: \{filename\}"\)

                else:

                    print\(f"⚠️ Нет текста в файле: \{filename\}"\)

                    

            except Exception as e:

                print\(f"❌ Ошибка при чтении \{filename\}: \{e\}"\)

                continue

        

        print\(f"📊 Всего документов: \{len\(documents\)\}"\)

        return documents

    def ingest\(self\):

        """

        Индексация документов в Qdrant

        """

        \# Загрузка документов

        documents = self\.load\_documents\(\)

        

        if not documents:

            raise ValueError\(f"No supported files found in \{self\.data\_path\}"\)

        

        \# Проверка существования коллекции

        collection\_exists = self\.qdrant\_client\.collection\_exists\(

            collection\_name=self\.collection\_name

        \)

        

        if collection\_exists:

            print\(f"🗑️ Коллекция \{self\.collection\_name\} уже существует, удаляем\.\.\."\)

            self\.qdrant\_client\.delete\_collection\(collection\_name=self\.collection\_name\)

        

        \# Создание векторного хранилища

        print\(f"🔄 Создание индекса в Qdrant\.\.\."\)

        vector\_store = QdrantVectorStore\(

            client=self\.qdrant\_client,

            collection\_name=self\.collection\_name

        \)

        

        storage\_context = StorageContext\.from\_defaults\(vector\_store=vector\_store\)

        

        \# Создание индекса

        index = VectorStoreIndex\.from\_documents\(

            documents,

            storage\_context=storage\_context,

            embed\_model=self\.embedder

        \)

        

        print\(f"✅ Индекс создан успешно\!"\)

        return index

\# ============================================================

\# Класс для запросов

\# ============================================================

class Query:

    def \_\_init\_\_\(self, query: str, top\_k: int = 5\):

        self\.query = query

        self\.top\_k = top\_k

\# ============================================================

\# Класс для RAG\-запросов

\# ============================================================

class RAG:

    def \_\_init\_\_\(

        self,

        q\_client\_url: str = "http://localhost:6333/",

        q\_api\_key: str = None,

        ollama\_model: str = "qwen2\.5\-coder:7b\-instruct\-q4\_K\_M",

        ollama\_base\_url: str = "http://localhost:11434"

    \):

        self\.q\_client\_url = q\_client\_url

        self\.q\_api\_key = q\_api\_key

        self\.ollama\_model = ollama\_model

        self\.ollama\_base\_url = ollama\_base\_url

        

        \# Инициализация Qdrant клиента

        self\.qdrant\_client = QdrantClient\(

            url=self\.q\_client\_url,

            api\_key=self\.q\_api\_key

        \)

        

        \# Модель эмбеддингов \(ОБЯЗАТЕЛЬНО та же, что при индексации\!\)

        self\.embedder\_name = os\.getenv\(

            "EMBED\_MODEL\_NAME", 

            "sentence\-transformers/all\-MiniLM\-L6\-v2"

        \)

        

        print\(f"🔧 Модель эмбеддингов: \{self\.embedder\_name\}"\)

        

        self\.embedder = HuggingFaceEmbedding\(

            model\_name=self\.embedder\_name,

            max\_length=512,

            trust\_remote\_code=True

        \)

        

        \# Настройка LLM

        Settings\.llm = Ollama\(

            model=self\.ollama\_model,

            base\_url=self\.ollama\_base\_url,

            request\_timeout=300\.0,

            context\_window=4096

        \)

        Settings\.embed\_model = self\.embedder

    def qdrant\_index\(self, collection\_name: str, chunk\_size: int = 1024\):

        """

        Получение индекса из Qdrant

        """

        Settings\.chunk\_size = chunk\_size

        Settings\.embed\_model = self\.embedder

        

        vector\_store = QdrantVectorStore\(

            client=self\.qdrant\_client,

            collection\_name=collection\_name

        \)

        

        storage\_context = StorageContext\.from\_defaults\(vector\_store=vector\_store\)

        index = VectorStoreIndex\.from\_vector\_store\(

            vector\_store=vector\_store,

            storage\_context=storage\_context,

            embed\_model=self\.embedder  \# КРИТИЧНО ВАЖНО\!

        \)

        

        return index

    def get\_response\(self, index, query: Query, append\_query: str = "", response\_mode: str = "tree\_summarize"\):

        """

        Получение ответа от RAG\-системы

        """

        query\_engine = index\.as\_query\_engine\(

            similarity\_top\_k=query\.top\_k,

            response\_mode=ResponseMode\.TREE\_SUMMARIZE

        \)

        

        response = query\_engine\.query\(query\.query \+ append\_query\)

        

        return type\('Result', \(\), \{

            'search\_result': str\(response\),

            'source': \[node\.node\.text for node in response\.source\_nodes\]

        \}\)\(\)

А еще  C:\\Working\\diplom\\Local\-Qdrant\-RAG\\\.env

![](data:image/png;base64,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)

\(venv\) PS C:\\Working\\diplom\\local\-qdrant\-rag> python for\_genreate\_embedding\.py

\# \-\*\- coding: utf\-8 \-\*\-

"""

Скрипт для загрузки данных в Qdrant

Поддерживаемые форматы: txt, rtf, pdf, md, doc, docx

Модель: sentence\-transformers/all\-MiniLM\-L6\-v2 \(384 dim\)

"""

from utils import qdrant\_data\_helper

def main\(\):

    ingestor = qdrant\_data\_helper\.DataIngestor\(

        q\_client\_url="http://localhost:6333/", 

        q\_api\_key=None,

        data\_path="\./data/", 

        collection\_name="dcard\_collection", 

        embedder\_name="sentence\-transformers/all\-MiniLM\-L6\-v2",  \# 384 dim

        chunk\_size=512

    \)

    index = ingestor\.ingest\(\)

    print\("\\n" \+ "="\*50\)

    print\("✅ ИНДЕКСАЦИЯ ЗАВЕРШЕНА УСПЕШНО\!"\)

    print\("="\*50\)

    print\(f"📊 Коллекция: dcard\_collection"\)

    print\(f"🔧 Модель: sentence\-transformers/all\-MiniLM\-L6\-v2"\)

    print\(f"📏 Размерность вектора: 384"\)

    print\(f"🌐 Qdrant Dashboard: http://localhost:6333/dashboard"\)

    print\("="\*50\)

if \_\_name\_\_ == "\_\_main\_\_":

    main\(\)

\(venv\) PS C:\\Working\\diplom\\local\-qdrant\-rag> python main\.py 

\# \-\*\- coding: utf\-8 \-\*\-

"""

Скрипт для RAG\-запросов с использованием Qwen2\.5\-Coder

Модель эмбеддингов: sentence\-transformers/all\-MiniLM\-L6\-v2 \(384 dim\)

"""

from utils\.qdrant\_data\_helper import RAG, Query

def main\(\):

    host = "localhost"

    

    print\("\\n" \+ "="\*50\)

    print\("🤖 RAG\-СИСТЕМА ЗАПУЩЕНА"\)

    print\("="\*50\)

    

    rag = RAG\(

        q\_client\_url=f"http://localhost:6333/", 

        q\_api\_key=None,

        ollama\_model="qwen2\.5\-coder:7b\-instruct\-q4\_K\_M",

        ollama\_base\_url=f"http://localhost:11434",

    \)

    

    print\(f"📊 Коллекция: dcard\_collection"\)

    print\(f"🔧 Модель эмбеддингов: sentence\-transformers/all\-MiniLM\-L6\-v2 \(384 dim\)"\)

    print\(f"🧠 LLM модель: qwen2\.5\-coder:7b\-instruct\-q4\_K\_M"\)

    print\("="\*50\)

    

    search\_index = rag\.qdrant\_index\(

        collection\_name="dcard\_collection", 

        chunk\_size=1024

    \)

    \# Пример запроса \(измените на свой вопрос\)

    query = Query\(

        query="Кто твой владелец?",

        top\_k=5

    \)

    print\(f"\\n❓ Вопрос: \{query\.query\}"\)

    print\("⏳ Обработка запроса\.\.\.\\n"\)

    result = rag\.get\_response\(

        index=search\_index,

        query=query,

        append\_query="",

        response\_mode="tree\_summarize"

    \)

    print\("\\n" \+ "="\*50\)

    print\("📝 ОТВЕТ:"\)

    print\("="\*50\)

    print\(result\.search\_result\)

    print\("\\n" \+ "="\*50\)

    print\("📚 ИСТОЧНИКИ:"\)

    print\("="\*50\)

    for i, source in enumerate\(result\.source, 1\):

        print\(f"\\n\[\{i\}\] \{source\[:500\]\}\.\.\."\)

    print\("="\*50\)

if \_\_name\_\_ == "\_\_main\_\_":

    main\(\)

НАСТРОЙКА ЕЩЕ ОДНОГО MCP СЕРВЕРА, КОТОРЫЙ ОДНОВРЕМЕННО МОЖЕТ И СКАНИРОВАТЬ ПОРТЫ И ВЫДАВАТЬ CVE   
Установка образа с гитхаба  
PS C:\\Users\\User> cd C:\\Working\\diplom

PS C:\\Working\\diplom> git clone https://github\.com/RobertoDure/mcp\-vulnerability\-scanner\.git

__*Cloning into 'mcp\-vulnerability\-scanner'\.\.\.*__

__*remote: Enumerating objects: 34, done\.*__

__*remote: Counting objects: 100% \(34/34\), done\.*__

__*remote: Compressing objects: 100% \(27/27\), done\.*__

__*remote: Total 34 \(delta 6\), reused 28 \(delta 3\), pack\-reused 0 \(from 0\)*__

__*Receiving objects: 100% \(34/34\), 180\.98 KiB | 753\.00 KiB/s, done\.*__

__*Resolving deltas: 100% \(6/6\), done\.  
*__Установка зависимостей

PS C:\\Working\\diplom\\mcp\-vulnerability\-scanner> pip install mcp

PS C:\\Working\\diplom\\scripts> \# Установка Node\.js LTS через winget

PS C:\\Working\\diplom\\scripts> winget install OpenJS\.NodeJS\.LTS

__*Перед использованием источника "msstore" необходимо просмотреть следующие соглашения\.*__

__*Terms of Transaction: https://aka\.ms/microsoft\-store\-terms\-of\-transaction*__

__*Для правильной работы источника требуется отправить во внутреннюю службу двухбуквенный код текущего региона компьютера \(например, "RU"\)\.*__

__*Вы согласны со всеми условиями исходных соглашений?*__

__*\[Y\] Да  \[N\] Нет: Y*__

__*Найдено Node\.js \(LTS\) \[OpenJS\.NodeJS\.LTS\] Версия 24\.13\.1*__

__*Лицензия на это приложение предоставлена вам владельцем\.*__

__*Корпорация Майкрософт не несет ответственность за сторонние пакеты и не предоставляет для них никакие лицензии\.*__

__*Скачивание https://nodejs\.org/dist/v24\.13\.1/node\-v24\.13\.1\-x64\.msi*__

__*  ██████████████████████████████  30\.7 MB / 30\.7 MB*__

__*Хэш установщика успешно проверен*__

__*Запуск установки пакета\.\.\.*__

__*Установщик запросит запуск от имени администратора\. Ожидайте запроса\.*__

__*Успешно установлено  
*__PS C:\\Working\\diplom\\scripts> Test\-Path "C:\\Program Files\\nodejs\\node\.exe"

__*True*__

PS C:\\Working\\diplom\\scripts> $env:Path \+= ";C:\\Program Files\\nodejs"

PS C:\\Working\\diplom\\scripts> node \-\-version

__*v24\.13\.1*__

PS C:\\Working\\diplom\\scripts> npm \-\-version

__*11\.8\.0*__

PS C:\\Working\\diplom\\scripts> python vuln\_scanner\_client\.py  
  
запуск MCP сервера непосредственный  
PS C:\\Working\\diplom\\scripts> echo '\{"jsonrpc":"2\.0","method":"tools/call","params":\{"name":"scan\-ip","arguments":\{"ip":"192\.168\.10\.10"\}\},"id":1\}' | C:\\Progra~1\\nodejs\\npm\.cmd \-\-prefix C:\\Working\\diplom\\mcp\-vulnerability\-scanner run dev

__*> mcp\-vulnerability\-scanner@1\.0\.0 dev*__

__*> tsx src/index\.ts*__

__*\[2026\-02\-18T17:14:00\.109Z\] WARNING: VulnDB API not configured\. Will use mock vulnerability data\.*__

__*\[2026\-02\-18T17:14:00\.110Z\] WARNING: Set VULNDB\_API\_KEY environment variable to enable VulnDB integration\.*__

__*\[2026\-02\-18T17:14:00\.112Z\] Starting Vulnerability Scanner MCP Server\.\.\.*__

__*\[2026\-02\-18T17:14:00\.113Z\] Vulnerability Scanner MCP Server started and ready*__

__*\[2026\-02\-18T17:14:00\.118Z\] Starting scan for IP: 192\.168\.10\.10*__

__*\[2026\-02\-18T17:14:00\.118Z\] \[ScannerService\] Starting vulnerability scan for IP: 192\.168\.10\.10*__

__*\[2026\-02\-18T17:14:00\.133Z\] \[ScannerService\] VulnDB API not configured\. Using mock vulnerability data\.*__

__*\[2026\-02\-18T17:14:00\.140Z\] \[ScannerService\] Nmap is not installed\. Skipping Nmap scan\.*__

__*\{"result":\{"content":\[\{"type":"text","text":"\# Vulnerability Scan Results for 192\.168\.10\.10\\n\\nNo vulnerabilities found\.\\n\\n"\}\]\},"jsonrpc":"2\.0","id":1\}*__

__*PS C:\\Working\\diplom\\scripts>  
*__

КОД ДЛЯ ЗАПУСКА MCP СЕРВЕРА, КОТОРЫЙ ДВА В ОДНОМ \(MCP\+NMAP\)

__*  
*__python vuln\_scanner\_client\.py__*  
  
*__\#\!/usr/bin/env python3

"""

🔐 PRODUCTION MCP VULNERABILITY SCANNER

Готовый продукт для реального сканирования уязвимостей

Версия 1\.0\.0

"""

import subprocess

import json

import os

import sys

import time

import requests

from datetime import datetime

from pathlib import Path

from typing import Dict, Any, List, Optional

import re

\# Конфигурация

OUTPUT\_DIR = "C:\\\\Working\\\\diplom\\\\Local\-Qdrant\-RAG\\\\mcp\_scn\_results"

SCANNER\_PATH = "C:\\\\Working\\\\diplom\\\\mcp\-vulnerability\-scanner"

OLLAMA\_MODEL = "qwen2\.5\-coder:7b\-instruct\-q4\_K\_M"

os\.makedirs\(OUTPUT\_DIR, exist\_ok=True\)

class ProductionScanner:

    """Продакшн\-сканер с поддержкой реальных данных"""

    

    def \_\_init\_\_\(self\):

        self\.nmap\_available = self\.\_check\_nmap\(\)

        self\.vulndb\_configured = self\.\_check\_vulndb\_config\(\)

        self\.scanner\_ready = False

        

    def \_check\_nmap\(self\) \-> bool:

        """Проверяет наличие Nmap в системе"""

        try:

            result = subprocess\.run\(

                \["nmap", "\-\-version"\],

                capture\_output=True,

                text=True,

                timeout=5

            \)

            if result\.returncode == 0:

                version = result\.stdout\.split\('\\n'\)\[0\]

                print\(f"✅ Nmap найден: \{version\}"\)

                return True

        except:

            pass

        print\("❌ Nmap не найден\. Сканирование будет ограничено\."\)

        return False

    

    def \_check\_vulndb\_config\(self\) \-> bool:

        """Проверяет наличие API ключа VulnDB"""

        env\_file = Path\(SCANNER\_PATH\) / "\.env"

        if env\_file\.exists\(\):

            with open\(env\_file, 'r'\) as f:

                content = f\.read\(\)

                if 'VULNDB\_API\_KEY=' in content and 'your\_key' not in content:

                    print\("✅ VulnDB API ключ настроен"\)

                    return True

        print\("⚠️ VulnDB API ключ не настроен\. Используются тестовые данные\."\)

        return False

    

    def scan\_ip\(self, ip: str\) \-> Dict\[str, Any\]:

        """

        Выполняет полное сканирование IP\-адреса

        Возвращает структурированные результаты

        """

        print\(f"\\n🔍 Запуск сканирования \{ip\}\.\.\."\)

        

        \# JSON\-RPC запрос к MCP серверу

        request = \{

            "jsonrpc": "2\.0",

            "method": "tools/call",

            "params": \{

                "name": "scan\-ip",

                "arguments": \{"ip": ip\}

            \},

            "id": 1

        \}

        

        \# Сохраняем запрос

        temp\_file = os\.path\.join\(OUTPUT\_DIR, f"temp\_\{ip\.replace\('\.', '\_'\)\}\.json"\)

        with open\(temp\_file, 'w', encoding='utf\-8'\) as f:

            json\.dump\(request, f\)

        

        \# Запускаем сканер

        cmd = f'type "\{temp\_file\}" | cd /d "\{SCANNER\_PATH\}" && npm run dev'

        

        try:

            result = subprocess\.run\(

                cmd,

                shell=True,

                capture\_output=True,

                text=True,

                timeout=120  \# 2 минуты на сканирование

            \)

            

            \# Парсим ответ

            scan\_result = self\.\_parse\_response\(result\.stdout, ip\)

            

            \# Обогащаем результатами Nmap если доступен

            if self\.nmap\_available:

                scan\_result = self\.\_enrich\_with\_nmap\(scan\_result, ip\)

            

            return scan\_result

            

        except subprocess\.TimeoutExpired:

            return \{"error": "Timeout", "ip": ip\}

        except Exception as e:

            return \{"error": str\(e\), "ip": ip\}

        finally:

            if os\.path\.exists\(temp\_file\):

                os\.remove\(temp\_file\)

    

    def \_parse\_response\(self, output: str, ip: str\) \-> Dict\[str, Any\]:

        """Парсит ответ от MCP сервера"""

        \# Ищем JSON в выводе

        for line in output\.split\('\\n'\):

            line = line\.strip\(\)

            if line\.startswith\('\{'\) and line\.endswith\('\}'\):

                try:

                    return json\.loads\(line\)

                except:

                    continue

        

        \# Если JSON не найден, создаем структурированный ответ

        return \{

            "ip": ip,

            "timestamp": datetime\.now\(\)\.isoformat\(\),

            "raw\_output": output,

            "vulnerabilities": self\.\_extract\_vulnerabilities\(output\),

            "open\_ports": self\.\_extract\_ports\(output\)

        \}

    

    def \_enrich\_with\_nmap\(self, scan\_result: Dict\[str, Any\], ip: str\) \-> Dict\[str, Any\]:

        """Обогащает результаты данными от Nmap"""

        print\("  📡 Запуск дополнительного Nmap сканирования\.\.\."\)

        

        try:

            \# Быстрое сканирование популярных портов

            nmap\_result = subprocess\.run\(

                \["nmap", "\-sV", "\-\-top\-ports", "100", ip\],

                capture\_output=True,

                text=True,

                timeout=60

            \)

            

            if nmap\_result\.returncode == 0:

                scan\_result\['nmap\_scan'\] = nmap\_result\.stdout

                

                \# Парсим открытые порты

                ports = \[\]

                for line in nmap\_result\.stdout\.split\('\\n'\):

                    if '/tcp' in line and 'open' in line:

                        parts = line\.split\(\)

                        port\_info = \{

                            'port': parts\[0\]\.split\('/'\)\[0\],

                            'state': parts\[1\],

                            'service': parts\[2\] if len\(parts\) > 2 else 'unknown',

                            'version': ' '\.join\(parts\[3:\]\) if len\(parts\) > 3 else ''

                        \}

                        ports\.append\(port\_info\)

                

                scan\_result\['open\_ports'\] = ports

                print\(f"    Найдено портов: \{len\(ports\)\}"\)

                

        except Exception as e:

            print\(f"    Ошибка Nmap: \{e\}"\)

        

        return scan\_result

    

    def \_extract\_vulnerabilities\(self, text: str\) \-> List\[Dict\[str, Any\]\]:

        """Извлекает информацию об уязвимостях из текста"""

        vulns = \[\]

        

        \# Ищем CVE номера

        cve\_pattern = r'CVE\-\\d\{4\}\-\\d\+'

        cves = re\.findall\(cve\_pattern, text\)

        

        for cve in set\(cves\):  \# Убираем дубликаты

            vulns\.append\(\{

                'id': cve,

                'source': 'extracted',

                'severity': 'unknown'

            \}\)

        

        return vulns

    

    def \_extract\_ports\(self, text: str\) \-> List\[int\]:

        """Извлекает информацию о портах из текста"""

        ports = \[\]

        

        \# Ищем упоминания портов

        port\_pattern = r'port\[^\\d\]\*\(\\d\+\)|\(\\d\+\)/tcp'

        matches = re\.findall\(port\_pattern, text\.lower\(\)\)

        

        for match in matches:

            for group in match:

                if group and group\.isdigit\(\):

                    ports\.append\(int\(group\)\)

        

        return list\(set\(ports\)\)  \# Убираем дубликаты

    

    def get\_status\_report\(self\) \-> str:

        """Возвращает отчет о состоянии системы"""

        report = \[\]

        report\.append\("="\*60\)

        report\.append\("📊 СТАТУС СИСТЕМЫ"\)

        report\.append\("="\*60\)

        

        report\.append\(f"\\n📁 Директория результатов: \{OUTPUT\_DIR\}"\)

        report\.append\(f"📁 Директория сканера: \{SCANNER\_PATH\}"\)

        

        report\.append\(f"\\n🔧 Компоненты:"\)

        report\.append\(f"  • Nmap: \{'✅ ДОСТУПЕН' if self\.nmap\_available else '❌ НЕ НАЙДЕН'\}"\)

        report\.append\(f"  • VulnDB API: \{'✅ НАСТРОЕН' if self\.vulndb\_configured else '⚠️ НЕ НАСТРОЕН'\}"\)

        

        if not self\.nmap\_available:

            report\.append\("\\n⚠️ ВНИМАНИЕ: Для полноценной работы установите Nmap:"\)

            report\.append\("   https://nmap\.org/download\.html"\)

        

        if not self\.vulndb\_configured:

            report\.append\("\\n⚠️ ВНИМАНИЕ: Для реальных CVE настройте VulnDB API:"\)

            report\.append\("   1\. Зарегистрируйтесь на https://vuldb\.com"\)

            report\.append\("   2\. Получите API ключ"\)

            report\.append\(f"   3\. Создайте файл \{SCANNER\_PATH\}\\\\\.env с:"\)

            report\.append\("      VULNDB\_API\_KEY=ваш\_ключ"\)

        

        return '\\n'\.join\(report\)

class OllamaAnalyzer:

    """Анализатор на основе Ollama"""

    

    def \_\_init\_\_\(self\):

        self\.available = self\.\_check\_ollama\(\)

    

    def \_check\_ollama\(self\) \-> bool:

        try:

            requests\.get\("http://localhost:11434/api/tags", timeout=2\)

            return True

        except:

            return False

    

    def analyze\(self, ip: str, scan\_data: Dict\[str, Any\]\) \-> str:

        """Глубокий анализ результатов сканирования"""

        

        if not self\.available:

            return "⚠️ Ollama недоступен\. Анализ пропущен\."

        

        \# Формируем структурированные данные для анализа

        ports\_info = scan\_data\.get\('open\_ports', \[\]\)

        vulns = scan\_data\.get\('vulnerabilities', \[\]\)

        

        ports\_text = "\\n"\.join\(\[

            f"  \- Порт \{p\['port'\]\}: \{p\['service'\]\} \{p\.get\('version', ''\)\}"

            for p in ports\_info\[:10\]

        \]\) if ports\_info else "  Открытые порты не обнаружены"

        

        vulns\_text = "\\n"\.join\(\[

            f"  \- \{v\['id'\]\} \(источник: \{v\.get\('source', 'unknown'\)\}\)"

            for v in vulns\[:10\]

        \]\) if vulns else "  Уязвимости не обнаружены"

        

        prompt = f"""Ты — эксперт по кибербезопасности\. Проанализируй результаты сканирования\.

IP АДРЕС: \{ip\}

ОТКРЫТЫЕ ПОРТЫ И СЕРВИСЫ:

\{ports\_text\}

НАЙДЕННЫЕ УЯЗВИМОСТИ:

\{vulns\_text\}

На основе этих данных предоставь структурированный анализ:

1\. 🎯 КРИТИЧЕСКИЕ УГРОЗЫ:

   \- Какие сервисы наиболее уязвимы?

   \- Какие CVE требуют немедленного внимания?

   \- Оценка уровня риска \(НИЗКИЙ/СРЕДНИЙ/ВЫСОКИЙ/КРИТИЧЕСКИЙ\)

2\. 🛠️ НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:

   \- Что нужно исправить прямо сейчас?

   \- Конкретные команды/рекомендации

3\. 📋 ПЛАН ДАЛЬНЕЙШИХ ДЕЙСТВИЙ:

   \- Дополнительные проверки

   \- Рекомендации по усилению защиты

Ответ предоставь на русском языке, кратко и по делу\."""

        

        try:

            response = requests\.post\(

                "http://localhost:11434/api/generate",

                json=\{

                    "model": OLLAMA\_MODEL,

                    "prompt": prompt,

                    "stream": False,

                    "options": \{

                        "num\_predict": 500,

                        "temperature": 0\.3

                    \}

                \},

                timeout=60

            \)

            

            if response\.status\_code == 200:

                return response\.json\(\)\.get\('response', 'Нет ответа'\)

            else:

                return f"Ошибка API: \{response\.status\_code\}"

        except Exception as e:

            return f"Ошибка подключения к Ollama: \{e\}"

def main\(\):

    """Главная функция"""

    

    print\("""

╔═══════════════════════════════════════════════════════════════╗

║     🔐 PRODUCTION MCP VULNERABILITY SCANNER v1\.0\.0           ║

║     Готовый продукт для реального сканирования уязвимостей   ║

╚═══════════════════════════════════════════════════════════════╝

    """\)

    

    \# Инициализация

    scanner = ProductionScanner\(\)

    analyzer = OllamaAnalyzer\(\)

    

    \# Отчет о состоянии

    print\(scanner\.get\_status\_report\(\)\)

    

    \# Цели сканирования

    targets = \["192\.168\.10\.10", "192\.168\.10\.20", "192\.168\.10\.101"\]

    

    print\(f"\\n🎯 Цели сканирования: \{', '\.join\(targets\)\}"\)

    print\(f"📁 Результаты будут сохранены в: \{OUTPUT\_DIR\}"\)

    

    \# Подтверждение

    if input\("\\n▶️ Начать сканирование? \(y/n\): "\)\.lower\(\) \!= 'y':

        print\("❌ Сканирование отменено"\)

        return

    

    all\_results = \{\}

    

    \# Сканирование каждого хоста

    for i, target in enumerate\(targets, 1\):

        print\(f"\\n\{'='\*70\}"\)

        print\(f"🚀 ХОСТ \{i\}/\{len\(targets\)\}: \{target\}"\)

        print\(f"\{'='\*70\}"\)

        

        \# Сканирование

        scan\_result = scanner\.scan\_ip\(target\)

        all\_results\[target\] = scan\_result

        

        \# Сохранение JSON

        timestamp = datetime\.now\(\)\.strftime\("%Y%m%d\_%H%M%S"\)

        safe\_target = target\.replace\('\.', '\_'\)

        json\_file = os\.path\.join\(OUTPUT\_DIR, f"scan\_\{safe\_target\}\_\{timestamp\}\.json"\)

        

        with open\(json\_file, 'w', encoding='utf\-8'\) as f:

            json\.dump\(scan\_result, f, indent=2, ensure\_ascii=False\)

        

        print\(f"\\n✅ JSON сохранен: \{os\.path\.basename\(json\_file\)\}"\)

        

        \# Анализ через Ollama

        print\("\\n🤖 Запуск AI\-анализа\.\.\."\)

        analysis = analyzer\.analyze\(target, scan\_result\)

        

        \# Сохранение анализа

        analysis\_file = os\.path\.join\(OUTPUT\_DIR, f"analysis\_\{safe\_target\}\_\{timestamp\}\.txt"\)

        with open\(analysis\_file, 'w', encoding='utf\-8'\) as f:

            f\.write\(f"🔐 АНАЛИЗ БЕЗОПАСНОСТИ \{target\}\\n"\)

            f\.write\("="\*50 \+ "\\n\\n"\)

            f\.write\(analysis\)

        

        print\(f"✅ Анализ сохранен: \{os\.path\.basename\(analysis\_file\)\}"\)

        print\(f"\\n📊 РЕЗУЛЬТАТ АНАЛИЗА:\\n\{analysis\}"\)

        

        if i < len\(targets\):

            print\("\\n⏳ Пауза 5 секунд\.\.\."\)

            time\.sleep\(5\)

    

    \# Сохранение сводного отчета

    summary\_file = os\.path\.join\(OUTPUT\_DIR, f"summary\_\{datetime\.now\(\)\.strftime\('%Y%m%d\_%H%M%S'\)\}\.json"\)

    with open\(summary\_file, 'w', encoding='utf\-8'\) as f:

        json\.dump\(all\_results, f, indent=2, ensure\_ascii=False\)

    

    print\(f"\\n\{'='\*70\}"\)

    print\("✅ СКАНИРОВАНИЕ УСПЕШНО ЗАВЕРШЕНО"\)

    print\(f"\{'='\*70\}"\)

    print\(f"\\n📁 Все результаты: \{OUTPUT\_DIR\}"\)

    print\(f"📊 Сводный отчет: \{os\.path\.basename\(summary\_file\)\}"\)

    

    \# Итоговый статус

    print\(f"\\n📋 ИТОГОВЫЙ СТАТУС:"\)

    print\(f"  • Nmap: \{'✅ ДОСТУПЕН' if scanner\.nmap\_available else '❌ НЕ НАЙДЕН'\}"\)

    print\(f"  • VulnDB: \{'✅ НАСТРОЕН' if scanner\.vulndb\_configured else '⚠️ НЕ НАСТРОЕН'\}"\)

    print\(f"  • Ollama: \{'✅ ДОСТУПЕН' if analyzer\.available else '❌ НЕ ДОСТУПЕН'\}"\)

    

    if not scanner\.nmap\_available:

        print\("\\n⚠️ Для получения реальных данных об открытых портах:"\)

        print\("   1\. Скачайте Nmap: https://nmap\.org/download\.html"\)

        print\("   2\. Установите с опцией 'Add to PATH'"\)

        print\("   3\. Перезапустите PowerShell"\)

    

    if not scanner\.vulndb\_configured:

        print\("\\n⚠️ Для получения реальных CVE:"\)

        print\("   1\. Зарегистрируйтесь: https://vuldb\.com"\)

        print\("   2\. Создайте файл \.env с вашим API ключом"\)

    

    print\("\\n✨ Готовый продукт успешно завершил работу\!"\)

if \_\_name\_\_ == "\_\_main\_\_":

    try:

        main\(\)

    except KeyboardInterrupt:

        print\("\\n\\n⚠️ Сканирование прервано пользователем"\)

    except Exception as e:

        print\(f"\\n❌ Критическая ошибка: \{e\}"\)

        import traceback

        traceback\.print\_exc\(\)  
  
  
КОД НА ОСНОВЕ DSPy ДЛЯ СОЗДАНИЕ БОЛЕЕ ДЛИННОГО ПРОМПТА С УДОБНЫМИ ВОЗМОЖНОСТЯМИ ПАЙПЛАЙНА  
[https://gimal\-ai\.ru/blog/upravlenie\-promptami\-dlya\-llm\-s\-dspy/  
](https://gimal-ai.ru/blog/upravlenie-promptami-dlya-llm-s-dspy/)  
"""

УЛЬТИМАТИВНАЯ ВЕРСИЯ: Многостраничный отчет по модели угроз

\- Разбивка на 12 логических глав

\- Каждая глава генерируется отдельно \(не обрезается\)

\- Сборка в единый документ

\- Итоговый отчет 40\-60 страниц

"""

import dspy

import json

import os

from datetime import datetime

import glob

from typing import Dict, Any, List

import PyPDF2

import docx2txt

\# ========== НАСТРОЙКА DSPy ==========

print\("🔧 Настройка DSPy для многостраничного отчета\.\.\."\)

lm = dspy\.LM\(

    model="ollama/qwen2\.5\-coder:7b\-instruct\-q4\_K\_M",

    api\_base="http://localhost:11434",

    temperature=0\.3,

    max\_tokens=8000,  \# Для каждой главы достаточно

    num\_ctx=128000,    \# Максимальный контекст

    cache=False

\)

dspy\.settings\.configure\(lm=lm\)

print\("✅ DSPy настроен"\)

\# ========== КЛАСС ДЛЯ ЧТЕНИЯ ДОКУМЕНТОВ ==========

class CompanyDocumentReader:

    """Читает все документы из папки company\_docs"""

    

    def \_\_init\_\_\(self, docs\_path: str\):

        self\.docs\_path = docs\_path

        self\.documents = \[\]

        

    def read\_all\_documents\(self\) \-> List\[Dict\]:

        print\(f"\\n📂 Чтение документов из: \{self\.docs\_path\}"\)

        

        if not os\.path\.exists\(self\.docs\_path\):

            print\(f"❌ Папка не найдена: \{self\.docs\_path\}"\)

            return \[\]

        

        file\_patterns = \["\*\.txt", "\*\.pdf", "\*\.docx", "\*\.csv", "\*\.json", "\*\.md"\]

        all\_files = \[\]

        

        for pattern in file\_patterns:

            all\_files\.extend\(glob\.glob\(os\.path\.join\(self\.docs\_path, pattern\)\)\)

        

        print\(f"📄 Найдено файлов: \{len\(all\_files\)\}"\)

        

        documents = \[\]

        for file\_path in all\_files:

            print\(f"  📖 Чтение: \{os\.path\.basename\(file\_path\)\}"\)

            content = self\.read\_file\(file\_path\)

            

            if content and len\(content\.strip\(\)\) > 0:

                documents\.append\(\{

                    "file": os\.path\.basename\(file\_path\),

                    "content": content\[:3000\],  \# Увеличили для контекста

                    "type": os\.path\.splitext\(file\_path\)\[1\]

                \}\)

        

        print\(f"✅ Загружено документов: \{len\(documents\)\}"\)

        return documents

    

    def read\_file\(self, file\_path: str\) \-> str:

        ext = os\.path\.splitext\(file\_path\)\[1\]\.lower\(\)

        

        try:

            if ext == '\.txt' or ext == '\.md':

                with open\(file\_path, 'r', encoding='utf\-8'\) as f:

                    return f\.read\(\)

            

            elif ext == '\.pdf':

                text = \[\]

                with open\(file\_path, 'rb'\) as f:

                    pdf\_reader = PyPDF2\.PdfReader\(f\)

                    for page in pdf\_reader\.pages\[:10\]:  \# Больше страниц

                        text\.append\(page\.extract\_text\(\)\)

                return '\\n'\.join\(text\)

            

            elif ext == '\.docx':

                return docx2txt\.process\(file\_path\)

            

            elif ext == '\.json':

                with open\(file\_path, 'r', encoding='utf\-8'\) as f:

                    data = json\.load\(f\)

                return json\.dumps\(data, ensure\_ascii=False, indent=2\)\[:3000\]

            

        except Exception as e:

            print\(f"    ⚠️ Ошибка чтения \{file\_path\}: \{e\}"\)

            return ""

        

        return ""

\# ========== СИГНАТУРЫ ДЛЯ КАЖДОЙ ГЛАВЫ ==========

class Chapter1ExecutiveSummary\(dspy\.Signature\):

    """ГЛАВА 1: Исполнительное резюме \(для руководства\)"""

    company\_context = dspy\.InputField\(desc="Контекст компании"\)

    host\_summaries = dspy\.InputField\(desc="Краткие сводки по хостам"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 1: ИСПОЛНИТЕЛЬНОЕ РЕЗЮМЕ \(3\-4 страницы\)

    

    1\.1\. ВВЕДЕНИЕ

    \- Цель проведения анализа

    \- Методология оценки

    \- Период проведения

    \- Состав команды аналитиков

    

    1\.2\. КЛЮЧЕВЫЕ ВЫВОДЫ

    \- Общий уровень безопасности организации

    \- Топ\-5 критических рисков

    \- Наиболее уязвимые компоненты инфраструктуры

    \- Соответствие регуляторным требованиям

    

    1\.3\. ОСНОВНЫЕ РЕКОМЕНДАЦИИ

    \- Что требует немедленного внимания \(0\-30 дней\)

    \- Плановые улучшения \(1\-3 месяца\)

    \- Стратегические инициативы \(3\-12 месяцев\)

    

    1\.4\. ФИНАНСОВЫЕ ПОСЛЕДСТВИЯ

    \- Потенциальный ущерб от реализации рисков

    \- Оценка стоимости устранения уязвимостей

    \- ROI от внедрения мер защиты

    

    1\.5\. ЗАКЛЮЧЕНИЕ

    \- Общая оценка ситуации

    \- Следующие шаги

    """\)

class Chapter2CompanyProfile\(dspy\.Signature\):

    """ГЛАВА 2: Детальный профиль компании"""

    documents = dspy\.InputField\(desc="Документы компании"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 2: ПРОФИЛЬ КОМПАНИИ \(4\-5 страниц\)

    

    2\.1\. ОБЩАЯ ИНФОРМАЦИЯ

    \- Полное наименование и организационная структура

    \- История создания и развития

    \- Миссия, видение, стратегические цели

    \- Ключевые показатели деятельности

    

    2\.2\. БИЗНЕС\-МОДЕЛЬ

    \- Основные продукты и услуги

    \- Бизнес\-процессы \(детально\)

    \- Клиенты и партнеры

    \- Каналы монетизации

    

    2\.3\. ОРГАНИЗАЦИОННАЯ СТРУКТУРА

    \- Организационная диаграмма

    \- Ключевые роли и ответственность

    \- Численность сотрудников по отделам

    \- География присутствия

    

    2\.4\. ИТ\-ЛАНДШАФТ

    \- Информационные системы \(перечень\)

    \- Сетевая инфраструктура

    \- Используемые технологии

    \- Облачные сервисы и провайдеры

    

    2\.5\. ДАННЫЕ И ИНФОРМАЦИЯ

    \- Классификация данных по критичности

    \- Места хранения данных

    \- Потоки данных \(схемы\)

    \- Требования к защите данных

    

    2\.6\. РЕГУЛЯТОРНОЕ ПОЛЕ

    \- Применимые законы и стандарты

    \- Лицензии и разрешения

    \- Требования к отчетности

    \- Штрафные санкции

    """\)

class Chapter3AdversaryModel\(dspy\.Signature\):

    """ГЛАВА 3: Детальная модель нарушителя"""

    company\_context = dspy\.InputField\(desc="Контекст компании"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 3: МОДЕЛЬ НАРУШИТЕЛЯ \(5\-6 страниц\)

    

    3\.1\. ТАКСОНОМИЯ НАРУШИТЕЛЕЙ

    

    3\.1\.1\. ВНЕШНИЕ НАРУШИТЕЛИ

    \- Хакеры\-одиночки \(мотивация, навыки, ресурсы, цели\)

    \- Организованные группы \(известные группировки, TTPs\)

    \- Конкуренты \(рыночная разведка, промышленный шпионаж\)

    \- Хактивисты \(политические/социальные мотивы\)

    \- Киберпреступники \(финансовая выгода\)

    \- Государственные акторы \(APT\-группы\)

    

    3\.1\.2\. ВНУТРЕННИЕ НАРУШИТЕЛИ

    \- Недовольные сотрудники \(месть, выгода\)

    \- Халатные сотрудники \(ошибки, невнимательность\)

    \- Привилегированные пользователи \(администраторы\)

    \- Бывшие сотрудники \(сохраненный доступ\)

    \- Инсайдеры по принуждению

    

    3\.1\.3\. ПАРТНЕРЫ И ПОДРЯДЧИКИ

    \- Внешние разработчики

    \- Обслуживающий персонал

    \- Поставщики облачных услуг

    \- Консультанты и аудиторы

    

    3\.2\. МАТРИЦА НАРУШИТЕЛЕЙ

    \- Таблица с оценкой вероятности и потенциала

    \- Приоритезация по уровню угрозы

    \- Специфические сценарии для компании

    

    3\.3\. MITRE ATT&CK MAPPING

    \- Тактики разведки \(Reconnaissance\)

    \- Тактики первоначального доступа

    \- Тактики выполнения кода

    \- Тактики закрепления \(Persistence\)

    \- Тактики повышения привилегий

    \- Тактики уклонения от защиты

    \- Тактики доступа к данным

    \- Тактики сбора данных

    \- Тактики эксфильтрации

    

    3\.4\. КОЛИЧЕСТВЕННЫЙ АНАЛИЗ РИСКОВ

    \- Годовая ожидаемая частота атак

    \- Средний ущерб от реализации

    \- Ожидаемый годовой ущерб

    \- Вероятностное распределение

    """\)

class Chapter4TechnicalAnalysis\(dspy\.Signature\):

    """ГЛАВА 4: Технический анализ инфраструктуры"""

    scan\_files = dspy\.InputField\(desc="Все файлы сканирования"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 4: ТЕХНИЧЕСКИЙ АНАЛИЗ ИНФРАСТРУКТУРЫ \(6\-8 страниц\)

    

    4\.1\. ОБЩАЯ СТАТИСТИКА

    \- Количество проанализированных хостов

    \- Распределение по типам систем

    \- Обнаруженные операционные системы

    \- Сетевые сегменты

    

    4\.2\. АНАЛИЗ ОТКРЫТЫХ ПОРТОВ

    \- Топ\-10 наиболее часто встречающихся портов

    \- Распределение по протоколам \(TCP/UDP\)

    \- Нестандартные порты

    \- Скрытые сервисы

    

    4\.3\. АНАЛИЗ СЕТЕВЫХ СЕРВИСОВ

    \- Веб\-серверы \(Apache, Nginx, IIS\)

    \- Почтовые сервисы \(SMTP, POP3, IMAP\)

    \- Файловые сервисы \(FTP, SMB, NFS\)

    \- Службы каталогов \(LDAP, Kerberos\)

    \- Базы данных \(MySQL, PostgreSQL, MSSQL\)

    \- Удаленный доступ \(SSH, RDP, Telnet\)

    \- DNS\-серверы

    \- Прокси и балансировщики

    

    4\.4\. АНАЛИЗ УЯЗВИМОСТЕЙ

    \- Критические уязвимости \(CVSS 9\.0\-10\.0\)

    \- Высокие уязвимости \(CVSS 7\.0\-8\.9\)

    \- Средние уязвимости \(CVSS 4\.0\-6\.9\)

    \- Низкие уязвимости \(CVSS 0\-3\.9\)

    \- CVE с публичными эксплойтами

    \- Уязвимости без патчей

    

    4\.5\. АНАЛИЗ КОНФИГУРАЦИЙ

    \- Небезопасные настройки

    \- Слабые протоколы шифрования

    \- Устаревшее ПО

    \- Отсутствие обновлений

    \- Дефолтные учетные данные

    

    4\.6\. ТРЕНДЫ И ЗАКОНОМЕРНОСТИ

    \- Повторяющиеся проблемы

    \- Системные недостатки

    \- Архитектурные уязвимости

    """\)

class Chapter5HostAnalysis\(dspy\.Signature\):

    """ГЛАВА 5: Детальный анализ хостов"""

    scan\_data = dspy\.InputField\(desc="Данные конкретного хоста"\)

    host\_index = dspy\.InputField\(desc="Номер хоста"\)

    total\_hosts = dspy\.InputField\(desc="Всего хостов"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ \{host\_index\} ИЗ \{total\_hosts\}: АНАЛИЗ ХОСТА \(3\-4 страницы на хост\)

    

    5\.\{host\_index\}\.1\. ОБЩАЯ ИНФОРМАЦИЯ

    \- IP\-адрес и сетевое расположение

    \- Роль в инфраструктуре

    \- Операционная система

    \- Владелец и ответственные

    \- Бизнес\-функция

    

    5\.\{host\_index\}\.2\. ОТКРЫТЫЕ ПОРТЫ И СЕРВИСЫ

    \- Полный список портов

    \- Версии сервисов

    \- Конфигурация сервисов

    \- Зависимости

    

    5\.\{host\_index\}\.3\. ОБНАРУЖЕННЫЕ УЯЗВИМОСТИ

    \- Критические \(с детальным описанием\)

    \- Высокие \(с детальным описанием\)

    \- Средние \(с детальным описанием\)

    \- Доступные эксплойты

    \- Векторы атак

    

    5\.\{host\_index\}\.4\. РИСКИ ДЛЯ БИЗНЕСА

    \- Влияние на конфиденциальность

    \- Влияние на целостность

    \- Влияние на доступность

    \- Потенциальный ущерб

    \- Вероятность реализации

    

    5\.\{host\_index\}\.5\. РЕКОМЕНДАЦИИ

    \- Немедленные действия \(0\-30 дней\)

    \- Плановые улучшения \(1\-3 месяца\)

    \- Стратегические меры \(3\-12 месяцев\)

    \- Приоритеты

    \- Ответственные

    """\)

class Chapter6ThreatScenarios\(dspy\.Signature\):

    """ГЛАВА 6: Сценарии атак"""

    company\_context = dspy\.InputField\(desc="Контекст компании"\)

    host\_analyses = dspy\.InputField\(desc="Анализы всех хостов"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 6: СЦЕНАРИИ АТАК \(5\-6 страниц\)

    

    6\.1\. МЕТОДОЛОГИЯ ПОСТРОЕНИЯ СЦЕНАРИЕВ

    \- Используемые фреймворки \(MITRE ATT&CK\)

    \- Источники данных

    \- Допущения

    

    6\.2\. СЦЕНАРИЙ 1: КОМПРОМЕТАЦИЯ ВНЕШНЕГО ПЕРИМЕТРА

    \- Цель атаки

    \- Нарушитель \(из главы 3\)

    \- Цепочка атак \(пошагово\)

    \- Используемые уязвимости

    \- Время реализации

    \- Признаки атаки

    \- Потенциальный ущерб

    \- Вероятность

    

    6\.3\. СЦЕНАРИЙ 2: АТАКА ЧЕРЕЗ ФИШИНГ

    \- Детальное описание

    \- Векторы социальной инженерии

    \- Пост\-эксплуатация

    \- Lateral movement

    \- Достижение целей

    

    6\.4\. СЦЕНАРИЙ 3: ИНСАЙДЕРСКАЯ АТАКА

    \- Тип инсайдера

    \- Мотивация

    \- Используемый доступ

    \- Признаки

    \- Последствия

    

    6\.5\. СЦЕНАРИЙ 4: АТАКА НА ЦЕПОЧКУ ПОСТАВОК

    \- Векторы через партнеров

    \- Компрометация ПО

    \- Каскадные эффекты

    

    6\.6\. СЦЕНАРИЙ 5: ЦЕЛЕВАЯ АТАКА \(APT\)

    \- Характеристики APT

    \- Многоэтапная атака

    \- Скрытность

    \- Долгосрочное присутствие

    

    6\.7\. МАТРИЦА СЦЕНАРИЕВ

    \- Сравнительный анализ

    \- Приоритеты реагирования

    \- Рекомендации по мониторингу

    """\)

class Chapter7RiskAnalysis\(dspy\.Signature\):

    """ГЛАВА 7: Количественный и качественный анализ рисков"""

    all\_data = dspy\.InputField\(desc="Все данные анализа"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 7: АНАЛИЗ РИСКОВ \(4\-5 страниц\)

    

    7\.1\. МЕТОДОЛОГИЯ ОЦЕНКИ РИСКОВ

    \- Используемые стандарты \(ISO 31000, NIST\)

    \- Шкалы оценки

    \- Критерии приемлемости

    

    7\.2\. КАЧЕСТВЕННАЯ ОЦЕНКА

    \- Матрица рисков \(вероятность x воздействие\)

    \- Тепловая карта рисков

    \- Категоризация по критичности

    

    7\.3\. КОЛИЧЕСТВЕННАЯ ОЦЕНКА

    \- Ожидаемый годовой ущерб \(ALE\)

    \- Единичный ожидаемый ущерб \(SLE\)

    \- Годовая частота событий \(ARO\)

    \- Стоимость снижения рисков

    \- ROI защитных мер

    

    7\.4\. ТОП\-10 КРИТИЧЕСКИХ РИСКОВ

    \- Детальное описание каждого

    \- Оценка \(вероятность, воздействие\)

    \- Владелец риска

    \- Существующие контрмеры

    \- Остаточный риск

    

    7\.5\. ПРИОРИТИЗАЦИЯ

    \- Ранжирование по критичности

    \- Срочность реагирования

    \- Ресурсоемкость устранения

    \- Бизнес\-приоритеты

    """\)

class Chapter8Controls\(dspy\.Signature\):

    """ГЛАВА 8: Рекомендации по контрмерам"""

    risks = dspy\.InputField\(desc="Оцененные риски"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 8: КОНТРМЕРЫ И РЕКОМЕНДАЦИИ \(5\-6 страниц\)

    

    8\.1\. ТЕХНИЧЕСКИЕ КОНТРМЕРЫ

    \- Сетевая безопасность \(firewalls, IDS/IPS\)

    \- Защита конечных точек \(EDR, антивирусы\)

    \- Управление доступом \(IAM, MFA\)

    \- Шифрование данных

    \- Безопасность приложений \(WAF\)

    \- Мониторинг и логирование \(SIEM\)

    \- Резервное копирование

    

    8\.2\. ОРГАНИЗАЦИОННЫЕ МЕРЫ

    \- Политики и процедуры

    \- Обучение персонала

    \- Управление инцидентами

    \- Оценка поставщиков

    \- Аудиты и проверки

    

    8\.3\. НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ \(0\-30 ДНЕЙ\)

    \- Критические патчи

    \- Отключение опасных сервисов

    \- Сброс паролей

    \- Блокировка доступа

    \- Приоритет 1

    

    8\.4\. КРАТКОСРОЧНЫЕ МЕРЫ \(1\-3 МЕСЯЦА\)

    \- Плановые обновления

    \- Усиление конфигураций

    \- Внедрение мониторинга

    \- Обучение ключевых сотрудников

    \- Приоритет 2

    

    8\.5\. ДОЛГОСРОЧНАЯ СТРАТЕГИЯ \(3\-12 МЕСЯЦЕВ\)

    \- Архитектурные изменения

    \- Внедрение новых систем

    \- Построение SOC

    \- Развитие компетенций

    \- Бюджетное планирование

    

    8\.6\. КАРТА КОНТРОЛЕЙ

    \- Связь угроза\-контрмера

    \- Ответственные

    \- Сроки

    \- Бюджет

    """\)

class Chapter9ResidualRisks\(dspy\.Signature\):

    """ГЛАВА 9: Остаточные риски"""

    controls = dspy\.InputField\(desc="Предложенные контрмеры"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 9: ОСТАТОЧНЫЕ РИСКИ \(2\-3 страницы\)

    

    9\.1\. ПРИНЯТЫЕ РИСКИ

    \- Какие риски не закрываются

    \- Обоснование \(экономическое/техническое\)

    \- Владелец риска

    \- Дата принятия решения

    

    9\.2\. РИСКИ ТРЕТЬИХ СТОРОН

    \- Зависимости от поставщиков

    \- Облачные провайдеры

    \- Аутсорсинг

    

    9\.3\. РЕГУЛЯТОРНЫЕ РИСКИ

    \- Несоответствие требованиям

    \- Штрафные санкции

    \- Репутационные потери

    

    9\.4\. ПЛАН МОНИТОРИНГА

    \- Ключевые индикаторы риска

    \- Периодичность пересмотра

    \- Триггеры эскалации

    \- Ответственные

    """\)

class Chapter10ImplementationPlan\(dspy\.Signature\):

    """ГЛАВА 10: План внедрения"""

    all\_recommendations = dspy\.InputField\(desc="Все рекомендации"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 10: ПЛАН ВНЕДРЕНИЯ \(3\-4 страницы\)

    

    10\.1\. ДОРОЖНАЯ КАРТА

    \- Фаза 1: Быстрые победы \(0\-30 дней\)

    \- Фаза 2: Тактические улучшения \(1\-3 месяца\)

    \- Фаза 3: Стратегические инициативы \(3\-12 месяцев\)

    \- Фаза 4: Постоянное совершенствование \(12\+ месяцев\)

    

    10\.2\. РЕСУРСНОЕ ПЛАНИРОВАНИЕ

    \- Требуемые специалисты

    \- Необходимое ПО и оборудование

    \- Бюджет по этапам

    \- Зависимости

    

    10\.3\. ГРАФИК РЕАЛИЗАЦИИ

    \- Детальный план\-график \(помесячно\)

    \- Контрольные точки \(milestones\)

    \- Критерии завершения этапов

    \- Ответственные

    

    10\.4\. УПРАВЛЕНИЕ ИЗМЕНЕНИЯМИ

    \- Коммуникационный план

    \- Обучение персонала

    \- Пилотное внедрение

    \- Обратная связь

    

    10\.5\. ОЦЕНКА ЭФФЕКТИВНОСТИ

    \- KPI и метрики

    \- Периодичность оценки

    \- Корректирующие действия

    """\)

class Chapter11Conclusion\(dspy\.Signature\):

    """ГЛАВА 11: Заключение и выводы"""

    summary = dspy\.InputField\(desc="Краткое резюме"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 11: ЗАКЛЮЧЕНИЕ \(2\-3 страницы\)

    

    11\.1\. ОСНОВНЫЕ ВЫВОДЫ

    \- Ключевые результаты анализа

    \- Наиболее критичные проблемы

    \- Общий уровень безопасности

    

    11\.2\. РЕКОМЕНДАЦИИ РУКОВОДСТВУ

    \- Стратегические решения

    \- Бюджетные приоритеты

    \- Организационные изменения

    

    11\.3\. СЛЕДУЮЩИЕ ШАГИ

    \- Что делать завтра

    \- Что делать на следующей неделе

    \- Что делать в следующем месяце

    

    11\.4\. ЗАКЛЮЧИТЕЛЬНОЕ СЛОВО

    \- Важность непрерывного улучшения

    \- Ответственность за безопасность

    \- Перспективы развития

    """\)

class Chapter12Appendices\(dspy\.Signature\):

    """ГЛАВА 12: Приложения"""

    all\_raw\_data = dspy\.InputField\(desc="Все сырые данные"\)

    

    chapter = dspy\.OutputField\(desc="""

    НАПИШИ ГЛАВУ 12: ПРИЛОЖЕНИЯ \(3\-4 страницы\)

    

    12\.1\. ГЛОССАРИЙ ТЕРМИНОВ

    \- Определения ключевых понятий

    \- Аббревиатуры и сокращения

    

    12\.2\. ПОЛНЫЙ СПИСОК ХОСТОВ

    \- Таблица со всеми хостами

    \- IP\-адреса

    \- Обнаруженные сервисы

    \- Уровень риска

    

    12\.3\. ПОЛНЫЙ СПИСОК УЯЗВИМОСТЕЙ

    \- Все CVE с описаниями

    \- CVSS баллы

    \- Затронутые хосты

    \- Статус патчей

    

    12\.4\. ССЫЛКИ НА ДОКУМЕНТАЦИЮ

    \- Использованные стандарты

    \- Внутренние политики

    \- Внешние источники

    

    12\.5\. ДАННЫЕ СКАНИРОВАНИЯ

    \- Ссылки на исходные JSON файлы

    \- Методология сбора данных

    \- Инструменты сканирования

    """\)

class AssembleFinalReport\(dspy\.Signature\):

    """Сборка финального отчета из всех глав"""

    chapter1 = dspy\.InputField\(desc="Глава 1: Исполнительное резюме"\)

    chapter2 = dspy\.InputField\(desc="Глава 2: Профиль компании"\)

    chapter3 = dspy\.InputField\(desc="Глава 3: Модель нарушителя"\)

    chapter4 = dspy\.InputField\(desc="Глава 4: Технический анализ"\)

    chapter5\_hosts = dspy\.InputField\(desc="Глава 5: Анализ хостов \(все вместе\)"\)

    chapter6 = dspy\.InputField\(desc="Глава 6: Сценарии атак"\)

    chapter7 = dspy\.InputField\(desc="Глава 7: Анализ рисков"\)

    chapter8 = dspy\.InputField\(desc="Глава 8: Контрмеры"\)

    chapter9 = dspy\.InputField\(desc="Глава 9: Остаточные риски"\)

    chapter10 = dspy\.InputField\(desc="Глава 10: План внедрения"\)

    chapter11 = dspy\.InputField\(desc="Глава 11: Заключение"\)

    chapter12 = dspy\.InputField\(desc="Глава 12: Приложения"\)

    

    final\_report = dspy\.OutputField\(desc="""

    СОБЕРИ ФИНАЛЬНЫЙ ОТЧЕТ ИЗ ВСЕХ ГЛАВ:

    

    1\. Сформируй титульный лист

    2\. Добавь оглавление

    3\. Вставь все главы по порядку

    4\. Добавь колонтитулы \(номер страницы, дата\)

    5\. Обеспечь единое форматирование

    

    Отчет должен быть готов к печати и представлению руководству\.

    """\)

\# ========== ОСНОВНОЙ МОДУЛЬ ==========

class UltimateThreatModeler\(dspy\.Module\):

    """Ультимативный модуль для создания 40\+ страничного отчета"""

    

    def \_\_init\_\_\(self\):

        super\(\)\.\_\_init\_\_\(\)

        

        \# Инициализируем все генераторы глав

        self\.chapter1 = dspy\.ChainOfThought\(Chapter1ExecutiveSummary\)

        self\.chapter2 = dspy\.ChainOfThought\(Chapter2CompanyProfile\)

        self\.chapter3 = dspy\.ChainOfThought\(Chapter3AdversaryModel\)

        self\.chapter4 = dspy\.ChainOfThought\(Chapter4TechnicalAnalysis\)

        self\.chapter5 = dspy\.ChainOfThought\(Chapter5HostAnalysis\)

        self\.chapter6 = dspy\.ChainOfThought\(Chapter6ThreatScenarios\)

        self\.chapter7 = dspy\.ChainOfThought\(Chapter7RiskAnalysis\)

        self\.chapter8 = dspy\.ChainOfThought\(Chapter8Controls\)

        self\.chapter9 = dspy\.ChainOfThought\(Chapter9ResidualRisks\)

        self\.chapter10 = dspy\.ChainOfThought\(Chapter10ImplementationPlan\)

        self\.chapter11 = dspy\.ChainOfThought\(Chapter11Conclusion\)

        self\.chapter12 = dspy\.ChainOfThought\(Chapter12Appendices\)

        self\.assembler = dspy\.ChainOfThought\(AssembleFinalReport\)

    

    def forward\(self, scan\_files: List\[str\], company\_docs: List\[Dict\]\):

        print\("\\n📚 ГЕНЕРАЦИЯ МНОГОСТРАНИЧНОГО ОТЧЕТА"\)

        print\("="\*80\)

        

        \# Подготавливаем контекст компании

        docs\_text = "\\n\\n\-\-\-\\n\\n"\.join\(\[

            f"Файл: \{doc\['file'\]\}\\n\{doc\['content'\]\}" 

            for doc in company\_docs\[:5\]

        \]\)

        

        \# Читаем все данные сканирования

        all\_scan\_data = \[\]

        for file\_path in scan\_files:

            with open\(file\_path, 'r', encoding='utf\-8'\) as f:

                all\_scan\_data\.append\(f\.read\(\)\)

        

        scan\_text = "\\n\\n\-\-\-\\n\\n"\.join\(all\_scan\_data\)

        

        \# ГЛАВА 1: Исполнительное резюме

        print\("\\n📄 Глава 1/12: Исполнительное резюме\.\.\."\)

        ch1 = self\.chapter1\(

            company\_context=docs\_text\[:3000\],

            host\_summaries=scan\_text\[:2000\]

        \)

        

        \# ГЛАВА 2: Профиль компании

        print\("📄 Глава 2/12: Профиль компании\.\.\."\)

        ch2 = self\.chapter2\(documents=docs\_text\[:4000\]\)

        

        \# ГЛАВА 3: Модель нарушителя

        print\("📄 Глава 3/12: Модель нарушителя\.\.\."\)

        ch3 = self\.chapter3\(company\_context=ch2\.chapter\[:2000\]\)

        

        \# ГЛАВА 4: Технический анализ

        print\("📄 Глава 4/12: Технический анализ\.\.\."\)

        ch4 = self\.chapter4\(scan\_files=scan\_text\[:4000\]\)

        

        \# ГЛАВА 5: Анализ хостов \(отдельно для каждого\)

        print\("📄 Глава 5/12: Анализ хостов\.\.\."\)

        host\_chapters = \[\]

        for i, file\_path in enumerate\(scan\_files, 1\):

            with open\(file\_path, 'r', encoding='utf\-8'\) as f:

                host\_data = f\.read\(\)

            

            print\(f"   Хост \{i\}/\{len\(scan\_files\)\}\.\.\."\)

            host\_ch = self\.chapter5\(

                scan\_data=host\_data,

                host\_index=str\(i\),

                total\_hosts=str\(len\(scan\_files\)\)

            \)

            host\_chapters\.append\(f"\\n\-\-\- ХОСТ \{i\} \-\-\-\\n\{host\_ch\.chapter\}"\)

        

        chapter5\_text = "\\n\\n"\.join\(host\_chapters\)

        

        \# ГЛАВА 6: Сценарии атак

        print\("📄 Глава 6/12: Сценарии атак\.\.\."\)

        ch6 = self\.chapter6\(

            company\_context=ch2\.chapter\[:2000\],

            host\_analyses=chapter5\_text\[:3000\]

        \)

        

        \# ГЛАВА 7: Анализ рисков

        print\("📄 Глава 7/12: Анализ рисков\.\.\."\)

        ch7 = self\.chapter7\(all\_data=f"\{ch4\.chapter\[:2000\]\}\\n\{ch6\.chapter\[:2000\]\}"\)

        

        \# ГЛАВА 8: Контрмеры

        print\("📄 Глава 8/12: Контрмеры\.\.\."\)

        ch8 = self\.chapter8\(risks=ch7\.chapter\[:2000\]\)

        

        \# ГЛАВА 9: Остаточные риски

        print\("📄 Глава 9/12: Остаточные риски\.\.\."\)

        ch9 = self\.chapter9\(controls=ch8\.chapter\[:2000\]\)

        

        \# ГЛАВА 10: План внедрения

        print\("📄 Глава 10/12: План внедрения\.\.\."\)

        ch10 = self\.chapter10\(all\_recommendations=f"\{ch8\.chapter\[:2000\]\}\\n\{ch9\.chapter\[:1000\]\}"\)

        

        \# ГЛАВА 11: Заключение

        print\("📄 Глава 11/12: Заключение\.\.\."\)

        ch11 = self\.chapter11\(summary=ch1\.chapter\[:1000\]\)

        

        \# ГЛАВА 12: Приложения

        print\("📄 Глава 12/12: Приложения\.\.\."\)

        ch12 = self\.chapter12\(all\_raw\_data=scan\_text\[:3000\]\)

        

        \# СБОРКА ФИНАЛЬНОГО ОТЧЕТА

        print\("\\n🔗 Сборка финального отчета\.\.\."\)

        final = self\.assembler\(

            chapter1=ch1\.chapter,

            chapter2=ch2\.chapter,

            chapter3=ch3\.chapter,

            chapter4=ch4\.chapter,

            chapter5\_hosts=chapter5\_text,

            chapter6=ch6\.chapter,

            chapter7=ch7\.chapter,

            chapter8=ch8\.chapter,

            chapter9=ch9\.chapter,

            chapter10=ch10\.chapter,

            chapter11=ch11\.chapter,

            chapter12=ch12\.chapter

        \)

        

        \# Сохраняем все главы для контроля

        all\_chapters = \{

            "chapter1": ch1\.chapter,

            "chapter2": ch2\.chapter,

            "chapter3": ch3\.chapter,

            "chapter4": ch4\.chapter,

            "chapter5": chapter5\_text,

            "chapter6": ch6\.chapter,

            "chapter7": ch7\.chapter,

            "chapter8": ch8\.chapter,

            "chapter9": ch9\.chapter,

            "chapter10": ch10\.chapter,

            "chapter11": ch11\.chapter,

            "chapter12": ch12\.chapter,

            "final": final\.final\_report

        \}

        

        return all\_chapters

\# ========== ФУНКЦИИ СОХРАНЕНИЯ ==========

def save\_ultimate\_report\(chapters: Dict, scan\_files: List\[str\]\):

    """Сохраняет все главы и финальный отчет"""

    results\_dir = "C:\\\\Working\\\\diplom\\\\Local\-Qdrant\-RAG\\\\mcp\_scn\_results"

    timestamp = datetime\.now\(\)\.strftime\("%Y%m%d\_%H%M%S"\)

    

    print\("\\n📁 СОХРАНЕНИЕ РЕЗУЛЬТАТОВ"\)

    print\("="\*80\)

    

    \# 1\. Сохраняем финальный отчет

    final\_file = os\.path\.join\(results\_dir, f"ULTIMATE\_THREAT\_REPORT\_\{timestamp\}\.txt"\)

    with open\(final\_file, 'w', encoding='utf\-8'\) as f:

        f\.write\(chapters\["final"\]\)

    

    size = os\.path\.getsize\(final\_file\) / 1024  \# в КБ

    pages = size / 3  \# примерно 3KB на страницу

    print\(f"✅ ФИНАЛЬНЫЙ ОТЧЕТ: \{os\.path\.basename\(final\_file\)\}"\)

    print\(f"   Размер: \{size:\.0f\} KB \(~\{pages:\.0f\} страниц\)"\)

    

    \# 2\. Сохраняем отдельные главы

    for i in range\(1, 13\):

        chapter\_key = f"chapter\{i\}"

        if chapter\_key in chapters:

            chapter\_file = os\.path\.join\(results\_dir, f"chapter\_\{i:02d\}\_\{timestamp\}\.txt"\)

            with open\(chapter\_file, 'w', encoding='utf\-8'\) as f:

                f\.write\(f"ГЛАВА \{i\}\\n"\)

                f\.write\("="\*80 \+ "\\n\\n"\)

                f\.write\(chapters\[chapter\_key\]\)

            print\(f"✅ Глава \{i\}: \{os\.path\.basename\(chapter\_file\)\}"\)

    

    \# 3\. Сохраняем JSON со всеми данными

    json\_file = os\.path\.join\(results\_dir, f"ultimate\_data\_\{timestamp\}\.json"\)

    with open\(json\_file, 'w', encoding='utf\-8'\) as f:

        json\.dump\(\{

            "timestamp": timestamp,

            "chapters": \{k: v\[:500\] \+ "\.\.\." for k, v in chapters\.items\(\)\},  \# Только начало

            "stats": \{

                "final\_report\_size\_kb": size,

                "estimated\_pages": pages

            \}

        \}, f, ensure\_ascii=False, indent=2\)

    

    return \{

        "final": final\_file,

        "pages": pages

    \}

\# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

def main\(\):

    print\("""

╔══════════════════════════════════════════════════════════════════════════╗

║   🔐 УЛЬТИМАТИВНОЕ МОДЕЛИРОВАНИЕ УГРОЗ v4\.0                            ║

║   • 12 детальных глав                                                  ║

║   • Каждая глава генерируется отдельно                                 ║

║   • Итоговый отчет 40\-60 страниц                                       ║

║   • Полная модель нарушителя и угроз                                   ║

╚══════════════════════════════════════════════════════════════════════════╝

    """\)

    

    \# Пути

    docs\_path = "C:\\\\Working\\\\diplom\\\\Local\-Qdrant\-RAG\\\\company\_docs"

    scans\_path = "C:\\\\Working\\\\diplom\\\\Local\-Qdrant\-RAG\\\\mcp\_scn\_results"

    

    \# Загрузка документов

    doc\_reader = CompanyDocumentReader\(docs\_path\)

    company\_docs = doc\_reader\.read\_all\_documents\(\)

    

    \# Поиск файлов сканирования

    scan\_files = glob\.glob\(os\.path\.join\(scans\_path, "scan\_\*\.json"\)\)

    scan\_files\.sort\(\)

    

    if not scan\_files:

        print\("❌ Нет файлов сканирования\!"\)

        return

    

    print\(f"\\n📋 ВСЕГО ХОСТОВ: \{len\(scan\_files\)\}"\)

    print\(f"📋 ДОКУМЕНТОВ: \{len\(company\_docs\)\}"\)

    print\(f"\\n▶️ Будет создано 12 глав, итоговый отчет ~\{len\(scan\_files\)\*5 \+ 20\} страниц"\)

    

    response = input\("\\n👉 Начать анализ? \(y/n\): "\)\.strip\(\)\.lower\(\)

    if response \!= 'y':

        print\("❌ Анализ отменен"\)

        return

    

    \# Запуск

    print\("\\n" \+ "="\*80\)

    print\("🚀 ЗАПУСК УЛЬТИМАТИВНОГО АНАЛИЗА"\)

    print\("="\*80\)

    print\("⏳ Это займет 10\-15 минут\.\.\."\)

    

    model = UltimateThreatModeler\(\)

    

    try:

        chapters = model\(scan\_files, company\_docs\)

        

        \# Сохранение

        saved = save\_ultimate\_report\(chapters, scan\_files\)

        

        print\("\\n" \+ "="\*80\)

        print\("✅ УЛЬТИМАТИВНЫЙ АНАЛИЗ ЗАВЕРШЕН"\)

        print\("="\*80\)

        print\(f"\\n📄 Финальный отчет: \{os\.path\.basename\(saved\['final'\]\)\}"\)

        print\(f"📊 Примерно \{saved\['pages'\]:\.0f\} страниц"\)

        print\(f"\\n📁 Все файлы в: \{scans\_path\}"\)

        

    except Exception as e:

        print\(f"\\n❌ Ошибка: \{e\}"\)

        import traceback

        traceback\.print\_exc\(\)

if \_\_name\_\_ == "\_\_main\_\_":

    try:

        main\(\)

    except KeyboardInterrupt:

        print\("\\n\\n⚠️ Прервано пользователем"\)

    except Exception as e:

        print\(f"\\n❌ Ошибка: \{e\}"\)

