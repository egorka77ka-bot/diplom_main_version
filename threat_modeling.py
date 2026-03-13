import os
import json
import glob
from datetime import datetime
from typing import Dict, Any, List, Optional
import PyPDF2
import docx2txt
import requests
from pathlib import Path

# Класс для создания шаблонов промптов
from langchain_core.prompts import PromptTemplate
# Библиотека для преобразования ответа LLM в строку
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import OllamaLLM

# Пути к данным
RESULTS_DIR = "model_results"
COMPANY_DOCS_PATH = "./company_docs"
SCANS_PATH = ".\local-rag-mcp\src\docs"
RAG_SERVER_URL = "http://localhost:8080"

# Клиент для подключения к rag-серверу
class RAGClient:
        
    def __init__(self, server_url: str = RAG_SERVER_URL):
        self.server_url = server_url.rstrip('/')
        self.available = self._check_connection()
        if self.available:
            print("Подключение к RAG серверу успешно.")
        else:
            print("RAG сервер не доступен. Убедитесь, что local-rag-mcp запущен.")
            print("Запустите: cd local-rag-mcp/src && uvicorn main:app --host 0.0.0.0 --port 8000")
    
    # Проверка доступности RAG сервера
    def _check_connection(self) -> bool:
        try:
            
                    response = requests.get(
                        f"{self.server_url}", 
                        timeout=2
                    )
                    if response.status_code == 200:
                        return True
                
        except:
            return False
    
    
    # Получение данных из RAG
    def get_context(self, query: str, k: int = 3) -> str:
        if not self.available:
            return ""
        try:
            # Пробуем разные форматы запроса
            response = requests.get(
                f"{self.server_url}/",
                params={"q": query, "k": k},
                timeout=5
            )
            
            if response.status_code == 200:
                results = response.json()
                if isinstance(results, list) and results:
                    parts = []
                    for r in results:
                        source = r.get('source', r.get('file', 'unknown'))
                        text = r.get('text', r.get('content', ''))
                        parts.append(f"Из документа: {source}]\n{text}")
                    return "\n\n---\n\n".join(parts)
        except Exception as e:
            print(f" Ошибка при запросе к RAG: {e}")
        
        return ""


# Инициализация LLM с новой библиотекой
llm = OllamaLLM(
    model="qwen2.5-coder:7b-instruct-q4_K_M",
    base_url="http://localhost:11434",
    temperature=0.2,
    num_ctx=128000,
    num_predict=8000,
    # При выборе следующего слова рассматривать только 40 лучших вариантов
    # Отсекает маловероятные варианты
    top_k=40,
    # выбирает слова пока сумма вероятностей < 0.9
    top_p=0.9,
)
print("LangChain настроен")

class CompanyDocumentReader:
        
    SUPPORTED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.csv', '.json', '.md'}
    
    def __init__(self, docs_path: str):
        self.docs_path = docs_path
        
    def read_all_documents(self, max_docs : int = 50, max_size: int = 3000) -> List[Dict]:
        print(f"\nЧтение документов из: {self.docs_path}")
        
        if not os.path.exists(self.docs_path):
            print(f"Папка не найдена: {self.docs_path}")
            return []
        
        # Сбор файлов
        all_files = []
        for ext in self.SUPPORTED_EXTENSIONS:
            all_files.extend(glob.glob(os.path.join(self.docs_path, f"*{ext}")))
        
        print(f"Всего файлов: {len(all_files)}")
        
        # Чтение файлов
        documents = []
        for i, file_path in enumerate(all_files):
                            
            print(f"  Чтение: {os.path.basename(file_path)}")
            content = self._read_file(file_path)
            
            if content and len(content.strip()) > 0:
                # Ограничиваем размер
                if len(content) > max_size:
                    content = content[:max_size] + "\n..."
                
                documents.append({
                    "file": os.path.basename(file_path),
                    "content": content,
                    "type": os.path.splitext(file_path)[1].lower(),
                    "full_path": file_path
                })
        
        print(f"Всего загружено {len(documents)} документов.")
        return documents
    # Функция чтения файлов
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

chapter1_prompt = PromptTemplate(
    input_variables=["company_context", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 1 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

    1. Сведения об основании, заказчике и целях работы

В этом разделе нужно указать:

Номер договора, технического задания, приказа или ссылка на требование регулятора (например, ФСТЭК, приказ о личной ответственности).

Кто заказчик: Полное наименование организации-владельца системы (или оператора).

Кто исполнитель: Название вашей компании.

Даты начала и окончания работ.

Цели: (например: «оценка соответствия требованиям к защите информации», «проверка эффективности реализованных мер защиты», «подготовка к аттестации»).

Задачи: Что конкретно делали, например: провели инвентаризацию, выявили уязвимости, оценили риски.
    """
)

chapter2_prompt = PromptTemplate(
    input_variables=["documents", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 2 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

    2. Информация об используемых средствах.

Нужно перечислить все программное обеспечение, которое применялось для анализа. Указывать лучше с версиями, чтобы можно было воспроизвести результаты.

Сканеры уязвимостей, например, MaxPatrol 8, RedCheck, XSpider.

Инструменты для пентеста: Nmap с версией, Burp Suite, Wireshark, Metasploit и т.д.

Собственные программные коды или средства: Если использовались, стоит указать их назначение (например: «код для перебора паролей на протоколе SSH»).
    
    """
)

chapter3_prompt = PromptTemplate(
    input_variables=["scan_data", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 3 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

   Здесь нужно показать результат исследования системы. Например, такой перечень:

- Сетевые адреса - IP-адреса и имена хостов.

- Открытые порты и службы - примером может служить следующий вариант «На хосте 10.0.0.1 открыт 22 порт (SSH), 80 порт (HTTP)».

- Сетевые сервисы - DNS, DHCP, Web-серверы и т.д.

- Программное обеспечение - операционные системы, версии ПО, установленные приложения (CMS, СУБД и т.д.).
 
    """
)

chapter4_prompt = PromptTemplate(
    input_variables=["scan_data", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 4 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

    4. Краткое описание пентестинга
    Внешнее тестирование - что делали со стороны черного хакера.

    Внутреннее тестирование - что делали, находясь уже внутри сети, со стороны белого хакера.

    """
)

chapter5_prompt = PromptTemplate(
    input_variables=["scan_data", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 5 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

    5. Перечень и описание найденных уязвимостей
    Это самая большая часть. По каждой уязвимости нужно указать:

- Название уязвимости, CVE-номер.

- IP-адрес/хост и порт этой уязвимости.

- Описание этой уязвимости.

И так для каждой уязвимости делать такое описание.

    """
)

chapter6_prompt = PromptTemplate(
    input_variables=["vulnerabilities", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 6 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

     6. Присвоение каждой найденной проблеме уровень опасности, используя шкалы CVSS: Критичная; Высокая; Средняя; Низкая.
    """
)

chapter7_prompt = PromptTemplate(
    input_variables=["all_data", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 7 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

    7. Перечень наиболее опасных уязвимостей (с обоснованием)

Здесь из общего списка (Глава 6) выбираются самые опасные для бизнеса. 

Критерий выбора — возможность реализации конкретной атаки, которая приведет к негативным последствиям. 

Пример обоснования: «Уязвимость "Слабый пароль на RDP" подлежит устранению, так как позволяет злоумышленнику подобрать пароль, войти на сервер и украсть базу данных клиентов».
    """
)

chapter8_prompt = PromptTemplate(
    input_variables=["risks", "rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 8 отчета.

    Документы компании:
    {company_context}

    Информация из базы знаний:
    {rag_context}

    8. Рекомендации по устранению уязвимостей

Нужно дать конкретные советы и рекомендации по устранению уязвимости. 

Например, можно сказать:

 - «Обновить версию Apache до 2.4.1»;

 - «Установить новый патч от Microsoft»;

 - «Сменить пароль на сложный, настроить политику блокировки»;

 - «Закрыть порт № на сетевом экране для доступа извне».
    """
)

chapter9_prompt = PromptTemplate(
    input_variables=["rag_context"],
    template="""
    Ты эксперт по информационной безопасности. Напиши ГЛАВУ 9 отчета.

    Информация из базы знаний:
    {rag_context}

    9. Ограничения на действия исполнителя
    - Запреты ксающиеся проведения определенного вида работ
    - Исключения дл проведения работ
    - Отсутствие доступа к определенным ресурсам
    """
)

assemble_prompt = PromptTemplate(
    input_variables=["chapters"],
    template="""
    Ты эксперт по информационной безопасности. Составь финальный отчет из глав.

    ТРЕБОВАНИЯ:
    1. Создай титульный лист с названием "ОТЧЕТ ПО МОДЕЛИРОВАНИЮ УГРОЗ"
    2. Укажи дату: {date}
    3. Добавь оглавление
    4. Вставь все главы по порядку
    5. Добавь колонтитулы

    {chapters}
    """
)

def create_chain(prompt):
    return prompt | llm | StrOutputParser()

# Создаем цепочки
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

def generate_threat_report(scan_files: List[str], company_docs: List[Dict], rag: RAGClient) -> Dict:
    """Генерация отчета"""
    print("\nНачало генерации модели угроз")
    
    # Подготовка данных из документов компании
    docs_text = "\n\n---\n\n".join([
        f"Файл: {doc['file']}\n{doc['content']}" 
        for doc in company_docs[:1]
    ])
        
    # Получение RAG данных для каждой главы
    print("\nПолучение даных из RAG...")
    rag_ctx_1 = rag.get_context("договор заказчик цели работы техническое задание")
    rag_ctx_2 = rag.get_context("инструменты сканеры уязвимости nmap burp metasploit")
    rag_ctx_3 = rag.get_context("сеть ip адреса порты службы операционные системы")
    rag_ctx_4 = rag.get_context("пентест тестирование внешнее внутреннее методология")
    rag_ctx_5 = rag.get_context("уязвимости cve описание обнаружение")
    rag_ctx_6 = rag.get_context("cvss уровень опасности критичность")
    rag_ctx_7 = rag.get_context("критические уязвимости риски последствия")
    rag_ctx_8 = rag.get_context("рекомендации устранение патчи обновления")
    rag_ctx_9 = rag.get_context("ограничения запреты исключения доступ")
    
    # Генерация глав
    print("\nГлава 1: Основные сведения")
    ch1 = chapter1_chain.invoke({
        "company_context": docs_text,
        "rag_context": rag_ctx_1
    })
    
    print("Глава 2: Используемые средствах")
    ch2 = chapter2_chain.invoke({
        "company_context": docs_text,
        "rag_context": rag_ctx_2
    })
    
    print("Глава 3: Результаты сканирования сетей")
    ch3 = chapter3_chain.invoke({
        "company_context": docs_text,
        "rag_context": rag_ctx_3
    })
    
    print("Глава 4: Краткое описание пентестинга")
    ch4 = chapter4_chain.invoke({
        "company_context": docs_text,
        "rag_context": rag_ctx_4
    })
    
    print("Глава 5: Перечень и описание найденных уязвимостей")
    ch5 = chapter5_chain.invoke({
        "company_context": docs_text,
        "rag_context": rag_ctx_5
    })
    
    print("Глава 6: Присвоение уровня опасности")
    ch6 = chapter6_chain.invoke({
        "company_context": ch5[:],
        "rag_context": rag_ctx_6
    })
    
    print("Глава 7: Наиболее опасные уязвимости")
    ch7 = chapter7_chain.invoke({
        "company_context": f"{ch5[:]}\n{ch6[:]}",
        "rag_context": rag_ctx_7
    })
    
    print("Глава 8: Рекомендации по устранению")
    ch8 = chapter8_chain.invoke({
        "company_context": ch7[:],
        "rag_context": rag_ctx_8
    })
    
    print("Глава 9: Ограничения на действия исполнителя")
    ch9 = chapter9_chain.invoke({
        "rag_context": rag_ctx_9
    })
    
    print("\nНаписание отчета")
    chapters_text = ""
    for i, ch in enumerate([ch1, ch2, ch3, ch4, ch5, ch6, ch7, ch8, ch9], 1):
        chapters_text += f"\n\nГлава {i}\n\n{ch}"
    
    final = assemble_chain.invoke({
        "chapters": chapters_text,
        "date": datetime.now().strftime("%d.%m.%Y")
    })
    
    print(f"Отчет сгенерирован!")
    
    return {
        "chapter1": ch1, "chapter2": ch2, "chapter3": ch3,
        "chapter4": ch4, "chapter5": ch5, "chapter6": ch6,
        "chapter7": ch7, "chapter8": ch8, "chapter9": ch9,
        "final": final
    }


def save_report(chapters: Dict, scan_files: List[str]) -> Dict:
    # Создаем директорию для результатов
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("\nСохранение результатов")
    
    # Сохраняем финальный отчет
    final_file = os.path.join(RESULTS_DIR, f"threat_report_{timestamp}.txt")
    with open(final_file, 'w', encoding='utf-8') as f:
        f.write(chapters["final"])
    
    size_kb = os.path.getsize(final_file) / 1024
    pages = size_kb / 3
    
    print(f"Итоговый отчет: {os.path.basename(final_file)}")
    print(f"Размер: {size_kb:.0f} KB (~{pages:.0f} страниц)")
    
    # Сохраняем главы
    chapters_dir = os.path.join(RESULTS_DIR, f"chapters_{timestamp}")
    os.makedirs(chapters_dir, exist_ok=True)
    
    for i in range(1, 10):
        chapter_key = f"chapter{i}"
        if chapter_key in chapters:
            chapter_file = os.path.join(chapters_dir, f"chapter_{i:02d}.txt")
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(chapters[chapter_key])
            print(f"Глава {i}: {os.path.basename(chapter_file)}")
    
    # Метаданные
    metadata = {
        "timestamp": timestamp,
        "final_report": final_file,
        "size_kb": size_kb,
        "pages": pages,
        "scan_files": [os.path.basename(f) for f in scan_files[:10]]
    }
    
    meta_file = os.path.join(RESULTS_DIR, f"metadata_{timestamp}.json")
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    return {
        "final": final_file,
        "pages": pages,
        "metadata": meta_file
    }

def main():
    # Проверка наличия RAG сервера
    rag = RAGClient()
    
    if not rag.available:
        print("\nRAG сервер не запущен!")
        print(f"Запустите его в другом окне терминала:")
        print(f"cd {os.path.abspath('local-rag-mcp/src')}")
        print(f"python main.py")
        print("\nПродолжить без RAG? (y/n): ")
        response = input().strip().lower()
        if response != 'y':
            print("Анализ отменен")
            return
    
    # Чтение документов компании
    reader = CompanyDocumentReader(COMPANY_DOCS_PATH)
    company_docs = reader.read_all_documents()
    
    # Поиск файлов сканирования
    scan_files = glob.glob(os.path.join(SCANS_PATH, "scan_*.json"))
    scan_files.sort()
    
    if not scan_files:
        print("Файлы сканирования не найдены")
        return
    
    print(f"\Найдено хостов: {len(scan_files)}")
    print(f"Документов компании: {len(company_docs)}")
    
    response = input("\nНачать анализ? (y/n): ").strip().lower()
    if response != 'y':
        print("Анализ отменен")
        return
    
    # Запуск   
    try:
        chapters = generate_threat_report(scan_files, company_docs, rag)
        
        # Сохранение
        saved = save_report(chapters, scan_files)
        
        print("Анализ завершен")
        print(f"\nФинальный отчет: {os.path.basename(saved['final'])}")
        print(f"Объем: {saved['pages']:.0f} страниц")
        print(f"\nВсе файлы сохранены в папке: {RESULTS_DIR}")
        
    except KeyboardInterrupt:
        print("\n\nАнализ прерван пользователем")
    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()