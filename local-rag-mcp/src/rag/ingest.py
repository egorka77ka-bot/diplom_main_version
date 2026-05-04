from pathlib import Path
from pypdf import PdfReader
import docx2txt
import sys
from datetime import datetime
import pandas as pd
import json
import os

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DOCUMENTS_DIR

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".xlsx", ".json", ".doc"}

# Загрузка данных документа и фрмирование метаданных
def load_document(path: Path):
    """Load document content and extract metadata."""
    stat = path.stat()
    
    metadata = {
        "source": str(path),
        "filename": path.name,
        "extension": path.suffix,
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
    }
    
    if path.suffix in [".txt", ".md", ".csv"]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        
    elif path.suffix == ".pdf":
        reader = PdfReader(path)
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
        text = "\n".join(pages_text)
        
    elif path.suffix == ".docx":
        text = docx2txt.process(str(path))
        
    elif path.suffix == ".doc":
        # Пробуем через antiword
        try:
            result = subprocess.run(
                ["antiword", str(path)],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout
            else:
                # Fallback: пробуем через catdoc если antiword не сработал
                result = subprocess.run(
                    ["catdoc", str(path)],
                    capture_output=True, text=True, timeout=30
                )
                text = result.stdout if result.returncode == 0 else ""
        except Exception as e:
            print(f"   Warning: Could not read .doc file {path.name}: {e}")
            text = ""
            
    elif path.suffix in [".xlsx", ".xls"]:
        try:
            # Читаем все листы Excel файла
            df_dict = pd.read_excel(path, sheet_name=None, engine='openpyxl')
            text_parts = []
            for sheet_name, df in df_dict.items():
                if not df.empty:
                    text_parts.append(f"=== Лист: {sheet_name} ===")
                    text_parts.append(df.to_string(index=False))
            text = "\n".join(text_parts)
        except Exception as e:
            print(f"   Warning: Could not read Excel file {path.name}: {e}")
            text = ""
            
    elif path.suffix == ".json":
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            text = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"   Warning: Could not read JSON file {path.name}: {e}")
            text = ""
    else:
        text = ""
    
    return text, metadata

# Функция чтение и загрузки всех файлов и папки
def ingest_documents():
    documents = []

    base_dir = Path(DOCUMENTS_DIR)
    if not base_dir.exists():
        print(f"Папка с файлами отсутствует")
        return documents

    # Рекурсивный обход всех вложенных папок
    for path in base_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            print(f"Loading: {path.name}")
            try:
                text, metadata = load_document(path)
                if text and len(text.strip()) > 0:
                    documents.append({
                        "path": str(path),
                        "text": text,
                        "metadata": metadata
                    })
                else:
                    print(f"   Skipping: {path.name} (no text content)")
            except Exception as e:
                print(f"Error loading {path.name}: {e}")

    return documents


if __name__ == "__main__":
    docs = ingest_documents()
    print(f"Found {len(docs)} documents")
    for doc in docs:
        print(f"  - {Path(doc['path']).name}: {len(doc['text'])} chars")