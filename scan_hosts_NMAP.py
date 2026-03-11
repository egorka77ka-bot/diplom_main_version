#!/usr/bin/env python3
# Модуль для запуска внешних
# команд - позволяет выполнять 
# программы из Python (например, nmap)
import subprocess
# Работа с JSON - для сохранения результатов в структурированном формате
import json
# Взаимодействие с операционной системой - пути к файлам, создание директорий
import os
# Системные функции - доступ к аргументам командной строки, 
import sys
import time
# HTTP-запросы - для связи с Ollama API (локальный AI)
import requests
# Дата и время - для временных меток в именах файлов
from datetime import datetime
from pathlib import Path
# Типизация - подсказки типов для лучшей читаемости кода
from typing import Dict, Any, List, Optional
# Регулярные выражения - поиск паттернов в тексте
import re
# Работа с IP-адресами - парсинг и валидация сетей
import ipaddress
# Параллельное выполнение - сканирование нескольких хостов одновременно
import concurrent.futures
# Многопоточность - для потокобезопасного вывода
import threading

# Конфигурация
OUTPUT_DIR = ".\RAG\data"
SCANNER_PATH = ".\mcp-vulnerability-scanner"
OLLAMA_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
NETWORK = "192.168.10.0/24"  # Сеть для сканирования
MAX_WORKERS = 5  # Максимальное количество параллельных сканирований
SCAN_TIMEOUT = 300  # Время на сканирование одного хоста (секунды)
PORT_SCAN_RANGE = "1-65535"  # Все порты

# Функция, используемая для того, чтобы каждое сканирование 
# выводило данные в консоль поочередно, а не одновременно
print_lock = threading.Lock()
#Создание нужной папки - если её нет, 
#(exist_ok=True - наличие искомой папки просто пропускает эту операцию)
os.makedirs(OUTPUT_DIR, exist_ok=True)
#Функция для вывода в консоль любых принимаемых данных,
def safe_print(*args, **kwargs):
    #with print_lock - только один поток может печатать одновременно
    with print_lock:
        print(*args, **kwargs)
# Класс для описания сканера
class ProductionScanner:
       
    def __init__(self):
        self.nmap_available = True
        self.vulndb_configured = True
        self.scanner_ready = True
        # Массив для хранения результатов сканирования
        self.scan_results = {}    
    # Вывод список обнаруженных IP адресов
   
    def discover_hosts(self) -> List[str]:
        safe_print(f"\nПоиск хостов в сети {NETWORK}...")
        # Массив для обнаруженных хостов с помощью ping sweep
        live_hosts = []
        
        try:
            # Используем Nmap
            if self.nmap_available:
                safe_print("  Nmap запущен...")
                # Команда Nmap для пингования сети
                cmd = ["nmap", "-sn", NETWORK]
                # Запуск Nmap
                result = subprocess.run(
                cmd, # Команда для выполнения
                shell=True, # Использовать командную оболочку Windows
                capture_output=True, # Захват stdout и stderr
                text=True, # Работа с текстом, а не с байтами
                timeout=SCAN_TIMEOUT
            )
                
            
                # Парсинг вывода nmap по хостам с помощью цикла 
                # для анализа каждой строчки
                for line in result.stdout.split('\n'):
                    # Определение IP адреса по ключевому слову 
                    # "Nmap scan report for" в отчетах Nmap
                    if "Nmap scan report for" in line:
                        # Извлекаем IP из строки
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if ip_match:
                            ip = ip_match.group(1)
                            # Извлекаем IP из результата поиска
                            live_hosts.append(ip)
                            safe_print(f"    Найден хост: {ip}")   
            
            # Если nmap недоступен, сканируем всю сеть (может быть медленно)
            
        except Exception as e:
            safe_print(f"  Ошибка обнаружения хостов: {e}")
        
        safe_print(f"\nВсего обнаружено хостов: {len(live_hosts)}")
        return live_hosts
    # Выполняет сканирование IP-адреса на все порты
    def scan_ip_full(self, ip: str) -> Dict[str, Any]:
        
        # С помощью JSON-RPC запрос формируем команду для MCP сервера
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "scan-ip",
                "arguments": {
                    "ip": ip,
                    "options": f"-sV -p {PORT_SCAN_RANGE}"
                }
            },
            "id": 1
        }
        
        # Сохраняем запрос во временном файле
        temp_file = os.path.join(OUTPUT_DIR, f"temp_{ip.replace('.', '_')}.json")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(request, f)
        
        # Запускаем сканер в Windows
        """Команда для Windows:
        type "{temp_file}" - читаем файл
        cd /d "{SCANNER_PATH}" - переходим в папку сканера
        && npm run dev - запускаем MCP сервер"""
        cmd = f'type "{temp_file}" | cd /d "{SCANNER_PATH}" && npm run dev'
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd, # Команда для выполнения
                shell=True, # Использовать командную оболочку Windows
                capture_output=True, # Захват stdout и stderr
                text=True, # Работа с текстом, а не с байтами
                timeout=SCAN_TIMEOUT
            )
            elapsed = time.time() - start_time
            
            # Парсинг ответа, полученного от MCP сервера
            scan_result = self._parse_response(result.stdout, ip)
            
            # Добавление результатов с Nmap
            if self.nmap_available:
                scan_result = self._enrich_with_nmap_full(scan_result, ip)
            
            scan_result['scan_duration'] = elapsed
            safe_print(f" Сканирование завершено за {elapsed:.1f} сек")
            
            return scan_result
        # Блок анализа и вывода времени сканирования     
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)   
    # Функция сохранения результатов сканирования
    def scan_ip_parallel(self, ip: str) -> Dict[str, Any]:
        result = self.scan_ip_full(ip)
        self.scan_results[ip] = result
        return result
    # Парсинг ответа от MCP сервера
    def _parse_response(self, output: str, ip: str) -> Dict[str, Any]:
        
        # Ищем JSON
        for line in output.split('\n'):
            line = line.strip()
            # Если строка похожа на JSON, то пробуем его распарсить
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except:
                    continue
        
        # Если такой JSON не найден, создаем структурированный ответ
        return {
            "ip": ip,
            "timestamp": datetime.now().isoformat(),
            "raw_output": output,
            "vulnerabilities": self._extract_vulnerabilities(output),
            "open_ports": self._extract_ports(output)
        }
    # Добавление данных от nmap
    def _enrich_with_nmap_full(self, scan_result: Dict[str, Any], ip: str) -> Dict[str, Any]:
        
        safe_print(" Запуск Nmap сканирования.")
        
        try:
            # Полное сканирование всех портов с определением версий
            cmd = ["nmap", "-sV", "-p", PORT_SCAN_RANGE, ip]
            nmap_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SCAN_TIMEOUT
            )
            
            if nmap_result.returncode == 0:
                scan_result['nmap_full_scan'] = nmap_result.stdout
                
                ports = []
                for line in nmap_result.stdout.split('\n'):
                    if '/tcp' in line and 'open' in line:
                        parts = line.split()
                        port_info = {
                            'port': parts[0].split('/')[0],
                            'state': parts[1],
                            'service': parts[2] if len(parts) > 2 else 'unknown',
                            'version': ' '.join(parts[3:]) if len(parts) > 3 else ''
                        }
                        # Добавление в список выше
                        ports.append(port_info)
                
                scan_result['open_ports_full'] = ports
                safe_print(f" Найдено открытых портов: {len(ports)}")
                
        except Exception as e:
            safe_print(f" Ошибка Nmap: {e}")
        
        return scan_result
    # Посик CVE уязвимостяей в тексте
    def _extract_vulnerabilities(self, text: str) -> List[Dict[str, Any]]:
        
        vulns = []
        
        # Ищем CVE номера по паттернну
        cve_pattern = r'CVE-\d{4}-\d+'
        cves = re.findall(cve_pattern, text)
        
        for cve in set(cves):
            vulns.append({
                'id': cve,
                'source': 'extracted',
                'severity': 'unknown'
            })
        
        return vulns
    
    def _extract_ports(self, text: str) -> List[int]:
        """Извлекает информацию о портах из текста"""
        ports = []
        port_pattern = r'port[^\d]*(\d+)|(\d+)/tcp'
        matches = re.findall(port_pattern, text.lower())
        
        for match in matches:
            for group in match:
                if group and group.isdigit():
                    ports.append(int(group))
        
        return list(set(ports))
    
    def get_status_report(self) -> str:
        report = []
        report.append(f"Папка сохранения результатов: {OUTPUT_DIR}")
        report.append(f"Сеть для сканирования: {NETWORK}")
        report.append(f"Диапазон портов: {PORT_SCAN_RANGE}")
        report.append(f"Параллельных потоков сканирования: {MAX_WORKERS}")      
               
        return '\n'.join(report)

# Описание анализатора в Ollama
class OllamaAnalyzer:
        
    def __init__(self):
        self.available = self._check_ollama()
    
    # Проверка доступности Ollama
    def _check_ollama(self) -> bool:
        try:
            requests.get("http://localhost:11434/api/tags", timeout=2)
            return True
        except:
            return False
   # Запуск анализа результатов сканирования
    def analyze(self, ip: str, scan_data: Dict[str, Any]) -> str:
        
        if not self.available:
            return "Ollama недоступен. Запустите Ollama."
        
        # Используем полные данные и добавляем описание для промпта
        ports_info = scan_data.get('open_ports_full', scan_data.get('open_ports', []))
        vulns = scan_data.get('vulnerabilities', [])
        
        ports_text = "\n".join([
            f"  - Порт {p['port']}: {p['service']} {p.get('version', '')}"
            for p in ports_info[:20]
        ]) if ports_info else " Открытые порты не обнаружены. "
        
        vulns_text = "\n".join([
            f"  - {v['id']} (источник: {v.get('source', 'unknown')})"
            for v in vulns[:15]
        ]) if vulns else " Уязвимости не обнаружены. "
        
        prompt = f"""Ты — эксперт по информационной безопасности и кибербезопасности. Проанализируй результаты сканирования всех портов хостов).

IP АДРЕС: {ip}

ОТКРЫТЫЕ ПОРТЫ И СЕРВИСЫ (полный список):
{ports_text}

НАЙДЕННЫЕ УЯЗВИМОСТИ:
{vulns_text}

На основе этих данных предоставь структурированный анализ:

1. КРИТИЧЕСКИЕ УГРОЗЫ:
   - Какие сервисы наиболее уязвимы?
   - Какие нестандартные порты открыты?
   - Какие CVE требуют немедленного внимания?
   - Оценка уровня риска (НИЗКИЙ/СРЕДНИЙ/ВЫСОКИЙ/КРИТИЧЕСКИЙ)

2. НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:
   - Что нужно исправить прямо сейчас?
   - Конкретные команды/рекомендации
   - Какие порты рекомендуется закрыть

3. ПЛАН ДАЛЬНЕЙШИХ ДЕЙСТВИЙ:
   - Дополнительные проверки
   - Рекомендации по усилению защиты
   - Приоритеты устранения уязвимостей

Ответ предоставь на русском языке, кратко и самое основное."""
        
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 800,
                        "temperature": 0.3
                    }
                },
                timeout=60
            )
            # Возвращаем ответ модели
            if response.status_code == 200:
                return response.json().get('response', 'Нет ответа')
            else:
                return f"Ошибка API: {response.status_code}"
        except Exception as e:
            return f"Ошибка подключения к Ollama: {e}"

# Функция вызова сканирования
def scan_worker(scanner: ProductionScanner, ip: str):
    
    safe_print(f"СКАНИРОВАНИЕ ХОСТА: {ip}")
    
    result = scanner.scan_ip_parallel(ip)
    
    # Сохранение JSON для этого хоста с нужным названием
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_ip = ip.replace('.', '_')
    json_file = os.path.join(OUTPUT_DIR, f"scan_full_{safe_ip}_{timestamp}.json")
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    safe_print(f"JSON сохранен: {os.path.basename(json_file)}")
    
    return result

# Главная функция
def main():
    print("Сканирование всех хостов в сети 192.168.10.0/24.")
    
    # Инициализация инструментов
    scanner = ProductionScanner()
    analyzer = OllamaAnalyzer()
    
    # Отчет о состоянии
    print(scanner.get_status_report())
    
    # Обнаружение хостов
    print(f"ЭТАП 1: ПОИСК ХОСТОВ В СЕТИ {NETWORK}")
    live_hosts = scanner.discover_hosts()
    
    if not live_hosts:
        print("Не обнаружено хостов в сети!")
        return
    
    print(f"Найдено работающих хостов: {len(live_hosts)}")
    print(f"Результаты будут сохранены в папке по следующему адресу: {OUTPUT_DIR}")
    
    # Проверка определены ли все хосты верно
    response = input(f"Начать сканирование {len(live_hosts)} хостов? (y/n): ")
    if response.lower() != 'y':
        print("Сканирование отменено пользователем")
        return
    
    print(f"ЭТАП 2: СКАНИРОВАНИЕ ХОСТОВ")
    print(f"Параллельных потоков: {MAX_WORKERS}")
    print(f"Таймаут на хост: {SCAN_TIMEOUT} сек")
    
    start_time = time.time()
    
    # Параллельное сканирование
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scan_worker, scanner, ip): ip for ip in live_hosts}
        
        for future in concurrent.futures.as_completed(futures):
            ip = futures[future]
            try:
                future.result()
            except Exception as e:
                safe_print(f"Ошибка при сканировании {ip}: {e}")
    
    elapsed_total = time.time() - start_time
    
    print("ЭТАП 3: АНАЛИЗ РЕЗУЛЬТАТОВ")
    # Анализ каждого хоста
    all_results = scanner.scan_results
    
    for ip, scan_result in all_results.items():
        print(f"Анализ хоста {ip}...")
        analysis = analyzer.analyze(ip, scan_result)
        
        # Сохранение анализа
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_ip = ip.replace('.', '_')
        analysis_file = os.path.join(OUTPUT_DIR, f"analysis_full_{safe_ip}_{timestamp}.txt")
        
        with open(analysis_file, 'w', encoding='utf-8') as f:
            f.write(f"АНАЛИЗ БЕЗОПАСНОСТИ {ip}\n")
            f.write(analysis)
        
        print(f"Анализ сохранен: {os.path.basename(analysis_file)}")
    
    # Сохранение сводного отчета
    print(f"ЭТАП 4: ИТОГОВЫЙ ОТЧЕТ")
 
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_file = os.path.join(OUTPUT_DIR, f"summary_full_scan_{timestamp}.json")
    
    summary_data = {
        "network": NETWORK,
        "scan_time": datetime.now().isoformat(),
        "total_hosts": len(live_hosts),
        "scanned_hosts": len(all_results),
        "duration_seconds": elapsed_total,
        "duration_minutes": round(elapsed_total/60, 1),
        "results": all_results
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)
    
    print("СКАНИРОВАНИЕ СЕТИ ЗАВЕРШЕНО")
    print(f"Статистика:")
    print(f"   • Обнаружено хостов: {len(live_hosts)}")
    print(f"   • Просканировано: {len(all_results)}")
    print(f"   • Общее время сканирования: {elapsed_total:.1f} сек ({elapsed_total/60:.1f} мин)")
    print(f"Все результаты сохранены в папке: {OUTPUT_DIR}")
    print(f"Сводный отчет: {os.path.basename(summary_file)}")
    
    print(f"Работа программы завершена.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Сканирование прервано пользователем")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()