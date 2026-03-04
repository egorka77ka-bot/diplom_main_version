import os
import json
import glob
from datetime import datetime
from typing import Dict, Any, List
import PyPDF2
import docx2txt

# ПРАВИЛЬНЫЕ ИМПОРТЫ ДЛЯ LANGCHAIN 0.3.x
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.llms import Ollama
from langchain_core.runnables import RunnableSequence

# ========== НАСТРОЙКА LANGCHAIN ==========
print("Настройка LangChain...")

llm = Ollama(
    model="qwen2.5-coder:7b-instruct-q4_K_M",
    base_url="http://localhost:11434",
    temperature=0.3,
    num_ctx=128000,
    num_predict=8000,
    verbose=False
)

print("LangChain настроен")

# ========== ЧТЕНИЕ ДОКУМЕНТОВ ==========
class CompanyDocumentReader:
    """Читает все документы из папки company_docs"""
    
    def __init__(self, docs_path: str):
        self.docs_path = docs_path
        self.documents = []
        
    def read_all_documents(self) -> List[Dict]:
        print(f"\nЧтение документов из: {self.docs_path}")
        
        if not os.path.exists(self.docs_path):
            print(f"Папка не найдена: {self.docs_path}")
            return []
        
        file_patterns = ["*.txt", "*.pdf", "*.docx", "*.csv", "*.json", "*.md"]
        all_files = []
        
        for pattern in file_patterns:
            all_files.extend(glob.glob(os.path.join(self.docs_path, pattern)))
        
        print(f"Найдено файлов: {len(all_files)}")
        
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
            print(f"    Ошибка чтения {file_path}: {e}")
            return ""
        
        return ""


# ========== ПРОМПТЫ ДЛЯ КАЖДОЙ ГЛАВЫ ==========

chapter1_prompt = PromptTemplate(
    input_variables=["company_context", "host_summaries"],
    template="""
    НАПИШИ ГЛАВУ 1: ИСПОЛНИТЕЛЬНОЕ РЕЗЮМЕ
    
    Контекст компании:
    {company_context}
    
    Сводки по хостам:
    {host_summaries}
    
    1.1. ВВЕДЕНИЕ
    - Цель проведения анализа
    
    1.2. КЛЮЧЕВЫЕ ВЫВОДЫ
    - Общий уровень безопасности организации
    - Наиболее уязвимые компоненты инфраструктуры
    - Соответствие регуляторным требованиям
    
    1.3. ОСНОВНЫЕ РЕКОМЕНДАЦИИ
    - Что требует экстренного решения
    - Плановые улучшения
    - Стратегическое развитие информационной безопасности компании
    
    1.4. ФИНАНСОВЫЕ ПОСЛЕДСТВИЯ
    - Потенциальный ущерб от реализации рисков
    - Оценка стоимости устранения уязвимостей
    - ROI от внедрения мер защиты
    
    1.5. ЗАКЛЮЧЕНИЕ
    - Общая оценка ситуации
    - Следующие шаги
    """
)

chapter2_prompt = PromptTemplate(
    input_variables=["documents"],
    template="""
    НАПИШИ ГЛАВУ 2: ПРОФИЛЬ КОМПАНИИ
    
    Документы компании:
    {documents}
    
    2.1. ОБЩАЯ ИНФОРМАЦИЯ
    - Полное наименование и организационная структура
    - Ключевые показатели деятельности
    
    2.2. БИЗНЕС-МОДЕЛЬ
    - Основные продукты и услуги
    - Бизнес-процессы (детально)
    - Клиенты и партнеры
    
    2.3. ОРГАНИЗАЦИОННАЯ СТРУКТУРА
    - Организационная структура
    - Ключевые роли и ответственность
    - Численность сотрудников по отделам
    
    2.4. IT инфраструктура
    - Информационные системы (перечень)
    - Сетевая инфраструктура
    - Используемые технологии
    - Облачные сервисы и провайдеры
    
    2.5. ДАННЫЕ И ИНФОРМАЦИЯ
    - Классификация данных по критичности
    - Места хранения данных
    - Требования к защите данных
    
    2.6. Правовое регулирование
    - Применимые законы и стандарты
    - Лицензии и разрешения
    """
)

chapter3_prompt = PromptTemplate(
    input_variables=["company_context"],
    template="""
    НАПИШИ ГЛАВУ 3: МОДЕЛЬ НАРУШИТЕЛЯ
    
    Контекст компании:
    {company_context}
    
    3.1. Модель НАРУШИТЕЛЯ
    
    3.1.1. ВНЕШНИЕ НАРУШИТЕЛИ
    - Мотивация, навыки, ресурсы, цели нарушителей
    - Организованные группы
    - Конкуренты (рыночная разведка, промышленный шпионаж)
    - Киберпреступники
    - Спецслужбы вражественных государств
    
    3.1.2. ВНУТРЕННИЕ НАРУШИТЕЛИ
    - Мотивация, навыки, ресурсы, цели нарушителей
    - Привилегированные пользователи
    - Бывшие сотрудники
    - Инсайдеры
    
    3.1.3. ПАРТНЕРЫ И ПОДРЯДЧИКИ
    - Внешние разработчики
    - Обслуживающий персонал
    - Провайдеры облачных ресурсов
    - Консультанты и аудиторы
    
    3.2. МАТРИЦА НАРУШИТЕЛЕЙ
    - Таблица с оценкой вероятности и потенциала
    - Приоритезация по уровню угрозы
    - Специфические сценарии для компании
    
    3.3. MITRE ATT&CK MAPPING
    - Всевозможные виды тактик применимых к данной системе
    
    3.4. КОЛИЧЕСТВЕННЫЙ АНАЛИЗ РИСКОВ
    - Годовая ожидаемая частота атак
    - Средний ущерб от реализации
    - Ожидаемый годовой ущерб
    - Вероятностное распределение
    """
)

chapter4_prompt = PromptTemplate(
    input_variables=["scan_files"],
    template="""
    НАПИШИ ГЛАВУ 4: ТЕХНИЧЕСКИЙ АНАЛИЗ ИНФРАСТРУКТУРЫ
    
    Данные сканирования:
    {scan_files}
    
    4.1. ОБЩАЯ СТАТИСТИКА
    - Количество проанализированных хостов
    - Распределение по типам систем
    - Обнаруженные операционные системы
    - Сетевые сегменты
    
    4.2. АНАЛИЗ ОТКРЫТЫХ ПОРТОВ
    - Список открытых портов
    - Виды протоколов
    - Нестандартные порты
    - Скрытые сервисы
    
    4.3. АНАЛИЗ СЕТЕВЫХ СЕРВИСОВ
    - Веб-серверы 
    - Почтовые сервисы 
    - Файловые сервисы 
    - Службы каталогов 
    - Базы данных 
    - Удаленный доступ 
    - DNS-серверы
    - Прокси и балансировщики
    
    4.4. АНАЛИЗ УЯЗВИМОСТЕЙ                  
    Есть ли и какие:                           
    - Критические уязвимости 
    - Высокие уязвимости 
    - Средние уязвимости 
    - Низкие уязвимости 
    - CVE с публичными эксплойтами
    - Уязвимости без патчей
    
    4.5. АНАЛИЗ КОНФИГУРАЦИЙ
    - Небезопасные настройки
    - Слабые протоколы шифрования
    - Устаревшее ПО
    - Отсутствие обновлений
    - Дефолтные учетные данные
    """
)

chapter5_prompt = PromptTemplate(
    input_variables=["scan_data", "host_index", "total_hosts"],
    template="""
    НАПИШИ ГЛАВУ {host_index} ИЗ {total_hosts}: АНАЛИЗ ХОСТА
    
    Данные хоста:
    {scan_data}
    
    5.{host_index}.1. ОБЩАЯ ИНФОРМАЦИЯ
    - IP-адрес и сетевое расположение
    - Роль в инфраструктуре
    - Операционная система
    - Владелец и ответственные
    - Бизнес-функция
    
    5.{host_index}.2. ОТКРЫТЫЕ ПОРТЫ И СЕРВИСЫ
    - Полный список портов
    - Версии сервисов
    - Конфигурация сервисов
      
    5.{host_index}.3. ОБНАРУЖЕННЫЕ УЯЗВИМОСТИ
    - Критические
    - Высокие
    - Средние 
    - Векторы атак
    
    5.{host_index}.4. РИСКИ ДЛЯ БИЗНЕСА
    - Потенциальный ущерб
    - Вероятность реализации
    
    5.{host_index}.5. РЕКОМЕНДАЦИИ
    - Немедленные действия 
    - Плановые улучшения 
    - Стратегические меры 
    - Приоритеты
    - Ответственные
    """
)

chapter6_prompt = PromptTemplate(
    input_variables=["company_context", "host_analyses"],
    template="""
    НАПИШИ ГЛАВУ 6: СЦЕНАРИИ АТАК
    
    Контекст компании:
    {company_context}
    
    Анализы хостов:
    {host_analyses}
    
    6.1. МЕТОДОЛОГИЯ ПОСТРОЕНИЯ СЦЕНАРИЕВ
    - Используемые методики
    - Источники данных
    - Допущения
    
    6.2. СЦЕНАРИЙ 1: КОМПРОМЕТАЦИЯ ВНЕШНЕГО ПЕРИМЕТРА
    - Цель атаки
    - Нарушитель
    - Цепочка атак
    - Используемые уязвимости
    - Время реализации
    - Признаки атаки
    - Потенциальный ущерб
    - Вероятность
    
    6.3. СЦЕНАРИЙ 2: АТАКА ЧЕРЕЗ ФИШИНГ
    - Цель атаки
    - Нарушитель
    - Цепочка атак
    - Используемые уязвимости
    - Время реализации
    - Признаки атаки
    - Потенциальный ущерб
    - Вероятность
    
    6.4. СЦЕНАРИЙ 3: ИНСАЙДЕР
    - Тип инсайдера
    - Мотивация
    - Используемый доступ
    - Признаки
    - Последствия
    
    6.5. СЦЕНАРИЙ 4: АТАКА НА ЦЕПОЧКУ ПОСТАВОК
    - Цель атаки
    - Нарушитель
    - Цепочка атак
    - Используемые уязвимости
    - Время реализации
    - Признаки атаки
    - Потенциальный ущерб
    - Вероятность
    """
)

chapter7_prompt = PromptTemplate(
    input_variables=["all_data"],
    template="""
    НАПИШИ ГЛАВУ 7: АНАЛИЗ РИСКОВ
    
    Данные для анализа:
    {all_data}
    
    7.1. МЕТОДОЛОГИЯ ОЦЕНКИ РИСКОВ
    - Используемые стандарты
    - Шкалы оценки
    - Критерии приемлемости
    
    7.2. КАЧЕСТВЕННАЯ ОЦЕНКА
    - Матрица рисков (вероятность x воздействие)
    - Тепловая карта рисков
    - Категоризация по критичности
          
    7.3. ТОП-10 КРИТИЧЕСКИХ РИСКОВ
    - Детальное описание каждого
    - Оценка (вероятность, воздействие)
    - Владелец риска
    - Существующие контрмеры
    - Остаточный риск
    
    7.4. ПРИОРИТИЗАЦИЯ
    - Ранжирование по критичности
    - Срочность реагирования
    - Ресурсоемкость устранения
    - Бизнес-приоритеты
    """
)

chapter8_prompt = PromptTemplate(
    input_variables=["risks"],
    template="""
    НАПИШИ ГЛАВУ 8: МЕРЫ И РЕКОМЕНДАЦИИ
    
    Оцененные риски:
    {risks}
    
    8.1. ТЕХНИЧЕСКИЕ КОНТРМЕРЫ
    - Сетевая безопасность (firewalls, IDS/IPS)
    - Защита конечных точек (EDR, антивирусы)
    - Управление доступом (IAM, MFA)
    - Шифрование
    - Мониторинг и логирование (SIEM)
    - Резервное копирование
    
    8.2. ОРГАНИЗАЦИОННЫЕ МЕРЫ
    - Политики и процедуры
    - Обучение персонала
    - Управление инцидентами
    - Оценка поставщиков
    - Аудиты и проверки
    
    8.3. НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ
    - Критические патчи
    - Отключение опасных сервисов
    - Сброс паролей
    - Блокировка доступа
    - Приоритет 1
    
    8.4. КРАТКОСРОЧНЫЕ МЕРЫ
    - Плановые обновления
    - Усиление конфигураций
    - Внедрение мониторинга
    - Обучение сотрудников
        
    8.5. ДОЛГОСРОЧНАЯ СТРАТЕГИЯ
    - Архитектурные изменения
    - Внедрение новых систем
    - Построение SOC
    - Развитие компетенций
    - Бюджетное планирование
    """
)

chapter9_prompt = PromptTemplate(
    input_variables=["controls"],
    template="""
    НАПИШИ ГЛАВУ 9: ОСТАТОЧНЫЕ РИСКИ
    
    Предложенные контрмеры:
    {controls}
    
    9.1. ПРИНЯТЫЕ РИСКИ
    - Какие риски не закрываются
    - Обоснование (экономическое/техническое)
    - Владелец риска
    - Дата принятия решения
    
    9.2. РИСКИ ПОДРЯДЧИКОВ
    - Зависимости от поставщиков
    - Облачные провайдеры
    - Аутсорсинг
    """
)

chapter10_prompt = PromptTemplate(
    input_variables=["all_recommendations"],
    template="""
    НАПИШИ ГЛАВУ 10: ПЛАН ВНЕДРЕНИЯ 
    
    Все рекомендации:
    {all_recommendations}
     
    10.1. РЕСУРСЫ
    - Требуемые специалисты
    - Необходимое ПО и оборудование
    - Бюджет по этапам
    - Зависимости
    
    10.2. ГРАФИК РЕАЛИЗАЦИИ
    - План-график
    - Критерии завершения этапов
    - Ответственные
    
    """
)

chapter11_prompt = PromptTemplate(
    input_variables=["summary"],
    template="""
    НАПИШИ ГЛАВУ 11: ЗАКЛЮЧЕНИЕ
    
    Краткое резюме:
    {summary}
    
    11.1. ОСНОВНЫЕ ВЫВОДЫ
    - Ключевые результаты анализа
    - Наиболее критичные проблемы
    - Общий уровень безопасности
    
    11.2. РЕКОМЕНДАЦИИ РУКОВОДСТВУ
    - Стратегические решения
    - Бюджетные приоритеты
    - Организационные изменения
    """
)

chapter12_prompt = PromptTemplate(
    input_variables=["all_raw_data"],
    template="""
    НАПИШИ ГЛАВУ 12: ПРИЛОЖЕНИЯ
    
    Сырые данные:
    {all_raw_data}
    
    12.1. ГЛОССАРИЙ ТЕРМИНОВ
    - Определения ключевых понятий
    - Аббревиатуры и сокращения
    
    12.2. ПОЛНЫЙ СПИСОК ХОСТОВ
    - Таблица со всеми хостами
    - IP-адреса
    - Обнаруженные сервисы
    - Уровень риска
    
    12.3. ПОЛНЫЙ СПИСОК УЯЗВИМОСТЕЙ
    - Все CVE с описаниями
    - CVSS баллы
    - Просканированные хосты
    - Версии ПО
    
    12.4. ССЫЛКИ НА ДОКУМЕНТАЦИЮ
    - Использованные стандарты
    - Законодательные акты
    - Методики
    - Внутренние политики
    - Внешние источники
    
    12.5. ДАННЫЕ СКАНИРОВАНИЯ
    - Ссылки на исходные JSON файлы
    - Методология сбора данных
    - Инструменты сканирования
    """
)

assemble_prompt = PromptTemplate(
    input_variables=["chapter1", "chapter2", "chapter3", "chapter4", "chapter5", 
                     "chapter6", "chapter7", "chapter8", "chapter9", "chapter10", "chapter11", "chapter12"],
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
    
    ГЛАВА 10:
    {chapter10}
    
    ГЛАВА 11:
    {chapter11}
    
    ГЛАВА 12:
    {chapter12}
    
    ТРЕБОВАНИЯ К ФОРМАТИРОВАНИЮ:
    1. Сформируй титульный лист с названием отчета и датой
    2. Добавь оглавление
    3. Вставь все главы по порядку
    4. Добавь колонтитулы (номер страницы, дата)
    5. Обеспечь единое форматирование
    """
)


# ========== СОЗДАНИЕ ЦЕПОЧЕК ==========
# В новых версиях LangChain используем pipe operator (|) вместо LLMChain

def create_chain(prompt):
    """Создает цепочку из промпта LLM"""
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
chapter10_chain = create_chain(chapter10_prompt)
chapter11_chain = create_chain(chapter11_prompt)
chapter12_chain = create_chain(chapter12_prompt)
assemble_chain = create_chain(assemble_prompt)


# ========== ГЕНЕРАЦИЯ ОТЧЕТА ==========
def generate_threat_report(scan_files: List[str], company_docs: List[Dict]) -> Dict:
        
    print("\nСОЗДАНИЕ МОДЕЛИ УГРОЗ")
    print("="*60)
    
    # Подготавливаем контекст компании
    docs_text = "\n\n---\n\n".join([
        f"Файл: {doc['file']}\n{doc['content']}" 
        for doc in company_docs[:5]
    ])
    
    # Читаем все данные сканирования
    all_scan_data = []
    for file_path in scan_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            all_scan_data.append(f.read())
    
    scan_text = "\n\n---\n\n".join(all_scan_data)
    
    # ГЛАВА 1: Исполнительное резюме
    print("\nГлава 1: Исполнительное резюме")
    ch1 = chapter1_chain.invoke({
        "company_context": docs_text[:3000],
        "host_summaries": scan_text[:2000]
    })
    print(f"   Получено {len(ch1)} символов")
    
    # ГЛАВА 2: Профиль компании
    print("Глава 2: Профиль компании")
    ch2 = chapter2_chain.invoke({"documents": docs_text[:4000]})
    print(f"   Получено {len(ch2)} символов")
    
    # ГЛАВА 3: Модель нарушителя
    print("Глава 3: Модель нарушителя")
    ch3 = chapter3_chain.invoke({"company_context": ch2[:2000]})
    print(f"   Получено {len(ch3)} символов")
    
    # ГЛАВА 4: Технический анализ
    print("Глава 4: Технический анализ")
    ch4 = chapter4_chain.invoke({"scan_files": scan_text[:4000]})
    print(f"   Получено {len(ch4)} символов")
    
    # ГЛАВА 5: Анализ хостов (отдельно для каждого)
    print("Глава 5: Анализ хостов")
    host_chapters = []
    for i, file_path in enumerate(scan_files, 1):
        with open(file_path, 'r', encoding='utf-8') as f:
            host_data = f.read()
        
        print(f"   Хост {i}/{len(scan_files)}...")
        host_ch = chapter5_chain.invoke({
            "scan_data": host_data,
            "host_index": str(i),
            "total_hosts": str(len(scan_files))
        })
        host_chapters.append(f"\n--- ХОСТ {i} ---\n{host_ch}")
        print(f"      Получено {len(host_ch)} символов")
    
    chapter5_text = "\n\n".join(host_chapters)
    
    # ГЛАВА 6: Сценарии атак
    print("Глава 6: Сценарии атак")
    ch6 = chapter6_chain.invoke({
        "company_context": ch2[:2000],
        "host_analyses": chapter5_text[:3000]
    })
       
    # ГЛАВА 7: Анализ рисков
    print("Глава 7: Анализ рисков")
    ch7 = chapter7_chain.invoke({"all_data": f"{ch4[:2000]}\n{ch6[:2000]}"})
       
    # ГЛАВА 8: Меры
    print("Глава 8: Меры")
    ch8 = chapter8_chain.invoke({"risks": ch7[:2000]})
        
    # ГЛАВА 9: Риски
    print("Глава 9: Риски")
    ch9 = chapter9_chain.invoke({"controls": ch8[:2000]})
        
    # ГЛАВА 10: План внедрения
    print("Глава 10: План внедрения")
    ch10 = chapter10_chain.invoke({"all_recommendations": f"{ch8[:2000]}\n{ch9[:1000]}"})
        
    # ГЛАВА 11: Заключение
    print("Глава 11: Заключение")
    ch11 = chapter11_chain.invoke({"summary": ch1[:1000]})
        
    # ГЛАВА 12: Приложения
    print("Глава 12: Приложения")
    ch12 = chapter12_chain.invoke({"all_raw_data": scan_text[:3000]})
        
    # Финальный отчет
    print("\nФинальный отчет...")
    final = assemble_chain.invoke({
        "chapter1": ch1,
        "chapter2": ch2,
        "chapter3": ch3,
        "chapter4": ch4,
        "chapter5": chapter5_text,
        "chapter6": ch6,
        "chapter7": ch7,
        "chapter8": ch8,
        "chapter9": ch9,
        "chapter10": ch10,
        "chapter11": ch11,
        "chapter12": ch12
    })
    print(f"   Получено {len(final)} символов")
    
    # Сохраняем все главы 
    all_chapters = {
        "chapter1": ch1,
        "chapter2": ch2,
        "chapter3": ch3,
        "chapter4": ch4,
        "chapter5": chapter5_text,
        "chapter6": ch6,
        "chapter7": ch7,
        "chapter8": ch8,
        "chapter9": ch9,
        "chapter10": ch10,
        "chapter11": ch11,
        "chapter12": ch12,
        "final": final
    }
    
    return all_chapters


# ========== СОХРАНЕНИЕ В ФАЙЛАХ ==========
def save_report(chapters: Dict, scan_files: List[str]):
    """Сохраняет все главы и финальный отчет"""
    results_dir = ".\model_results"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("\nСОХРАНЕНИЕ РЕЗУЛЬТАТОВ")
    print("="*60)
    
    # 1. Сохраняем финальный отчет
    final_file = os.path.join(results_dir, f"THREAT_REPORT_{timestamp}.txt")
    with open(final_file, 'w', encoding='utf-8') as f:
        f.write(chapters["final"])
    
    size = os.path.getsize(final_file) / 1024
    pages = size / 3
    print(f"ФИНАЛЬНЫЙ ОТЧЕТ: {os.path.basename(final_file)}")
    print(f"   Размер: {size:.0f} KB (~{pages:.0f} страниц)")
    
    # 2. Сохраняем отдельные главы
    for i in range(1, 13):
        chapter_key = f"chapter{i}"
        if chapter_key in chapters:
            chapter_file = os.path.join(results_dir, f"chapter_{i:02d}_{timestamp}.txt")
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(f"ГЛАВА {i}\n")
                f.write("="*80 + "\n\n")
                f.write(chapters[chapter_key])
            print(f"Глава {i}: {os.path.basename(chapter_file)}")
    
    # 3. Сохраняем JSON со всеми данными
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


# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    print("МОДЕЛь УГРОЗ ")
    
    # Пути хранения файлов
    docs_path = ".\data"
    scans_path = ".\data"
    
    # Загрузка документов
    doc_reader = CompanyDocumentReader(docs_path)
    company_docs = doc_reader.read_all_documents()
    
    # Поиск файлов сканирования
    scan_files = glob.glob(os.path.join(scans_path, "scan_*.json"))
    scan_files.sort()
    
    if not scan_files:
        print("Файлы отсутствуют")
        return
    
    print(f"\nВСЕГО ХОСТОВ: {len(scan_files)}")
    print(f"ДОКУМЕНТОВ: {len(company_docs)}")
    
    response = input("\nНачать анализ? (y/n): ").strip().lower()
    if response != 'y':
        print("Анализ отменен")
        return
    
    # Запуск
    print("\n" + "="*80)
    print("ЗАПУСК АНАЛИЗА")
    print("="*80)
    print("Это займет 10-15 минут...")
    
    try:
        chapters = generate_threat_report(scan_files, company_docs)
        
        # Сохранение
        saved = save_report(chapters, scan_files)
        
        print("\n" + "="*80)
        print("АНАЛИЗ ЗАВЕРШЕН")
        print("="*80)
        print(f"\nФинальный отчет: {os.path.basename(saved['final'])}")
        print(f"Примерно {saved['pages']:.0f} страниц")
        print(f"\nВсе файлы в: {scans_path}")
        
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