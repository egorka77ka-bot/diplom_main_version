#!/usr/bin/env python3
"""
PRODUCTION MCP VULNERABILITY SCANNER - FULL NETWORK SCAN
Сканирование всех хостов в сети 192.168.10.0/24 на все порты
Версия 2.0.0 (дипломный проект)
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
import ipaddress
import concurrent.futures
import threading

# Конфигурация
OUTPUT_DIR = ".\RAG\data"
SCANNER_PATH = ".\mcp-vulnerability-scanner"
OLLAMA_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
NETWORK = "192.168.10.0/24"  # Сеть для сканирования
MAX_WORKERS = 5  # Максимальное количество параллельных сканирований
SCAN_TIMEOUT = 300  # Таймаут на сканирование одного хоста (5 минут)
PORT_SCAN_RANGE = "1-65535"  # Все порты

# Блокировка для потокобезопасного вывода
print_lock = threading.Lock()

os.makedirs(OUTPUT_DIR, exist_ok=True)

def safe_print(*args, **kwargs):
    """Потокобезопасный вывод в консоль"""
    with print_lock:
        print(*args, **kwargs)

class ProductionScanner:
    """Продакшн-сканер с поддержкой реальных данных"""
    
    def __init__(self):
        self.nmap_available = self._check_nmap()
        self.vulndb_configured = self._check_vulndb_config()
        self.scanner_ready = False
        self.scan_results = {}  # Словарь для хранения результатов всех хостов
        
    def _check_nmap(self) -> bool:
        """Проверяет наличие Nmap в системе"""
        try:
            result = subprocess.run(
                ["nmap", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.split('\n')[0]
                safe_print(f"Nmap найден: {version}")
                return True
        except:
            pass
        safe_print("Nmap не найден. Сканирование будет ограничено.")
        return False
    
    def _check_vulndb_config(self) -> bool:
        """Проверяет наличие API ключа VulnDB"""
        env_file = Path(SCANNER_PATH) / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                content = f.read()
                if 'VULNDB_API_KEY=' in content and 'your_key' not in content:
                    safe_print("VulnDB API ключ настроен")
                    return True
        safe_print("VulnDB API ключ не настроен. Используются тестовые данные.")
        return False
    
    def discover_hosts(self) -> List[str]:
        """
        Обнаруживает все живые хосты в сети с помощью ping sweep
        """
        safe_print(f"\nОбнаружение хостов в сети {NETWORK}...")
        
        live_hosts = []
        
        try:
            # Используем nmap для ping sweep если доступен
            if self.nmap_available:
                safe_print("  Использование Nmap для обнаружения хостов...")
                cmd = ["nmap", "-sn", NETWORK]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                # Парсим вывод nmap для извлечения живых хостов
                for line in result.stdout.split('\n'):
                    if "Nmap scan report for" in line:
                        # Извлекаем IP из строки
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if ip_match:
                            ip = ip_match.group(1)
                            live_hosts.append(ip)
                            safe_print(f"    Найден хост: {ip}")
            
            # Если nmap недоступен, сканируем всю сеть (может быть медленно)
            else:
                safe_print("  Nmap недоступен, сканирование всех IP в сети...")
                network = ipaddress.ip_network(NETWORK, strict=False)
                for ip in network.hosts():
                    # Простая проверка ping
                    response = subprocess.run(
                        ["ping", "-n", "1", "-w", "500", str(ip)],
                        capture_output=True,
                        text=True
                    )
                    if response.returncode == 0:
                        live_hosts.append(str(ip))
                        safe_print(f"    Найден хост: {ip}")
            
        except Exception as e:
            safe_print(f"  Ошибка обнаружения хостов: {e}")
        
        safe_print(f"\nВсего обнаружено хостов: {len(live_hosts)}")
        return live_hosts
    
    def scan_ip_full(self, ip: str) -> Dict[str, Any]:
        """
        Выполняет ПОЛНОЕ сканирование IP-адреса на ВСЕ порты
        """
        safe_print(f"\nПОЛНОЕ СКАНИРОВАНИЕ {ip} (все порты 1-65535)...")
        
        # JSON-RPC запрос к MCP серверу
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "scan-ip",
                "arguments": {
                    "ip": ip,
                    "options": f"-sV -p {PORT_SCAN_RANGE}"  # Сканирование всех портов
                }
            },
            "id": 1
        }
        
        # Сохраняем запрос
        temp_file = os.path.join(OUTPUT_DIR, f"temp_{ip.replace('.', '_')}.json")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(request, f)
        
        # Запускаем сканер
        cmd = f'type "{temp_file}" | cd /d "{SCANNER_PATH}" && npm run dev'
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=SCAN_TIMEOUT
            )
            elapsed = time.time() - start_time
            
            # Парсим ответ
            scan_result = self._parse_response(result.stdout, ip)
            
            # Обогащаем результатами Nmap если доступен (для полноты)
            if self.nmap_available:
                scan_result = self._enrich_with_nmap_full(scan_result, ip)
            
            scan_result['scan_duration'] = elapsed
            safe_print(f"  Сканирование завершено за {elapsed:.1f} сек")
            
            return scan_result
            
        except subprocess.TimeoutExpired:
            safe_print(f"  Таймаут сканирования {ip}")
            return {"error": "Timeout", "ip": ip}
        except Exception as e:
            safe_print(f"  Ошибка: {e}")
            return {"error": str(e), "ip": ip}
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def scan_ip_parallel(self, ip: str) -> Dict[str, Any]:
        """
        Обертка для параллельного сканирования с сохранением результатов
        """
        result = self.scan_ip_full(ip)
        self.scan_results[ip] = result
        return result
    
    def _parse_response(self, output: str, ip: str) -> Dict[str, Any]:
        """Парсит ответ от MCP сервера"""
        # Ищем JSON в выводе
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except:
                    continue
        
        # Если JSON не найден, создаем структурированный ответ
        return {
            "ip": ip,
            "timestamp": datetime.now().isoformat(),
            "raw_output": output,
            "vulnerabilities": self._extract_vulnerabilities(output),
            "open_ports": self._extract_ports(output)
        }
    
    def _enrich_with_nmap_full(self, scan_result: Dict[str, Any], ip: str) -> Dict[str, Any]:
        """Обогащает результаты полным Nmap сканированием"""
        safe_print("  Запуск полного Nmap сканирования (все порты)...")
        
        try:
            # Полное сканирование всех портов с определением версий
            nmap_result = subprocess.run(
                ["nmap", "-sV", "-p", PORT_SCAN_RANGE, ip],
                capture_output=True,
                text=True,
                timeout=SCAN_TIMEOUT
            )
            
            if nmap_result.returncode == 0:
                scan_result['nmap_full_scan'] = nmap_result.stdout
                
                # Парсим открытые порты
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
                        ports.append(port_info)
                
                scan_result['open_ports_full'] = ports
                safe_print(f"    Найдено портов (полное сканирование): {len(ports)}")
                
        except Exception as e:
            safe_print(f"    Ошибка Nmap: {e}")
        
        return scan_result
    
    def _extract_vulnerabilities(self, text: str) -> List[Dict[str, Any]]:
        """Извлекает информацию об уязвимостях из текста"""
        vulns = []
        
        # Ищем CVE номера
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
        """Возвращает отчет о состоянии системы"""
        report = []
        report.append("="*60)
        report.append("СТАТУС СИСТЕМЫ")
        report.append("="*60)
        
        report.append(f"\nДиректория результатов: {OUTPUT_DIR}")
        report.append(f"Директория сканера: {SCANNER_PATH}")
        report.append(f"Сеть для сканирования: {NETWORK}")
        report.append(f"Диапазон портов: {PORT_SCAN_RANGE}")
        report.append(f"Параллельных потоков: {MAX_WORKERS}")
        
        report.append(f"\nКомпоненты:")
        report.append(f"  • Nmap: {'ДОСТУПЕН' if self.nmap_available else 'НЕ НАЙДЕН'}")
        report.append(f"  • VulnDB API: {'НАСТРОЕН' if self.vulndb_configured else 'НЕ НАСТРОЕН'}")
        
        if not self.nmap_available:
            report.append("\nВНИМАНИЕ: Для полноценной работы установите Nmap:")
            report.append("   https://nmap.org/download.html")
        
        if not self.vulndb_configured:
            report.append("\nВНИМАНИЕ: Для реальных CVE настройте VulnDB API:")
            report.append("   1. Зарегистрируйтесь на https://vuldb.com")
            report.append("   2. Получите API ключ")
            report.append(f"   3. Создайте файл {SCANNER_PATH}\\.env с:")
            report.append("      VULNDB_API_KEY=ваш_ключ")
        
        return '\n'.join(report)


class OllamaAnalyzer:
    """Анализатор на основе Ollama"""
    
    def __init__(self):
        self.available = self._check_ollama()
    
    def _check_ollama(self) -> bool:
        try:
            requests.get("http://localhost:11434/api/tags", timeout=2)
            return True
        except:
            return False
    
    def analyze(self, ip: str, scan_data: Dict[str, Any]) -> str:
        """Глубокий анализ результатов сканирования"""
        
        if not self.available:
            return "Ollama недоступен. Анализ пропущен."
        
        # Используем полные данные если есть
        ports_info = scan_data.get('open_ports_full', scan_data.get('open_ports', []))
        vulns = scan_data.get('vulnerabilities', [])
        
        ports_text = "\n".join([
            f"  - Порт {p['port']}: {p['service']} {p.get('version', '')}"
            for p in ports_info[:20]
        ]) if ports_info else "  Открытые порты не обнаружены"
        
        vulns_text = "\n".join([
            f"  - {v['id']} (источник: {v.get('source', 'unknown')})"
            for v in vulns[:15]
        ]) if vulns else "  Уязвимости не обнаружены"
        
        prompt = f"""Ты — эксперт по кибербезопасности. Проанализируй результаты ПОЛНОГО сканирования (все порты 1-65535).

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

Ответ предоставь на русском языке, кратко и по делу."""
        
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
            
            if response.status_code == 200:
                return response.json().get('response', 'Нет ответа')
            else:
                return f"Ошибка API: {response.status_code}"
        except Exception as e:
            return f"Ошибка подключения к Ollama: {e}"


def scan_worker(scanner: ProductionScanner, ip: str):
    """Функция для параллельного сканирования"""
    safe_print(f"\n{'='*70}")
    safe_print(f"СКАНИРОВАНИЕ ХОСТА: {ip}")
    safe_print(f"{'='*70}")
    
    result = scanner.scan_ip_parallel(ip)
    
    # Сохранение JSON для этого хоста
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_ip = ip.replace('.', '_')
    json_file = os.path.join(OUTPUT_DIR, f"scan_full_{safe_ip}_{timestamp}.json")
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    safe_print(f"\nJSON сохранен: {os.path.basename(json_file)}")
    
    return result


def main():
    """Главная функция"""
    
    print("="*80)
    print("PRODUCTION MCP VULNERABILITY SCANNER - FULL NETWORK SCAN")
    print("Сканирование всех хостов в сети 192.168.10.0/24 на все порты")
    print("Версия 2.0.0 (дипломный проект)")
    print("="*80)
    
    # Инициализация
    scanner = ProductionScanner()
    analyzer = OllamaAnalyzer()
    
    # Отчет о состоянии
    print(scanner.get_status_report())
    
    # Обнаружение хостов
    print(f"\nЭТАП 1: ОБНАРУЖЕНИЕ ХОСТОВ В СЕТИ {NETWORK}")
    print("="*70)
    live_hosts = scanner.discover_hosts()
    
    if not live_hosts:
        print("\nНе обнаружено живых хостов в сети!")
        return
    
    print(f"\nНайдено живых хостов: {len(live_hosts)}")
    print(f"Результаты будут сохранены в: {OUTPUT_DIR}")
    
    # Подтверждение
    response = input(f"\nНачать ПОЛНОЕ сканирование всех портов для {len(live_hosts)} хостов? (y/n): ")
    if response.lower() != 'y':
        print("Сканирование отменено")
        return
    
    print(f"\nЭТАП 2: ПОЛНОЕ СКАНИРОВАНИЕ ВСЕХ ПОРТОВ (1-65535)")
    print(f"   Параллельных потоков: {MAX_WORKERS}")
    print(f"   Таймаут на хост: {SCAN_TIMEOUT} сек")
    print("="*70)
    
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
    
    print(f"\n{'='*70}")
    print("ЭТАП 3: AI-АНАЛИЗ РЕЗУЛЬТАТОВ")
    
    
    # Анализ каждого хоста
    all_results = scanner.scan_results
    
    for ip, scan_result in all_results.items():
        print(f"\nАнализ хоста {ip}...")
        analysis = analyzer.analyze(ip, scan_result)
        
        # Сохранение анализа
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_ip = ip.replace('.', '_')
        analysis_file = os.path.join(OUTPUT_DIR, f"analysis_full_{safe_ip}_{timestamp}.txt")
        
        with open(analysis_file, 'w', encoding='utf-8') as f:
            f.write(f"ПОЛНЫЙ АНАЛИЗ БЕЗОПАСНОСТИ {ip}\n")
            f.write("="*60 + "\n\n")
            f.write(analysis)
        
        print(f"Анализ сохранен: {os.path.basename(analysis_file)}")
    
    # Сохранение сводного отчета
    print(f"\nЭТАП 4: ФОРМИРОВАНИЕ СВОДНОГО ОТЧЕТА")
 
    
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
    
    print(f"\n{'='*70}")
    print("ПОЛНОЕ СКАНИРОВАНИЕ СЕТИ ЗАВЕРШЕНО")
    print(f"{'='*70}")
    print(f"\nСтатистика:")
    print(f"   • Обнаружено хостов: {len(live_hosts)}")
    print(f"   • Просканировано: {len(all_results)}")
    print(f"   • Общее время: {elapsed_total:.1f} сек ({elapsed_total/60:.1f} мин)")
    print(f"\nВсе результаты: {OUTPUT_DIR}")
    print(f"Сводный отчет: {os.path.basename(summary_file)}")
    
    # Итоговый статус
    print(f"\nИТОГОВЫЙ СТАТУС:")
    print(f"  • Nmap: {'ДОСТУПЕН' if scanner.nmap_available else 'НЕ НАЙДЕН'}")
    print(f"  • VulnDB: {'НАСТРОЕН' if scanner.vulndb_configured else 'НЕ НАСТРОЕН'}")
    print(f"  • Ollama: {'ДОСТУПЕН' if analyzer.available else 'НЕ ДОСТУПЕН'}")
    
    if not scanner.nmap_available:
        print("\nРекомендация: Установите Nmap для получения более точных результатов")
    if not scanner.vulndb_configured:
        print("Рекомендация: Настройте VulnDB API для получения реальных CVE")
    
    print(f"\nРабота программы завершена.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nСканирование прервано пользователем")
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
        import traceback
        traceback.print_exc()