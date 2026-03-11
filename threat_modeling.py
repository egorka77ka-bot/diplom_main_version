import os
import json
import glob
from datetime import datetime
from typing import Dict, Any, List
import PyPDF2
import docx2txt
import requests

# ПРАВИЛЬНЫЕ ИМПОРТЫ ДЛЯ LANGCHAIN 0.3.x
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.llms import Ollama
from langchain_core.runnables import RunnableSequence

class RAGClient:
    """Клиент для подключения к RAG серверу (rag_core.py)"""
    
    def __init__(self, server_url="http://localhost:8080"):
        self.server_url = server_url
        self.available = self._check_connection()
        if self.available:
            print("Подключение к серверу успешно.")
        else:
            print("Сервер не доступен (запустите rag_core.py).")
    
    def _check_connection(self):
        try:
            response = requests.get(f"{self.server_url}/?q=test", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_context(self, query, k=3):
        if not self.available:
            return ""
        try:
            response = requests.get(
                f"{self.server_url}/",
                params={"q": query, "k": k},
                timeout=5
            )
            if response.status_code == 200:
                results = response.json()
                parts = []
                for r in results:
                    parts.append(f"[Из документа: {r['source']}]\n{r['text']}")
                return "\n\n---\n\n".join(parts)
        except:
            pass
        return ""

llm = Ollama(
    model="qwen2.5-coder:7b-instruct-q4_K_M",
    base_url="http://localhost:11434",
    temperature=0.3,
    num_ctx=128000,
    num_predict=8000,
    verbose=False
)

print("LangChain настроен")
# Класс для чтения документов
class CompanyDocumentReader:
    
    def __init__(self, docs_path: str):
        self.docs_path = docs_path
        self.documents = []
        
    def read_all_documents(self) -> List[Dict]:
        print(f"\nЧтение документов из: {self.docs_path}")
        
        if not os.path.exists(self.docs_path):
            print(f"Папка не найдена: {self.docs_path}")
            return []
        # Типы файлов
        file_patterns = ["*.txt", "*.pdf", "*.docx", "*.csv", "*.json", "*.md"]
        all_files = []
        # Определение типов файлов
        for pattern in file_patterns:
            all_files.extend(glob.glob(os.path.join(self.docs_path, pattern)))
        
        print(f"Найдено файлов: {len(all_files)}")
        # Чтение, определение и загрузка документов
        documents = []
        for file_path in all_files:
            print(f"  Чтение: {os.path.basename(file_path)}")
            content = self.read_file(file_path)
            
            if content and len(content.strip()) > 0:
                documents.append({
                    "file": os.path.basename(file_path),
                    "content": content[:3000],
                    "type": os.path.splitext(file_path)[1]
                })
        
        print(f"Загружено документов: {len(documents)}")
        return documents
    # Функция чтение каждого типа файлов
    def read_file(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == '.txt' or ext == '.md':
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            elif ext == '.pdf':
                text = []
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    for page in pdf_reader.pages[:10]:
                        text.append(page.extract_text())
                return '\n'.join(text)
            
            elif ext == '.docx':
                return docx2txt.process(file_path)
            
            elif ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return json.dumps(data, ensure_ascii=False, indent=2)[:3000]
            
        except Exception as e:
            print(f" Ошибка чтения {file_path}: {e}")
            return ""
        
        return ""


# ========== ПРОМПТЫ ДЛЯ КАЖДОЙ ГЛАВЫ ==========

chapter1_prompt = PromptTemplate(
    input_variables=["company_context", "host_summaries"],
    template="""
    НАПИШИ ГЛАВУ 1:
    
    Контекст компании:
    {company_context}
       
    1. Сведения об основании, заказчике и целях работы

В этом разделе нужно указать:

Номер договора, технического задания, приказа или ссылка на требование регулятора (например, ФСТЭК, приказ о личной ответственности).

Кто заказчик: Полное наименование организации-владельца системы (или оператора).

Кто исполнитель: Название вашей компании (или ваше имя, если вы частный специалист).

Даты начала и окончания работ (тестирования).

Цели: (например: «оценка соответствия требованиям к защите информации», «проверка эффективности реализованных мер защиты», «подготовка к аттестации»).

Задачи: Что конкретно делали (провели инвентаризацию, выявили уязвимости, оценили риски).
    """
)

chapter2_prompt = PromptTemplate(
    input_variables=["documents"],
    template="""
    НАПИШИ ГЛАВУ 2:
    
    Документы компании:
    {documents}
    
    2. Информация об используемых средствах.

Нужно перечислить все программное обеспечение, которое применялось для анализа. Указывать лучше с версиями, чтобы можно было воспроизвести результаты.

Сканеры уязвимостей, например, MaxPatrol 8, RedCheck, XSpider.

Инструменты для пентеста: Nmap (версия), Burp Suite, Wireshark, Metasploit и т.д.

Собственные программные коды или средства: Если использовались, стоит указать их назначение (например: «скрипт для перебора паролей на протоколе SSH»).
    
    """
)

chapter3_prompt = PromptTemplate(
    input_variables=["company_context"],
    template="""
    НАПИШИ ГЛАВУ 3:
    
    Контекст компании:
    {company_context}
    
    3.Результаты сканирования сетей.

Это результат этапа разведки, где нужно показать, что вы обследовали. Например, такой перечень:

- Сетевые адреса - IP-адреса и имена хостов.

- Открытые порты и службы - примером может служить следующий вариант «На хосте 10.0.0.1 открыт 22 порт (SSH), 80 порт (HTTP)».

- Сетевые сервисы - DNS, DHCP, Web-серверы и т.д.

- Программное обеспечение - операционные системы, версии ПО, установленные приложения (CMS, СУБД и т.д.).
    """
)

chapter4_prompt = PromptTemplate(
    input_variables=["scan_files"],
    template="""
    НАПИШИ ГЛАВУ 4: 
    
    Данные сканирования:
    {scan_files}
    
    4. Краткое описание пентестинга
    Внешнее тестирование - что делали со стороны черного хакера.

    Внутреннее тестирование - что делали, находясь уже внутри сети, со стороны белого хакера.

    """
)

chapter5_prompt = PromptTemplate(
    input_variables=["scan_data", "host_index", "total_hosts"],
    template="""
    НАПИШИ ГЛАВУ 5:
    
    Данные хоста:
    {scan_data}

    Анализы хостов:
    {host_analyses}
    
    5. Перечень и описание найденных уязвимостей
    
Это самая большая часть. По каждой уязвимости нужно указать:

- Название уязвимости (например, «Использование устаревшей версии OpenSSL»).

- IP-адрес/хост и порт.

- Подробности об уязвимости (например: CVE-номер, подробное описание этого CVE).
    """
)

chapter6_prompt = PromptTemplate(
    input_variables=["company_context", "host_analyses"],
    template="""
    НАПИШИ ГЛАВУ 6:
    
    Контекст компании:
    {company_context}
    
    Анализы хостов:
    {host_analyses}
    
    6. Присвоение каждой найденной проблеме уровень опасности, используя шкалы CVSS: Критичная; Высокая; Средняя; Низкая.
    """
)

chapter7_prompt = PromptTemplate(
    input_variables=["all_data"],
    template="""
    НАПИШИ ГЛАВУ 7:
    
    Данные для анализа:
    {all_data}
    
    7. Перечень наиболее опасных уязвимостей (с обоснованием)

Здесь из общего списка (пункт д) выбираются самые опасные для бизнеса. 

Критерий выбора — возможность реализации конкретной атаки, которая приведет к негативным последствиям. 

Пример обоснования: «Уязвимость "Слабый пароль на RDP" подлежит устранению, так как позволяет злоумышленнику подобрать пароль, войти на сервер и украсть базу данных клиентов».
    """
)

chapter8_prompt = PromptTemplate(
    input_variables=["risks"],
    template="""
    НАПИШИ ГЛАВУ 8:
    
    Оцененные риски:
    {risks}
    
    8. Рекомендации по устранению уязвимостей

Нужно дать конкретные советы и рекомендации по устранению уязвимости. 

Например, можно сказать:

 - «Обновить версию Apache до 2.4.1»;

 - «Установить патч KB123456 от Microsoft»;

 - «Сменить пароль на сложный, настроить политику блокировки»;

 - «Закрыть порт 1433 на сетевом экране для доступа извне».
    """
)

chapter9_prompt = PromptTemplate(
    input_variables=["rag_context"],
    template="""
    НАПИШИ ГЛАВУ 9:
    
    
    9. Ограничения на действия исполнителя

Важный раздел для снятия ответственности. Если что-то пошло не так или что-то не проверили — причина может быть здесь. Нужно указать:

Запреты на работы и «запрещен перебор паролей на домен-контроллере».

Исключения - например, какие хосты или подсети не входили в зону тестирования (например: «биллинговая система не проверялась»).

Отсутствие доступа: Если заказчик не дал логин/пароль для сканирования или доступ к настройкам, это тоже ограничение.
    
    Данные компании:
    {rag_context}
    """
)



assemble_prompt = PromptTemplate(
    input_variables=["chapter1", "chapter2", "chapter3", "chapter4", "chapter5", 
                     "chapter6", "chapter7", "chapter8", "chapter9"],
    template="""
    СОБЕРИ ФИНАЛЬНЫЙ ОТЧЕТ ИЗ ВСЕХ ГЛАВ:
    
    ГЛАВА 1:
    {chapter1}
    
    ГЛАВА 2:
    {chapter2}
    
    ГЛАВА 3:
    {chapter3}
    
    ГЛАВА 4:
    {chapter4}
    
    ГЛАВА 5:
    {chapter5}
    
    ГЛАВА 6:
    {chapter6}
    
    ГЛАВА 7:
    {chapter7}
    
    ГЛАВА 8:
    {chapter8}
    
    ГЛАВА 9:
    {chapter9}
     
    ТРЕБОВАНИЯ К ФОРМАТИРОВАНИЮ:
    1. Сформируй титульный лист с названием отчета и датой
    2. Добавь оглавление
    3. Вставь все главы по порядку
    4. Добавь колонтитулы (номер страницы, дата)
    5. Обеспечь единое форматирование
    """
)

# В новых версиях LangChain используем pipe operator (|) вместо LLMChai
# Функция создания цепочки промптов
def create_chain(prompt):
    return prompt | llm | StrOutputParser()

# Создаем цепочки для каждой главы
chapter1_chain = create_chain(chapter1_prompt)
chapter2_chain = create_chain(chapter2_prompt)
chapter3_chain = create_chain(chapter3_prompt)
chapter4_chain = create_chain(chapter4_prompt)
chapter5_chain = create_chain(chapter5_prompt)
chapter6_chain = create_chain(chapter6_prompt)
chapter7_chain = create_chain(chapter7_prompt)
chapter8_chain = create_chain(chapter8_prompt)
chapter9_chain = create_chain(chapter9_prompt)
assemble_chain = create_chain(assemble_prompt)

# Написание модели угроз
def generate_threat_report(scan_files: List[str], company_docs: List[Dict], rag: RAGClient) -> Dict:
        
    print("\nСоздание модели угроз")
    rag_ctx_1 = rag.get_context(""" 1. Сведения об основании, заказчике и целях работы

В этом разделе нужно указать:

Номер договора, технического задания, приказа или ссылка на требование регулятора (например, ФСТЭК, приказ о личной ответственности).

Кто заказчик: Полное наименование организации-владельца системы (или оператора).

Кто исполнитель: Название вашей компании (или ваше имя, если вы частный специалист).

Даты начала и окончания работ (тестирования).

Цели: (например: «оценка соответствия требованиям к защите информации», «проверка эффективности реализованных мер защиты», «подготовка к аттестации»).

Задачи: Что конкретно делали (провели инвентаризацию, выявили уязвимости, оценили риски).
    """)
    rag_ctx_2 = rag.get_context("""2. Информация об используемых средствах.

Нужно перечислить все программное обеспечение, которое применялось для анализа. Указывать лучше с версиями, чтобы можно было воспроизвести результаты.

Сканеры уязвимостей, например, MaxPatrol 8, RedCheck, XSpider.

Инструменты для пентеста: Nmap (версия), Burp Suite, Wireshark, Metasploit и т.д.

Собственные программные коды или средства: Если использовались, стоит указать их назначение (например: «скрипт для перебора паролей на протоколе SSH»).
    
    """)
    rag_ctx_3 = rag.get_context("""3.Результаты сканирования сетей.

Это результат этапа разведки, где нужно показать, что вы обследовали. Например, такой перечень:

- Сетевые адреса - IP-адреса и имена хостов.

- Открытые порты и службы - примером может служить следующий вариант «На хосте 10.0.0.1 открыт 22 порт (SSH), 80 порт (HTTP)».

- Сетевые сервисы - DNS, DHCP, Web-серверы и т.д.

- Программное обеспечение - операционные системы, версии ПО, установленные приложения (CMS, СУБД и т.д.).
    """)
    rag_ctx_4 = rag.get_context(""" 4. Краткое описание пентестинга
    Внешнее тестирование - что делали со стороны черного хакера.

    Внутреннее тестирование - что делали, находясь уже внутри сети, со стороны белого хакера.

    """)
    rag_ctx_5 = rag.get_context("""5. Перечень и описание найденных уязвимостей
    
Это самая большая часть. По каждой уязвимости нужно указать:

- Название уязвимости (например, «Использование устаревшей версии OpenSSL»).

- IP-адрес/хост и порт.

- Подробности об уязвимости (например: CVE-номер, подробное описание этого CVE).
    """)
    rag_ctx_6 = rag.get_context("""6. Присвоение каждой найденной проблеме уровень опасности, используя шкалы CVSS: Критичная; Высокая; Средняя; Низкая.
    """)
    rag_ctx_7 = rag.get_context("""7. Перечень наиболее опасных уязвимостей (с обоснованием)

Здесь из общего списка (пункт д) выбираются самые опасные для бизнеса. 

Критерий выбора — возможность реализации конкретной атаки, которая приведет к негативным последствиям. 

Пример обоснования: «Уязвимость "Слабый пароль на RDP" подлежит устранению, так как позволяет злоумышленнику подобрать пароль, войти на сервер и украсть базу данных клиентов».
    """)
    rag_ctx_8 = rag.get_context(""" 8. Рекомендации по устранению уязвимостей

Нужно дать конкретные советы и рекомендации по устранению уязвимости. 

Например, можно сказать:

 - «Обновить версию Apache до 2.4.1»;

 - «Установить патч KB123456 от Microsoft»;

 - «Сменить пароль на сложный, настроить политику блокировки»;

 - «Закрыть порт 1433 на сетевом экране для доступа извне».
    """)
    rag_ctx_9 = rag.get_context("""9. Ограничения на действия исполнителя

Важный раздел для снятия ответственности. Если что-то пошло не так или что-то не проверили — причина может быть здесь. Нужно указать:

Запреты на работы и «запрещен перебор паролей на домен-контроллере».

Исключения - например, какие хосты или подсети не входили в зону тестирования (например: «биллинговая система не проверялась»).

Отсутствие доступа: Если заказчик не дал логин/пароль для сканирования или доступ к настройкам, это тоже ограничение.
    """)

    # Подготавливаем документы компании
    docs_text = "\n\n---\n\n".join([
        f"Файл: {doc['file']}\n{doc['content']}" 
        for doc in company_docs[:6]
    ])
    
    # Читаем все данные сканирования
    all_scan_data = []
    for file_path in scan_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            all_scan_data.append(f.read())
    
    scan_text = "\n\n---\n\n".join(all_scan_data)
    
    print("\nГлава 1: Сведения об основании, заказчике и целях работы")
    ch1 = chapter1_chain.invoke({
        "company_context": docs_text[:3000]
    })
    
    print("Глава 2: Информация об используемых средствах")
    ch2 = chapter2_chain.invoke({"documents": docs_text[:4000]})
    
    print("Глава 3: Результаты сканирования сетей")
    ch3 = chapter3_chain.invoke({"company_context": ch2[:2000]})
    
    print("Глава 4: Краткое описание пентестинга")
    ch4 = chapter4_chain.invoke({"scan_files": scan_text[:4000]})

    print("Глава 5: Перечень и описание найденных уязвимостей")
    ch5 = chapter5_chain.invoke({
        "company_context": docs_text[:3000],
        "vulnerabilities": scan_text[:2000]
    })

    print("Глава 6: Присвоение каждой найденной проблеме уровень опасности")
    ch6 = chapter6_chain.invoke({
        "company_context": ch2[:2000],
        "vulnerabilities": ch5[:3000]
    })
       
    print("Глава 7: Перечень наиболее опасных уязвимостей (с обоснованием)")
    ch7 = chapter7_chain.invoke({"all_data": f"{ch4[:2000]}\n{ch6[:2000]}"})
       
    print("Глава 8: Рекомендации по устранению уязвимостей")
    ch8 = chapter8_chain.invoke({"risks": ch7[:2000]})
        
    print("Глава 9: Ограничения на действия исполнителя")
    ch9 = chapter9_chain.invoke({"controls": ch8[:2000]})
         
    # итоговый отчет
    print("\nФинальный отчет...")
    final = assemble_chain.invoke({
        "chapter1": ch1,
        "chapter2": ch2,
        "chapter3": ch3,
        "chapter4": ch4,
        "chapter5": ch5,
        "chapter6": ch6,
        "chapter7": ch7,
        "chapter8": ch8,
        "chapter9": ch9,
    })
    print(f"Получено {len(final)} символов")
    
    # Сохраняем все главы 
    all_chapters = {
        "chapter1": ch1,
        "chapter2": ch2,
        "chapter3": ch3,
        "chapter4": ch4,
        "chapter5": ch5,
        "chapter6": ch6,
        "chapter7": ch7,
        "chapter8": ch8,
        "chapter9": ch9,
        "final": final
    }
    
    return all_chapters


# Сохранение все главы и финальный отчет
def save_report(chapters: Dict, scan_files: List[str]):
    results_dir = ".\model_results"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("\nСохранение результатов")
    
    # Сохраняем финальный отчет
    final_file = os.path.join(results_dir, f"THREAT_REPORT_{timestamp}.txt")
    with open(final_file, 'w', encoding='utf-8') as f:
        f.write(chapters["final"])
    
    size = os.path.getsize(final_file) / 1024
    pages = size / 3
    print(f"Итоговый отчет: {os.path.basename(final_file)}")
    print(f"Размер: {size:.0f} KB (~{pages:.0f} страниц)")
    
    # Сохраняем отдельные главы
    for i in range(1, 13):
        chapter_key = f"chapter{i}"
        if chapter_key in chapters:
            chapter_file = os.path.join(results_dir, f"chapter_{i:02d}_{timestamp}.txt")
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(f"Глава {i}\n")
                f.write(chapters[chapter_key])
            print(f"Глава {i}: {os.path.basename(chapter_file)}")
    
    # Сохраняем JSON со всеми данными
    json_file = os.path.join(results_dir, f"report_data_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": timestamp,
            "stats": {
                "final_report_size_kb": size,
                "estimated_pages": pages
            }
        }, f, ensure_ascii=False, indent=2)
    
    return {
        "final": final_file,
        "pages": pages
    }


# Реализация основной функции
def main():

    rag = RAGClient()
    # Пути хранения файлов
    docs_path = "./company_docs"
    scans_path = "./RAG/data"
    
    # Загрузка документов
    doc_reader = CompanyDocumentReader(docs_path)
    company_docs = doc_reader.read_all_documents()
    
    # Поиск файлов сканирования
    scan_files = glob.glob(os.path.join(scans_path, "scan_*.json"))
    scan_files.sort()
    
    if not scan_files:
        print("Файлы отсутствуют")
        return
    
    print(f"\nВсего хостов: {len(scan_files)}")
    print(f"Документоd: {len(company_docs)}")
    
    response = input("\nНачать анализ? (y/n): ").strip().lower()
    if response != 'y':
        print("Анализ отменен")
        return
    
    # Запуск
    print("Запуск анализа")
    print("Это займет 1-2 часа...")
    
    try:
        chapters = generate_threat_report(scan_files, company_docs)
        
        # Сохранение
        saved = save_report(chapters, scan_files)
        
        print("Анализ завершен")
        print(f"\nФинальный отчет: {os.path.basename(saved['final'])}")
        print(f"В документе содержится {saved['pages']:.0f} страниц")
        print(f"\nВсе файлы сохранены в папке по адресу: {scans_path}")
        
    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        print(f"\nОшибка: {e}")