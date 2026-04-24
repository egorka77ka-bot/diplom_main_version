#!/usr/bin/env python3
"""
Скачивание всех необходимых зависимостей для офлайн работы.
Запустить один раз при наличии интернета.
"""

import subprocess
import sys
import os

print("=" * 50)
print("СКАЧИВАНИЕ ВСЕХ ЗАВИСИМОСТЕЙ ДЛЯ ОФЛАЙН РАБОТЫ")
print("=" * 50)

# 1. Скачивание модели sentence-transformers
print("\n[1/4] Скачивание модели sentence-transformers (all-MiniLM-L6-v2)...")
try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    print("Модель успешно скачана и сохранена в кэше")
except Exception as e:
    print(f"Ошибка при скачивании модели: {e}")
    print("Попробуйте установить: pip install sentence-transformers")

# 2. Установка базовых зависимостей
print("\n[2/4] Установка базовых зависимостей...")
base_packages = [
    "requests",
    "numpy",
    "faiss-cpu",
    "langchain",
    "langchain-ollama",
    "langchain-core",
    "fastapi",
    "uvicorn",
    "pypdf2",
    "docx2txt",
    "ollama",
    "rich",
    "tiktoken"
]

for package in base_packages:
    print(f"  Установка {package}...")
    subprocess.run([sys.executable, "-m", "pip", "install", package], 
                   capture_output=True, check=False)

# 3. Установка зависимостей для CVE сканера
print("\n[3/4] Установка зависимостей для CVE сканера...")
cve_packages = ["requests", "json5", "packaging"]
for package in cve_packages:
    print(f"  Установка {package}...")
    subprocess.run([sys.executable, "-m", "pip", "install", package], 
                   capture_output=True, check=False)

# 4. Установка дополнительных зависимостей для RAG
print("\n[4/4] Установка зависимостей для RAG...")
rag_packages = ["pypdf", "python-docx", "openpyxl", "pandas"]
for package in rag_packages:
    print(f"  Установка {package}...")
    subprocess.run([sys.executable, "-m", "pip", "install", package], 
                   capture_output=True, check=False)

print("\n" + "=" * 50)
print("ВСЕ ЗАВИСИМОСТИ СКАЧАНЫ")
print("=" * 50)
print("\nТеперь можно работать в офлайн режиме!")
print("\nДля проверки запустите:")
print("  python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')\"")