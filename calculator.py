"""
Модуль для расчета уровня критичности уязвимостей по Методике ФСТЭК от 30 июня 2025 г.
Версия: 1.0
"""

import os
import json
import glob
import time
import pickle
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import requests
from pathlib import Path

# Импорты LangChain
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import OllamaLLM

# ================ КОНФИГУРАЦИЯ ================

RESULTS_DIR = "model_results"
RAG_SERVER_URL = "http://localhost:8080"
CHUNKS_PATH = Path("local-rag-mcp/src/data/chunks_with_metadata.pkl")
SCANS_PATH = ".\\local-rag-mcp\\src\\docs"

os.makedirs(RESULTS_DIR, exist_ok=True)


# ================ КЛАСС ДЛЯ РАСЧЕТА УРОВНЯ КРИТИЧНОСТИ ================

class VulnerabilityCriticalityCalculator:
    """
    Расчет уровня критичности уязвимостей (V) по методике ФСТЭК от 30 июня 2025 г.
    Формула: V = I_cvss × I_infr × (I_at + I_imp)
    """
    
    def __init__(self):
        # Весовые коэффициенты из Таблицы 1 Методики
        self.weights = {
            'k': 0.5,   # Тип компонента
            'l': 0.2,   # Количество уязвимых компонентов
            'p': 0.3,   # Влияние на периметр
            'e': 1.0,   # Эксплуатация уязвимости
            'h': 1.0    # Последствия эксплуатации
        }
        
        # Значения показателей из Таблицы 1
        self.component_values = {
            'critical_processes': 1.1,      # Критические процессы, функции, полномочия
            'firewalls': 0.9,                # Межсетевые экраны
            'network_devices': 0.9,          # Сетевые устройства и шлюзы
            'telecom': 0.8,                  # Телекоммуникационное оборудование
            'servers': 0.7,                  # Серверы (центральные вычислительные узлы)
            'user_workstations': 0.5,        # Пользовательские устройства (АРМ)
            'storage': 0.4,                  # Системы хранения данных
            'other': 0.1                     # Другие компоненты
        }
        
        self.quantity_values = {
            'more_70': 1.0,                  # Более 70% компонентов
            '50_70': 0.8,                    # 50-70% компонентов
            '10_50': 0.6,                    # 10-50% компонентов
            'less_10': 0.5                   # Менее 10% компонентов
        }
        
        self.perimeter_values = {
            'internet_accessible': 1.1,      # Доступно из сети «Интернет»
            'not_internet_accessible': 0.6   # Недоступно из сети «Интернет»
        }
        
        self.exploit_values = {
            'exploited_in_attacks': 0.6,     # Эксплуатируется в реальных атаках
            'exploit_available': 0.3,        # Имеются сведения о наличии эксплойта
            'no_info': 0.1                   # Отсутствуют сведения
        }
        
        self.consequences_values = {
            'arbitrary_code_execution': 0.5,  # Выполнение произвольного кода
            'privilege_escalation': 0.5,      # Повышение привилегий
            'security_bypass': 0.4,           # Обход механизмов безопасности
            'code_injection': 0.34,           # Внедрение кода
            'loss_of_integrity': 0.3,         # Нарушение целостности данных
            'confidentiality_breach': 0.3,    # Получение конфиденциальной информации
            'dos': 0.26,                      # Отказ в обслуживании
            'overwrite_files': 0.22,          # Перезапись произвольных файлов
            'write_local_files': 0.2,         # Запись локальных файлов
            'read_local_files': 0.18,         # Чтение локальных файлов
            'spoof_ui': 0.12,                 # Поддельный пользовательский интерфейс
            'xss': 0.1                        # Межсайтовый скриптинг
        }
        
        self.vulnerabilities = []
    
    def add_vulnerability(self, cve_id: str, cvss_score: float, 
                          component_type: str, quantity: str,
                          perimeter_access: str, exploit_status: str,
                          consequences: List[str]):
        """
        Добавление уязвимости для расчета.
        
        Параметры:
        - cve_id: идентификатор CVE или BDU
        - cvss_score: базовая оценка CVSS (0-10)
        - component_type: тип компонента из component_values
        - quantity: количество уязвимых компонентов из quantity_values
        - perimeter_access: доступность из Интернет из perimeter_values
        - exploit_status: статус эксплуатации из exploit_values
        - consequences: список последствий из consequences_values
        """
        
        # Расчет I_infr = k×K + l×L + p×P (пункт 14 Методики)
        K = self.component_values.get(component_type, self.component_values['other'])
        L = self.quantity_values.get(quantity, self.quantity_values['less_10'])
        P = self.perimeter_values.get(perimeter_access, self.perimeter_values['not_internet_accessible'])
        
        I_infr = (self.weights['k'] * K) + (self.weights['l'] * L) + (self.weights['p'] * P)
        
        # Расчет I_at = e×E (пункт 16 Методики)
        E = self.exploit_values.get(exploit_status, self.exploit_values['no_info'])
        I_at = self.weights['e'] * E
        
        # Расчет I_imp = h×H (пункт 17 Методики)
        max_H = max([self.consequences_values.get(c, 0.1) for c in consequences]) if consequences else 0.1
        I_imp = self.weights['h'] * max_H
        
        # Расчет V = I_cvss × I_infr × (I_at + I_imp) (пункт 12 Методики)
        V = cvss_score * I_infr * (I_at + I_imp)
        
        # Определение уровня критичности по Таблице 2 (пункт 18 Методики)
        if V > 8.0:
            criticality_level = "КРИТИЧЕСКИЙ"
            recommended_time = "несколько часов (до 24 часов)"
        elif V >= 5.0:
            criticality_level = "ВЫСОКИЙ"
            recommended_time = "несколько дней (до 7 дней)"
        elif V >= 2.0:
            criticality_level = "СРЕДНИЙ"
            recommended_time = "несколько недель (до 4 недель)"
        else:
            criticality_level = "НИЗКИЙ"
            recommended_time = "несколько месяцев (до 4 месяцев)"
        
        vulnerability = {
            'cve_id': cve_id,
            'cvss_score': cvss_score,
            'I_infr': round(I_infr, 3),
            'I_at': round(I_at, 3),
            'I_imp': round(I_imp, 3),
            'V': round(V, 3),
            'criticality_level': criticality_level,
            'recommended_time': recommended_time
        }
        self.vulnerabilities.append(vulnerability)
        return vulnerability
    
    def get_summary(self) -> Dict:
        """Получение сводки по всем уязвимостям"""
        if not self.vulnerabilities:
            return {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'total': 0}
        
        summary = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for v in self.vulnerabilities:
            level = v['criticality_level']
            if level == "КРИТИЧЕСКИЙ":
                summary['critical'] += 1
            elif level == "ВЫСОКИЙ":
                summary['high'] += 1
            elif level == "СРЕДНИЙ":
                summary['medium'] += 1
            else:
                summary['low'] += 1
        summary['total'] = len(self.vulnerabilities)
        return summary
    
    def generate_calculation_details(self) -> str:
        """Генерация подробного описания расчетов для каждой уязвимости"""
        if not self.vulnerabilities:
            return "Уязвимости для расчета не найдены."
        
        details = []
        for i, v in enumerate(self.vulnerabilities, 1):
            detail = f"""
### Уязвимость {i}: {v['cve_id']}

**Исходные данные:**
- Базовая оценка CVSS (I_cvss): {v['cvss_score']:.1f}
- Показатель влияния на инфраструктуру (I_infr): {v['I_infr']:.3f}
- Показатель возможности эксплуатации (I_at): {v['I_at']:.3f}
- Показатель последствий эксплуатации (I_imp): {v['I_imp']:.3f}

**Расчет по формуле (пункт 12 Методики):**
V = I_cvss × I_infr × (I_at + I_imp)
V = {v['cvss_score']:.1f} × {v['I_infr']:.3f} × ({v['I_at']:.3f} + {v['I_imp']:.3f})
V = {v['cvss_score']:.1f} × {v['I_infr']:.3f} × {(v['I_at'] + v['I_imp']):.3f}
V = **{v['V']:.3f}**

**Результат оценки (Таблица 2 Методики):**
- Уровень критичности: **{v['criticality_level']}**
- Рекомендуемый срок устранения (пункт 21 Методики): {v['recommended_time']}
"""
            details.append(detail)
        
        return "\n".join(details)


# ================ КЛАСС ДЛЯ РАБОТЫ С RAG ================

class RAGClient:
    """Клиент для подключения к RAG-серверу."""
    
    def __init__(self, server_url: str = RAG_SERVER_URL):
        self.server_url = server_url.rstrip('/')
        self.available = self._check_connection()
        self.local_chunks = self._load_local_chunks()
        
        if self.available:
            print(f"Подключение к RAG серверу установлено: {self.server_url}")
        else:
            print(f"RAG сервер не доступен.")
            if self.local_chunks:
                print("Используются локальные чанки.")
            else:
                print("Для работы требуется запустить RAG сервер.")
    
    def _check_connection(self) -> bool:
        try:
            response = requests.get(f"{self.server_url}", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def _load_local_chunks(self):
        if CHUNKS_PATH.exists():
            try:
                with open(CHUNKS_PATH, "rb") as f:
                    chunks = pickle.load(f)
                print(f"Загружено локальных чанков: {len(chunks)}")
                return chunks
            except Exception as e:
                print(f"Ошибка загрузки локальных чанков: {e}")
        return None
    
    def _search_local(self, query: str, k: int = 5) -> List[Dict]:
        if not self.local_chunks:
            return []
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        scored = []
        for chunk in self.local_chunks:
            text = chunk.get('text', '').lower()
            metadata = chunk.get('metadata', {})
            
            score = sum(1 for word in query_words if word in text)
            
            filename = metadata.get('filename', '').lower()
            score += sum(3 for word in query_words if word in filename)
            
            source = chunk.get('source', '').lower()
            score += sum(2 for word in query_words if word in source)
            
            if score > 0:
                scored.append((score, chunk))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        return [chunk for _, chunk in scored[:k]]
    
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
    
    def get_context_with_metadata(self, query: str, k: int = 50) -> Tuple[str, List[Dict]]:
        results = []
        
        if self.available:
            try:
                response = requests.get(
                    f"{self.server_url}/query",
                    params={"q": query, "k": k},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
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
                print(f"Ошибка HTTP-запроса: {e}")
        
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
            
            metadata_str = f"[Источник: {filename}]"
            context_parts.append(f"{metadata_str}\n{text}")
            
            sources.append({
                "filename": filename,
                "source": source,
                "chunk_id": chunk_id,
                "chunk_total": chunk_total,
                "score": score,
                "text_preview": text[:200] + "..." if len(text) > 200 else text
            })
        
        return "\n\n---\n\n".join(context_parts), sources


# ================ ИНИЦИАЛИЗАЦИЯ LLM ================

print("Инициализация языковой модели...")
start_time = time.time()

llm = OllamaLLM(
    model="qwen3.5:4b-q8_0",
    base_url="http://localhost:11434",
    temperature=0.2,
    num_ctx=50000,
    num_predict=15000,
    top_k=70,
    top_p=0.9,
)

init_time = time.time() - start_time
print(f"Языковая модель инициализирована за {init_time:.2f} сек")


# ================ ФУНКЦИИ ДЛЯ РАСЧЕТА ================

def create_chain(prompt):
    """Создание цепочки LangChain"""
    return prompt | llm | StrOutputParser()


def parse_cve_from_scan_files(scan_files: List[str]) -> List[Dict]:
    """Извлечение CVE из файлов сканирования для расчета критичности"""
    cve_list = []
    
    for file_path in scan_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Ищем CVE в формате CVE-YYYY-NNNNN
                cve_pattern = r'CVE-\d{4}-\d{4,}'
                matches = re.findall(cve_pattern, content, re.IGNORECASE)
                
                for cve in matches:
                    cve_upper = cve.upper()
                    
                    # Проверяем, нет ли уже такой CVE
                    if any(c['id'] == cve_upper for c in cve_list):
                        continue
                    
                    # Пытаемся найти CVSS оценку рядом с CVE
                    cvss_score = 7.5  # Значение по умолчанию
                    cvss_pattern = r'CVSS[:\s]*(\d+\.?\d*)'
                    cvss_match = re.search(cvss_pattern, content, re.IGNORECASE)
                    if cvss_match:
                        try:
                            cvss_score = float(cvss_match.group(1))
                        except:
                            pass
                    
                    # Определяем тип компонента по контексту
                    component_type = 'servers'  # По умолчанию
                    if 'workstation' in content.lower() or 'арм' in content.lower():
                        component_type = 'user_workstations'
                    elif 'firewall' in content.lower() or 'межсетевой' in content.lower():
                        component_type = 'firewalls'
                    elif 'network' in content.lower() or 'сеть' in content.lower():
                        component_type = 'network_devices'
                    
                    # Определяем доступность из Интернет
                    perimeter_access = 'internet_accessible'
                    if 'internal' in content.lower() or 'внутренний' in content.lower():
                        perimeter_access = 'not_internet_accessible'
                    
                    # Определяем статус эксплуатации
                    exploit_status = 'no_info'
                    if 'exploit' in content.lower() or 'эксплойт' in content.lower():
                        exploit_status = 'exploit_available'
                    if 'attack' in content.lower() or 'атака' in content.lower():
                        exploit_status = 'exploited_in_attacks'
                    
                    # Определяем последствия
                    consequences = ['arbitrary_code_execution']
                    if 'privilege' in content.lower() or 'привилегий' in content.lower():
                        consequences = ['privilege_escalation']
                    elif 'dos' in content.lower() or 'отказ' in content.lower():
                        consequences = ['dos']
                    elif 'xss' in content.lower():
                        consequences = ['xss']
                    
                    cve_list.append({
                        'id': cve_upper,
                        'cvss': cvss_score,
                        'component_type': component_type,
                        'quantity': '10_50',
                        'perimeter': perimeter_access,
                        'exploit': exploit_status,
                        'consequences': consequences
                    })
        except Exception as e:
            print(f"Ошибка чтения файла {file_path}: {e}")
    
    return cve_list


# ================ ПРОМПТ ДЛЯ ГЕНЕРАЦИИ ОТЧЕТА ================

report_prompt = PromptTemplate(
    input_variables=["rag_context", "calculation_details", "vulnerability_assessment"],
    template="""Ты эксперт по информационной безопасности. Составь ОТЧЕТ по оценке уровня критичности уязвимостей в соответствии с Методикой ФСТЭК от 30 июня 2025 г.

Используй ТОЛЬКО данные предоставленные ниже:

Информация из базы знаний (RAG):
{rag_context}

Ниже приведены подробные расчеты уровня критичности каждой уязвимости:

{calculation_details}

И сводный раздел оценки:

{vulnerability_assessment}

СТРОГОЕ ПРАВИЛО ЦИТИРОВАНИЯ:
После КАЖДОГО факта, взятого из текста, ОБЯЗАТЕЛЬНО ставь маркер [Источник: имя_файла] точно так, как он указан в предоставленных данных.
НЕ придумывай свои маркеры - копируй их из текста выше!

Если в данных нет информации - напиши "Информация не предоставлена".

Составь полный отчет, который должен содержать:

1. ВВЕДЕНИЕ
   - Основание для проведения оценки (Методика ФСТЭК от 30.06.2025)
   - Цель оценки
   - Исходные данные об уязвимостях

2. МЕТОДИКА ОЦЕНКИ
   - Формула расчета V = I_cvss × I_infr × (I_at + I_imp)
   - Описание показателей I_cvss, I_infr, I_at, I_imp
   - Таблица весовых коэффициентов (k, l, p, e, h)
   - Таблица значений показателей (K, L, P, E, H)

3. РЕЗУЛЬТАТЫ РАСЧЕТА ДЛЯ КАЖДОЙ УЯЗВИМОСТИ
   - Для каждой уязвимости привести:
     * Идентификатор CVE/BDU
     * Исходные данные
     * Пошаговый расчет
     * Итоговое значение V
     * Присвоенный уровень критичности
     * Рекомендуемый срок устранения

4. СВОДНАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ
   | № | Идентификатор | CVSS | I_infr | I_at | I_imp | V | Уровень критичности | Срок устранения |

5. СТАТИСТИКА РАСПРЕДЕЛЕНИЯ
   - Количество уязвимостей по уровням критичности
   - Процентное соотношение

6. ЗАКЛЮЧЕНИЕ
   - Выводы по результатам оценки
   - Рекомендации по приоритизации устранения

Используй данные из предоставленных расчетов. Не выдумывай новые оценки и не изменяй рассчитанные значения V.
"""
)


# ================ ГЛАВНАЯ ФУНКЦИЯ ================

def main():
    print("=" * 70)
    print("РАСЧЕТ УРОВНЯ КРИТИЧНОСТИ УЯЗВИМОСТЕЙ")
    print("По методике ФСТЭК от 30 июня 2025 г.")
    print("=" * 70)
    
    program_start = time.time()
    
    # Подключение к RAG
    rag = RAGClient()
    
    if not rag.available and not rag.local_chunks:
        print("\nRAG сервер не запущен и нет локальных чанков!")
        print("Запустите RAG сервер: cd local-rag-mcp/src && uvicorn main:app --host 0.0.0.0 --port 8080")
        return
    
    # Поиск файлов сканирования
    scan_files = glob.glob(os.path.join(SCANS_PATH, "*.json"))
    scan_files.sort()
    
    if not scan_files:
        print("Файлы сканирования не найдены в:", SCANS_PATH)
        return
    
    print(f"\nНайдено файлов сканирования: {len(scan_files)}")
    
    # Получение контекста из RAG
    print("\nПолучение данных об уязвимостях из RAG...")
    rag_start = time.time()
    
    rag_ctx, rag_sources = rag.get_context_with_metadata(
        "id: CVE Published: summary: cvss: 3.7 full_cve ghsa_id: cve_id: url: html_url: "
        "Отчет по результатам анализа уязвимостей Vulnerability Assessment Report "
        "Перечень выявленных уязвимостей List of Identified Vulnerabilities "
        "Наименование уязвимости Vulnerability Name Уровень критичности Severity Level "
        "Высокий High Средний Medium Низкий Low Критический Critical "
        "Описание уязвимости Vulnerability Description "
        "CVE Common Vulnerabilities and Exposures идентификатор уязвимости CVE "
        "BDU Банк данных угроз безопасности информации ФСТЭК России идентификатор БДУ "
        "CVSS Common Vulnerability Scoring System базовая оценка Base Score "
        "вектор атаки Attack Vector AV Network Adjacent Local Physical "
        "уязвимость удалённого выполнения кода remote code execution RCE "
        "уязвимость повышения привилегий privilege escalation "
        "уязвимость отказа в обслуживании denial of service DoS",
        k=50
    )
    
    rag_elapsed = time.time() - rag_start
    print(f"Данные из RAG получены за {rag_elapsed:.2f} сек")
    
    if rag_sources:
        print(f"Найдено источников в RAG: {len(rag_sources)}")
        for src in rag_sources[:5]:
            print(f"  - {src['filename']} (релевантность: {src['score']:.3f})")
    
    # ========== РАСЧЕТ УРОВНЯ КРИТИЧНОСТИ ==========
    print("\n" + "-" * 50)
    print("ВЫПОЛНЕНИЕ РАСЧЕТА ПО МЕТОДИКЕ ФСТЭК ОТ 30.06.2025")
    print("-" * 50)
    
    vuln_calc = VulnerabilityCriticalityCalculator()
    
    # Извлекаем CVE из файлов сканирования
    cve_data = parse_cve_from_scan_files(scan_files)
    
    if not cve_data:
        print("CVE не найдены в файлах сканирования.")
        print("Расчет будет выполнен на основе данных из RAG.")
    
    for cve in cve_data:
        vuln_calc.add_vulnerability(
            cve_id=cve['id'],
            cvss_score=cve['cvss'],
            component_type=cve['component_type'],
            quantity=cve['quantity'],
            perimeter_access=cve['perimeter'],
            exploit_status=cve['exploit'],
            consequences=cve['consequences']
        )
    
    calculation_details = vuln_calc.generate_calculation_details()
    vulnerability_assessment = vuln_calc.generate_full_report()
    vuln_summary = vuln_calc.get_summary()
    
    print(f"\nРезультаты расчета:")
    print(f"  - Всего уязвимостей: {vuln_summary['total']}")
    print(f"  - Критических: {vuln_summary['critical']}")
    print(f"  - Высоких: {vuln_summary['high']}")
    print(f"  - Средних: {vuln_summary['medium']}")
    print(f"  - Низких: {vuln_summary['low']}")
    
    # ========== ГЕНЕРАЦИЯ ОТЧЕТА ==========
    print("\n" + "-" * 50)
    print("ГЕНЕРАЦИЯ ОТЧЕТА ПО ОЦЕНКЕ КРИТИЧНОСТИ")
    print("-" * 50)
    
    chain = create_chain(report_prompt)
    
    print("Создание отчета...")
    report_start = time.time()
    
    report = chain.invoke({
        "rag_context": rag_ctx,
        "calculation_details": calculation_details,
        "vulnerability_assessment": vulnerability_assessment
    })
    
    report_elapsed = time.time() - report_start
    print(f"Отчет создан за {report_elapsed:.2f} сек")
    
    # ========== СОХРАНЕНИЕ РЕЗУЛЬТАТОВ ==========
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Сохраняем отчет
    report_file = os.path.join(RESULTS_DIR, f"criticality_assessment_{timestamp}.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\nОтчет сохранен: {report_file}")
    
    # Сохраняем расчеты
    calc_file = os.path.join(RESULTS_DIR, f"calculation_details_{timestamp}.txt")
    with open(calc_file, 'w', encoding='utf-8') as f:
        f.write(calculation_details)
    print(f"Расчеты сохранены: {calc_file}")
    
    # Сохраняем сводку
    summary_file = os.path.join(RESULTS_DIR, f"vuln_summary_{timestamp}.json")
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(vuln_summary, f, indent=2, ensure_ascii=False)
    print(f"Сводка сохранена: {summary_file}")
    
    # Сохраняем источники RAG
    if rag_sources:
        sources_file = os.path.join(RESULTS_DIR, f"rag_sources_criticality_{timestamp}.json")
        with open(sources_file, 'w', encoding='utf-8') as f:
            json.dump(rag_sources, f, indent=2, ensure_ascii=False)
        print(f"Источники RAG сохранены: {sources_file}")
    
    total_elapsed = time.time() - program_start
    
    print("\n" + "=" * 70)
    print("РАСЧЕТ ЗАВЕРШЕН")
    print("=" * 70)
    print(f"\nОбщее время: {total_elapsed:.2f} сек ({total_elapsed/60:.2f} мин)")
    print(f"Результаты сохранены в: {RESULTS_DIR}")


if __name__ == "__main__":
    main()