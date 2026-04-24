import json
import ollama
import sys
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

# Добавляем текущую директорию в путь для импортов
sys.path.insert(0, str(Path(__file__).parent))
from rag.query import retrieve, build_prompt, ask_llm
from mcp.client import MCPClient
from config import OLLAMA_MODEL

class CompanyKBAssistant:
        
    def __init__(self):
        self.llm_client = ollama.Client()
        self.mcp = None
        self._init_mcp()
    # Запуск MCP агента    
    def _init_mcp(self):
        
        try:
            import sys
            from pathlib import Path
            python_cmd = sys.executable
            # Получаем путь к MCP серверу
            mcp_path = Path(__file__).parent / "mcp" / "server.py"
            self.mcp = MCPClient([python_cmd, str(mcp_path)])
        except Exception as e:
            print(f" Предупреждение: Не удалось инициализировать MCP клиент: {e}")
            self.mcp = None
    
    def _llm_decide_mcp_usage(self, query: str, contexts):
        """Запрос к LLM о необходимости использования MCP инструментов на основе запроса и полученных контекстов."""
        if not self.mcp:
            return None, None
        
        # Формируем сводку контекста для принятия решения LLM
        context_summary = ""
        if contexts:
            context_summary = f" Получено {len(contexts)} соответствующих фрагментов из базы знаний:\n"
            for i, ctx in enumerate(contexts[:3], 1):  
                # Показываем первые 3 фрагмента
                context_summary += f"{i}. Из {ctx['source']}: {ctx['text'][:200]}...\n"
        else:
            context_summary = "Соответствующие фрагменты в базе знаний не найдены.\n"
        
        decision_prompt = f""" Ты помогаешь отвечать на вопросы, используя систему базы знаний с RAG (поиск) и MCP инструментами.

Вопрос пользователя: {query}

{context_summary}

Доступные MCP инструменты:
1. read_document(file_path: str) - Прочитать конкретный файл документа (используй, когда нужно полное содержание документа)
2. list_documents() - Показать список всех доступных документов (используй, когда пользователь спрашивает "какие есть документы" или "покажи все документы")
3. search_documents(query: str) - Поиск документов по названию (используй, когда пользователь просит найти конкретный документ)

Правила принятия решения:
- Если полученные фрагменты полностью отвечают на вопрос, установи use_mcp в false
- Если фрагменты пусты или недостаточны, рассмотри использование MCP инструментов
- Если пользователь явно просит прочитать/показать/найти документы, используй соответствующий инструмент
- Если нужно полное содержание конкретного документа, упомянутого во фрагментах, используй read_document
- В случае сомнений, предпочти не использовать MCP (обычно фрагментов достаточно)

Отвечай ТОЛЬКО корректным JSON, без дополнительного текста:
{{"use_mcp": true/false, "tool": "имя_инструмента_или_null", "args": {{"имя_аргумента": "значение"}}}}

Примеры:
{{"use_mcp": false, "tool": null, "args": {{}}}}
{{"use_mcp": true, "tool": "read_document", "args": {{"file_path": "docs/vacation-policy.md"}}}}
{{"use_mcp": true, "tool": "list_documents", "args": {{}}}}
{{"use_mcp": true, "tool": "search_documents", "args": {{"query": "отпуск"}}}}

Твой JSON ответ:"""

        try:
            response = self.llm_client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": "Ты полезный ассистент, который решает, когда использовать инструменты. Всегда отвечай только корректным JSON."},
                    {"role": "user", "content": decision_prompt}
                ]
            )
            
            response_text = response["message"]["content"].strip()
            
            # Очищаем JSON, если он обернут в markdown
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            decision = json.loads(response_text)
            
            if decision.get("use_mcp", False):
                tool_name = decision.get("tool")
                tool_args = decision.get("args", {})
                return tool_name, tool_args
            
            return None, None
            
        except Exception as e:
            # Если решение LLM не удалось, не используем MCP
            return None, None
    
    def _call_mcp_tool(self, tool_name: str, tool_args: dict):
        """Вызов MCP инструмента с указанным именем и аргументами."""
        if not self.mcp:
            return None
        
        try:
            result = self.mcp.call_tool(tool_name, tool_args)
            return result.get("result", "")
        except Exception as e:
            return f" Ошибка вызова MCP инструмента {tool_name}: {str(e)}"
    
    def query(self, user_query: str, verbose=False):
        """Ответ на вопрос с использованием RAG и опционально MCP инструментов."""
        # Шаг 1: Получение данных из RAG
        contexts = retrieve(user_query)
        
        if verbose:
            print(f" Получено {len(contexts)} релевантных фрагментов из базы знаний")
        
        # Шаг 2: Запрос к LLM о необходимости MCP инструментов
        mcp_result = None
        mcp_tool_used = None
        tool_name, tool_args = self._llm_decide_mcp_usage(user_query, contexts)
        
        if tool_name:
            if verbose:
                print(f" LLM решил использовать MCP инструмент: {tool_name} с аргументами: {tool_args}")
            mcp_result = self._call_mcp_tool(tool_name, tool_args)
            mcp_tool_used = tool_name
            if verbose and mcp_result:
                print(f" MCP инструмент вернул результат (длина: {len(mcp_result)} символов)")
        
        # Шаг 3: Формирование промпта с контекстом RAG
        prompt = build_prompt(user_query, contexts)
        
        # Шаг 4: Добавление результата MCP, если доступен
        if mcp_result:
            prompt += f"\n\n<additional_info_from_mcp_tool>\n{mcp_result}\n</additional_info_from_mcp_tool>\n"
        
        # Шаг 5: Генерация ответа
        answer = ask_llm(prompt)
        
        # Шаг 6: Подготовка ответа с источниками
        sources = [c["source"] for c in contexts] if contexts else []
        
        return {
            "answer": answer,
            "sources": sources,
            "mcp_used": mcp_result is not None,
            "mcp_tool": mcp_tool_used
        }
    
    def close(self):
        if self.mcp:
            self.mcp.close()


if __name__ == "__main__":
    assistant = CompanyKBAssistant()
    
    print(" Ассистент базы знаний компании")
    print(" Введите 'exit' или 'quit' для выхода\n")
    
    try:
        while True:
            query = input(" Вопрос: ")
            if query.lower() in {"exit", "quit"}:
                break
            
            print("\n" + "─" * 60)
            result = assistant.query(query, verbose=True)
            
            print("\n Ответ:\n")

            console = Console(force_terminal=True)
            console.print(Markdown(result["answer"]))
            
            if result["sources"]:
                print("\n Источники:")
                seen_sources = set()
                for src in result["sources"]:
                    if src not in seen_sources:
                        print(f"  • {src}")
                        seen_sources.add(src)
            
            if result["mcp_used"]:
                print(f"\n Использован MCP инструмент: {result['mcp_tool']}")
            
            print("─" * 60 + "\n")
    
    finally:
        assistant.close()