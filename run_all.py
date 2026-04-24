#!/usr/bin/env python3

import subprocess
import sys
import time
import shutil
import signal
import atexit
from pathlib import Path

# ================ ПУТИ ================

BASE_DIR = Path(__file__).parent

# Сканеры
NMAP_DIR = BASE_DIR / "mcp-vulnerability-scanner"
NMAP_SCRIPT = NMAP_DIR / "SCRIPT.py"
CVE_DIR = BASE_DIR / "CVE-Search-MCP"
CVE_SCRIPT = CVE_DIR / "scan_hosts.py"
CVE_HOSTS = CVE_DIR / "hosts.json"

# РАГ
RAG_DIR = BASE_DIR / "local-rag-mcp"
RAG_SRC = RAG_DIR / "src"
RAG_MAIN = RAG_SRC / "main.py"
RAG_DOCS = RAG_SRC / "docs"

# Основной код
THREAT_MODELING = BASE_DIR / "threat_modeling.py"

# Глобальная переменная для хранения процесса RAG сервера
rag_process = None

# Остановка сервера РАГ

def kill_process_on_port(port: int = 8080):
    # Остановка сервера РАГ по порту
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True
        )
        
        for line in result.stdout.split('\n'):
            if f":{port}" in line and "проверка" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    print(f" Найден процесс на порту {port} (PID: {pid})")
                    #Запускает taskkill /F /PID <pid> для принудительного завершения процесса.
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                    print(f" Процесс {pid} завершен")
                    return True
    except Exception as e:
        print(f" Ошибка поиска процесса на порту {port}: {e}")
    return False


def kill_powershell_with_uvicorn():
    # Остановка сервера РАГ через закрытие окна с работающим uvicorn
    try:
        # Ищем процессы и проверяем командную строку
        result = subprocess.run(
            ["wmic", "process", "where", "name='powershell.exe'", "get", "processid,commandline"],
            capture_output=True,
            text=True
        )
        
        for line in result.stdout.split('\n'):
            if 'uvicorn' in line.lower() or 'main:app' in line:
                parts = line.strip().split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        print(f" Найдено окно PowerShell с uvicorn (PID: {pid})")
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                        print(f" Окно закрыто")
    except Exception as e:
        print(f" Ошибка при поиске окон PowerShell: {e}")


def cleanup_rag_server():
    # Останвливает РАГ полностью и вызывается при любом завершении программы
    global rag_process, rag_window_pid_file
    
    print(" Остановка RAG сервера...")
    
    # Завершаем процесс, если он был запущен через Popen
    if rag_process:
        try:
            rag_process.terminate()
            rag_process.wait(timeout=3)
            print(" Процесс завершен")
        except:
            try:
                rag_process.kill()
                print(" Процесс завершен")
            except:
                pass
    
    # Убиваем процесс на порту 8080
    kill_process_on_port(8080)
        
    # Убиваем процессы python, связанные с uvicorn
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe' and commandline like '%uvicorn%'", "get", "processid"],
            capture_output=True,
            text=True
        )
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line and line.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", line], capture_output=True)
                print(f" Процесс python с uvicorn (PID: {line}) завершен")
    except:
        pass
    
    # Закрываем окна PowerShell с uvicorn
    kill_powershell_with_uvicorn()
# Завершение работы вручную
def signal_handler(signum, frame):
    cleanup_rag_server()
    print(" Завершение программы...")
    sys.exit(0)

# Завершение работы сервера при ошибке работы основного кода
def exception_hook(exc_type, exc_value, exc_traceback):
    print("\n" + "=" * 70)
    print("Ошибка")
    print(f"Тип: {exc_type.__name__}")
    print(f"Сообщение: {exc_value}")
    cleanup_rag_server()

atexit.register(cleanup_rag_server)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
sys.excepthook = exception_hook


# ================ ШАГИ ПАЙПЛАЙНА ================

def nmap():
    print("ШАГ 1/6: Nmap сканирование сети")
    
    if not NMAP_SCRIPT.exists():
        print(f" Nmap скрипт не найден: {NMAP_SCRIPT}")
        return False
    
    print(f" Запуск: {NMAP_SCRIPT}")
    result = subprocess.run(
        [sys.executable, str(NMAP_SCRIPT)],
        cwd=str(NMAP_DIR)
    )
    
    if result.returncode != 0:
        print(" Nmap завершился с кодом {}".format(result.returncode))
    else:
        print(" Nmap сканирование завершено")
    
    return True


def cve():
    print("ШАГ 2/6: CVE сканирование уязвимостей")
    
    if not CVE_SCRIPT.exists():
        print(f" CVE агент не найден: {CVE_SCRIPT}")
        return False
    
    if not CVE_HOSTS.exists():
        print(f" Файл hosts.json не найден: {CVE_HOSTS}")
        print(" Пропуск CVE сканирования...")
        return True
    
    print(f" Запуск CVE агента")
    result = subprocess.run(
        ["uv", "run", "python", "scan_hosts.py", "--hosts", "hosts.json"],
        cwd=str(CVE_DIR)
    )
    
    if result.returncode != 0:
        print("Анализ CVE завершился с кодом {}".format(result.returncode))
    else:
        print("Сканирование завершено")
    
    return True


def copy_to_rag():
    print("ШАГ 3/6: Копирование результатов в RAG docs")
        
    RAG_DOCS.mkdir(parents=True, exist_ok=True)
    
    copied = 0
    
    # Копируем scan_*.json из mcp-vulnerability-scanner
    for pattern in ["scan_*.json", "*scan*.json", "nmap_*.json"]:
        for f in NMAP_DIR.glob(pattern):
            dest = RAG_DOCS / f.name
            shutil.copy2(f, dest)
            print(f" Скопирован: {f.name}")
            copied += 1
    
    # Копируем cve_*.json из CVE-Search-MCP
    for pattern in ["cve_*.json", "*cve*.json", "vulnerabilities*.json"]:
        for f in CVE_DIR.glob(pattern):
            dest = RAG_DOCS / f.name
            shutil.copy2(f, dest)
            print(f" Скопирован: {f.name}")
            copied += 1
    
    # Копируем hosts.json
    if CVE_HOSTS.exists():
        shutil.copy2(CVE_HOSTS, RAG_DOCS / "hosts.json")
        print(" Скопирован: hosts.json")
        copied += 1
    
    print(f" Скопировано файлов: {copied}")
    return True


def rag_build_index():
    print("ШАГ 4/6: Построение FAISS индекса")
    
    print(f"Запуск: python main.py build-index")
    result = subprocess.run(
        [sys.executable, "main.py", "build-index"],
        cwd=str(RAG_SRC)
    )
    
    if result.returncode != 0:
        print(" Индексация завершилась с ошибкой")
        return False
    
    print(" Индекс RAG построен")
    return True


def rag_server():
    
    global rag_process
    
    print("ШАГ 5/6: Запуск RAG сервера (новое окно PowerShell)")
    
    # Команда для запуска в PowerShell
    ps_command = f"""
$windowPid = [System.Diagnostics.Process]::GetCurrentProcess().Id
Write-Host 'Запуск сервера RAG...' -ForegroundColor Yellow
Write-Host ''
cd '{RAG_SRC}'
uvicorn main:app --host 0.0.0.0 --port 8080
"""
    
    print(f" Запуск PowerShell в новом окне")
    
    # Запускаем PowerShell в новом окне
    rag_process = subprocess.Popen(
        ["powershell", "-NoExit", "-Command", ps_command],
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    )
    
    print(f" Окно PowerShell открыто")
    print(" Ожидание готовности сервера (20 секунд)...")
    
    # Ждем загрузку модели и индекса
    time.sleep(20)
    
    # Проверяем доступность
    print(" Проверка доступности сервера...")
    max_attempts = 15
    for attempt in range(max_attempts):
        try:
            import requests
            response = requests.get("http://localhost:8080/health", timeout=2)
            if response.status_code == 200:
                print(f" RAG сервер готов к работе!")
                return rag_process
        except:
            time.sleep(2)
            if attempt % 3 == 2:
                print(f" Ожидание сервера... ({attempt + 1}/{max_attempts})")
    
    print(" Сервер не отвечает")
    print(" Повторная попытка через 10 секунд...")
    time.sleep(10)
    
    return rag_process


def threat_modeling():
    print("ШАГ 6/6: Генерация отчета по моделированию угроз")
    
    if not THREAT_MODELING.exists():
        print(f" Основной модуль системы не найден: {THREAT_MODELING}")
        return False
    
    print(f" Запуск: {THREAT_MODELING.name}")
    print("=" * 70)
    
    result = subprocess.run(
        [sys.executable, str(THREAT_MODELING)],
        cwd=str(BASE_DIR)
    )
    
    if result.returncode != 0:
        print("\n Генерация отчета завершилась с ошибкой")
        return False
    
    print("\n Отчет сгенерирован успешно")
    return True

def main():
    print("=" * 70)
    print("АВТОМАТИЧЕСКИЙ ПАЙПЛАЙН МОДЕЛИРОВАНИЯ УГРОЗ")
    print("=" * 70)
    
    try:
        # Шаг 1: Nmap
        if not nmap():
            print("\n Продолжение с ошибкой в Nmap...")
        
        # Шаг 2: CVE
        if not cve():
            print("\n Продолжение с ошибкой в CVE...")
        
        # Шаг 3: Копирование в RAG
        copy_to_rag()
        
        # Шаг 4: Индексация RAG
        if not rag_build_index():
            print("\n Не удалось построить индекс RAG")
            return
        
        # Шаг 5: Запуск RAG сервера в новом окне
        rag_server()
        
        # Шаг 6: Генерация отчета
        threat_modeling()
        
    except KeyboardInterrupt:
        print("\n\n Выполнение прервано пользователем")
    except Exception as e:
        print(f"\n Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    print("Завершение работы...")
    print(f"\nРезультаты в: {BASE_DIR / 'model_results'}")


if __name__ == "__main__":
    main()