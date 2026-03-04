#!/usr/bin/env python3
"""
Скрипт для сбора установленного ПО с удаленных хостов и проверки CVE
Запуск: uv run python scan_hosts.py --hosts hosts.json
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any
import argparse
import time
from pathlib import Path

# ========== НАСТРОЙКА ПУТЕЙ ==========
BASE_DIR = Path(__file__).parent.absolute()
CVE_SEARCH_PATH = BASE_DIR / "CVE-Search-MCP"
DATA_DIR = BASE_DIR / "RAG" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

print("="*80)
print("CVE SCANNER - МАССОВАЯ ПРОВЕРКА УСТАНОВЛЕННОГО ПО")
print("="*80)
print(f"\n[INFO] Основная папка: {BASE_DIR}")
print(f"[INFO] Путь к CVE-Search-MCP: {CVE_SEARCH_PATH}")
print(f"[INFO] Результаты будут сохраняться в: {DATA_DIR}")

# ========== АВТОМАТИЧЕСКИЙ ПОИСК МОДУЛЯ CVE ==========
MCP_AVAILABLE = False
search_by_keyword = None

if CVE_SEARCH_PATH.exists():
    # Добавляем пути в sys.path
    paths_to_add = [
        str(CVE_SEARCH_PATH),
        str(CVE_SEARCH_PATH / "src"),
        str(CVE_SEARCH_PATH / "mcp_server_cve_search"),
        str(CVE_SEARCH_PATH / "cve_search"),
        str(CVE_SEARCH_PATH / "cve-search"),
    ]
    
    for path in paths_to_add:
        if path not in sys.path and os.path.exists(path):
            sys.path.insert(0, path)
            print(f"[INFO] Добавлен путь: {path}")
    
    # Пробуем найти функцию search_by_keyword в разных местах
    import importlib
    
    # Список возможных модулей для проверки
    possible_modules = [
        "mcp_server_cve_search.server",
        "mcp_server_cve_search",
        "server",
        "cve_search.server",
        "cve_search",
        "main",
    ]
    
    for module_name in possible_modules:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, 'search_by_keyword'):
                search_by_keyword = getattr(module, 'search_by_keyword')
                MCP_AVAILABLE = True
                print(f"[OK] MCP сервер найден в модуле: {module_name}")
                break
        except ImportError:
            continue
    
    if not MCP_AVAILABLE:
        print("\n[ERROR] Не удалось найти функцию search_by_keyword")
        print("   Проверьте содержимое папки CVE-Search-MCP:")
        print(f"   {CVE_SEARCH_PATH}")
        print("\n   Возможные решения:")
        print("   1. Установите CVE-Search-MCP как пакет:")
        print(f"      cd {CVE_SEARCH_PATH}")
        print("      pip install -e .")
        print("   2. Или используйте прямой импорт, указав правильное имя модуля")
else:
    print(f"\n[ERROR] Папка CVE-Search-MCP не найдена: {CVE_SEARCH_PATH}")

# ========== ИМПОРТ ДЛЯ WINDOWS ==========
try:
    from impacket.smbconnection import SMBConnection
    from impacket.dcerpc.v5 import transport, registry
    IMPACKET_AVAILABLE = True
    print("[OK] impacket найден")
except ImportError:
    IMPACKET_AVAILABLE = False
    print("\n[WARN] impacket не установлен. Установите: pip install impacket")

# ========== ИМПОРТ ДЛЯ LINUX ==========
try:
    import paramiko
    SSH_AVAILABLE = True
    print("[OK] paramiko найден")
except ImportError:
    SSH_AVAILABLE = False
    print("\n[WARN] paramiko не установлен. Установите: pip install paramiko")


class HostScanner:
    """Класс для сканирования отдельного хоста"""
    
    def __init__(self, host_config: Dict):
        self.config = host_config
        self.installed_software = []
        self.vulnerabilities = []
        self.vulnerable_software = []
        
    def collect_software_windows(self) -> List[Dict]:
        """Сбор ПО с Windows хоста через SMB и реестр"""
        print(f"  [INFO] Windows хост {self.config['ip']}...")
        
        if not IMPACKET_AVAILABLE:
            print("    [ERROR] impacket не установлен")
            return []
        
        try:
            print(f"    [INFO] Подключение к {self.config['ip']} через SMB...")
            
            conn = SMBConnection(
                remoteName=self.config['ip'],
                remoteHost=self.config['ip']
            )
            conn.login(
                user=self.config['username'],
                password=self.config['password']
            )
            
            print(f"    [OK] SMB подключение установлено")
            
            string_binding = r'ncacn_np:445[\pipe\winreg]'
            rpctransport = transport.DCERPCTransportFactory(string_binding)
            rpctransport.set_smb_connection(conn)
            
            dce = rpctransport.get_dce_rpc()
            dce.connect()
            dce.bind(registry.MSRPC_UUID_REGR)
            
            software_list = []
            reg_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ]
            
            for reg_path in reg_paths:
                try:
                    ans = registry.hOpenLocalMachine(dce)
                    key_handle = registry.hBaseRegOpenKey(
                        dce, ans, reg_path, 
                        samDesired=registry.KEY_READ
                    )
                    
                    i = 0
                    while True:
                        try:
                            subkey_name = registry.hBaseRegEnumKey(dce, key_handle, i)
                            
                            subkey_handle = registry.hBaseRegOpenKey(
                                dce, key_handle, subkey_name,
                                samDesired=registry.KEY_READ
                            )
                            
                            try:
                                name = registry.hBaseRegQueryValue(dce, subkey_handle, "DisplayName")
                            except:
                                name = None
                                
                            try:
                                version = registry.hBaseRegQueryValue(dce, subkey_handle, "DisplayVersion")
                            except:
                                version = "unknown"
                                
                            try:
                                vendor = registry.hBaseRegQueryValue(dce, subkey_handle, "Publisher")
                            except:
                                vendor = "unknown"
                            
                            if name and name[1]:
                                software_list.append({
                                    "name": name[1],
                                    "version": version[1] if version != "unknown" else "unknown",
                                    "vendor": vendor[1] if vendor != "unknown" else "unknown"
                                })
                            
                            registry.hBaseRegCloseKey(dce, subkey_handle)
                            i += 1
                            
                        except Exception:
                            break
                    
                    registry.hBaseRegCloseKey(dce, key_handle)
                    
                except Exception as e:
                    print(f"    [WARN] Ошибка чтения {reg_path}: {e}")
            
            dce.disconnect()
            conn.close()
            
            print(f"    [OK] Найдено {len(software_list)} программ")
            self.installed_software = software_list
            
        except Exception as e:
            print(f"    [ERROR] Ошибка: {e}")
        
        return self.installed_software
    
    def collect_software_linux(self) -> List[Dict]:
        """Сбор ПО с Linux хоста через SSH"""
        print(f"  [INFO] Linux хост {self.config['ip']}...")
        
        if not SSH_AVAILABLE:
            print("    [ERROR] paramiko не установлен")
            return []
        
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                self.config['ip'],
                port=self.config.get('port', 22),
                username=self.config['username'],
                password=self.config['password'],
                timeout=10
            )
            
            stdin, stdout, stderr = client.exec_command('cat /etc/os-release 2>/dev/null || echo "unknown"')
            os_info = stdout.read().decode().lower()
            
            software_list = []
            
            if 'ubuntu' in os_info or 'debian' in os_info:
                print("    [INFO] Определена Debian/Ubuntu")
                cmd = "dpkg-query -W -f='${Package}\\t${Version}\\t${Maintainer}\\n' 2>/dev/null | head -200"
            elif 'rhel' in os_info or 'centos' in os_info or 'fedora' in os_info:
                print("    [INFO] Определена RHEL/CentOS")
                cmd = "rpm -qa --queryformat '%{NAME}\\t%{VERSION}\\t%{VENDOR}\\n' 2>/dev/null | head -200"
            elif 'arch' in os_info:
                print("    [INFO] Определена Arch")
                cmd = "pacman -Q 2>/dev/null | head -200"
            elif 'alpine' in os_info:
                print("    [INFO] Определена Alpine")
                cmd = "apk info -v 2>/dev/null | head -200"
            else:
                print(f"    [INFO] Неизвестная ОС, пробуем общие команды")
                for test_cmd in [
                    "dpkg-query -W -f='${Package}\\t${Version}\\n' 2>/dev/null | head -100",
                    "rpm -qa --queryformat '%{NAME}\\t%{VERSION}\\n' 2>/dev/null | head -100",
                ]:
                    stdin, stdout, stderr = client.exec_command(test_cmd)
                    if stdout.read().decode().strip():
                        cmd = test_cmd
                        break
                else:
                    cmd = "echo 'No package manager found'"
            
            stdin, stdout, stderr = client.exec_command(cmd)
            output = stdout.read().decode()
            
            for line in output.strip().split('\n'):
                if line and '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        software_list.append({
                            "name": parts[0].strip(),
                            "version": parts[1].strip(),
                            "vendor": parts[2].strip() if len(parts) > 2 else 'unknown'
                        })
            
            client.close()
            print(f"    [OK] Найдено {len(software_list)} пакетов")
            self.installed_software = software_list
            
        except Exception as e:
            print(f"    [ERROR] Ошибка: {e}")
        
        return self.installed_software
    
    def collect_software(self) -> List[Dict]:
        print(f"\n  [HOST] {self.config['ip']} ({self.config['os']})")
        
        if self.config['os'].lower() == 'windows':
            return self.collect_software_windows()
        elif self.config['os'].lower() == 'linux':
            return self.collect_software_linux()
        else:
            print(f"  [ERROR] Неподдерживаемая ОС")
            return []
    
    def check_cve_for_software(self, max_items=30) -> List[Dict]:
        if not self.installed_software:
            return []
        
        print(f"\n  [INFO] Проверка ПО на уязвимости...")
        
        if not MCP_AVAILABLE or search_by_keyword is None:
            print("    [ERROR] MCP сервер не доступен")
            return []
        
        vulnerable_software = []
        total = min(len(self.installed_software), max_items)
        
        for i, software in enumerate(self.installed_software[:max_items], 1):
            keyword = software['name'].split()[0] if software['name'] else "unknown"
            if len(keyword) > 30:
                keyword = keyword[:30]
            
            print(f"    [{i}/{total}] {keyword}...", end="")
            
            try:
                result = search_by_keyword(keyword, limit=3)
                
                if result and result.get('vulnerabilities'):
                    vuln_count = len(result['vulnerabilities'])
                    print(f" [FOUND] {vuln_count}")
                    vulnerable_software.append({
                        "software": software,
                        "cve_count": vuln_count,
                        "details": result['vulnerabilities'][:3]
                    })
                else:
                    print(f" [OK]")
                    
            except Exception as e:
                print(f" [ERROR]")
            
            time.sleep(0.3)
        
        self.vulnerable_software = vulnerable_software
        print(f"\n  [INFO] Уязвимых: {len(vulnerable_software)}")
        return vulnerable_software


class Orchestrator:
    def __init__(self, hosts_config: List[Dict]):
        self.hosts = [HostScanner(config) for config in hosts_config]
        self.results = {}
        
    def scan_all(self):
        print(f"\n{'='*80}")
        print(f"ЗАПУСК СКАНИРОВАНИЯ {len(self.hosts)} ХОСТОВ")
        print(f"{'='*80}")
        
        for host in self.hosts:
            self.scan_single_host(host)
        
        return self.results
    
    def scan_single_host(self, host: HostScanner):
        print(f"\n{'='*60}")
        print(f"ХОСТ: {host.config['ip']} ({host.config['os']})")
        print(f"{'='*60}")
        
        software = host.collect_software()
        
        if not software:
            self.results[host.config['ip']] = {
                "config": host.config,
                "error": "Failed to collect software",
                "timestamp": datetime.now().isoformat()
            }
            return
        
        vulns = host.check_cve_for_software(max_items=30)
        
        self.results[host.config['ip']] = {
            "config": host.config,
            "software_count": len(software),
            "software_sample": software[:5],
            "vulnerable_software_count": len(vulns),
            "vulnerable_software": vulns,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"\nИТОГИ: ПО={len(software)}, УЯЗВИМО={len(vulns)}")
    
    def save_report(self, filename: str = None) -> str:
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cve_scan_report_{timestamp}.json"
        
        full_path = DATA_DIR / filename
        
        total_software = sum(r.get('software_count', 0) for r in self.results.values())
        total_vulnerable = sum(r.get('vulnerable_software_count', 0) for r in self.results.values())
        
        full_report = {
            "scan_time": datetime.now().isoformat(),
            "total_hosts": len(self.hosts),
            "successful_scans": len([r for r in self.results.values() if 'error' not in r]),
            "failed_scans": len([r for r in self.results.values() if 'error' in r]),
            "results": self.results,
            "summary": {
                "total_software": total_software,
                "total_vulnerable": total_vulnerable,
                "vulnerability_rate": f"{(total_vulnerable/total_software*100):.1f}%" if total_software else "0%"
            }
        }
        
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(full_report, f, indent=2, ensure_ascii=False)
        
        print(f"\n[OK] Отчет сохранен: {full_path}")
        return str(full_path)


def load_hosts_from_file(filename: str) -> List[Dict]:
    file_path = Path(filename)
    if not file_path.exists():
        file_path = BASE_DIR / filename
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Файл {filename} не найден")
        return []
    except json.JSONDecodeError as e:
        print(f"[ERROR] Ошибка в JSON: {e}")
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hosts', type=str, default='hosts.json')
    parser.add_argument('--output', type=str)
    parser.add_argument('--max-per-host', type=int, default=30)
    args = parser.parse_args()
    
    if not MCP_AVAILABLE:
        print("\n[ERROR] MCP сервер не доступен. Работа невозможна.")
        print("\nВыполните команду для установки:")
        print(f"cd {CVE_SEARCH_PATH}")
        print("pip install -e .")
        print("\nИли проверьте структуру модуля и исправьте импорт вручную.")
        return
    
    hosts_config = load_hosts_from_file(args.hosts)
    if not hosts_config:
        print("\nСоздайте файл hosts.json:")
        print("""
[
    {
        "ip": "192.168.10.20",
        "os": "linux",
        "username": "root",
        "password": "password",
        "port": 22
    }
]
        """)
        return
    
    print(f"\nЗагружено хостов: {len(hosts_config)}")
    for h in hosts_config:
        print(f"  - {h['ip']} ({h['os']})")
    
    orchestrator = Orchestrator(hosts_config)
    orchestrator.scan_all()
    
    if args.output:
        if os.path.sep in args.output:
            output_path = args.output
        else:
            output_path = DATA_DIR / args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = DATA_DIR / f"cve_scan_report_{timestamp}.json"
    
    orchestrator.save_report(str(output_path))
    
    print(f"\nСКАНИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"Отчет: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        print(f"\n[ERROR] {e}")