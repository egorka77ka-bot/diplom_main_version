#!/usr/bin/env python3
from fastapi import FastAPI, Query
from pydantic import BaseModel
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path

# Настройка путей до импорта локальных модулей
sys.path.insert(0, str(Path(__file__).parent))

from assistant import CompanyKBAssistant
from rag.query import retrieve_with_metadata


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "build-index":
        # Build index mode
        from rag.build_index import build_index
        build_index()
        return
    
    # Interactive Q&A mode
    assistant = CompanyKBAssistant()
    
    print("Company Knowledge Base Assistant")
    print("\nAsk questions about company policies, procedures, and documentation.")
    print("Type 'exit' or 'quit' to stop\n")
    
    try:
        while True:
            query = input(" Question: ").strip()
            
            if not query:
                continue
                
            if query.lower() in {"exit", "quit", "q"}:
                print("\n Goodbye!")
                break
            
            print("\n" + "─" * 60)
            print(" Answer:\n")
            
            try:
                result = assistant.query(query, verbose=True)
                print(result["answer"])
                
                if result["sources"]:
                    print("\n Sources:")
                    for src in result["sources"]:
                        print(f"  • {src}")
                
                if result["mcp_used"]:
                    print(f"\n Used MCP tool: {result['mcp_tool']}")
                
            except Exception as e:
                print(f" Error: {e}")
                import traceback
                traceback.print_exc()
    
    except KeyboardInterrupt:
        print("\n\n Goodbye!")
    finally:
        assistant.close()


# FastAPI app
app = FastAPI(title="Company Knowledge Base RAG API")

class QueryRequest(BaseModel):
    question: str
    k: Optional[int] = 5

@app.get("/")
def root():
    return {
        "status": "RAG server running",
        "endpoints": ["GET /query", "POST /query", "/health"]
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/query")
async def query_get(q: str = Query(..., description="Search query"), k: int = Query(5, description="Number of results")):
    """
    GET endpoint for RAG queries.
    Returns relevant chunks with metadata.
    """
    try:
        results = retrieve_with_metadata(q, k)
        
        formatted_results = []
        for r in results:
            formatted_results.append({
                "text": r.get("text", ""),
                "source": r.get("source", "unknown"),
                "metadata": r.get("metadata", {}),
                "score": r.get("score", 0),
                "chunk_id": r.get("chunk_id", "?")
            })
        
        return {
            "query": q,
            "results": formatted_results,
            "count": len(formatted_results)
        }
    except Exception as e:
        return {
            "error": str(e),
            "query": q,
            "results": []
        }

@app.post("/query")
def query_post(q: QueryRequest):
    """
    POST endpoint for RAG queries.
    Returns answer and sources.
    """
    from rag.query import ask
    
    try:
        answer, sources = ask(q.question)
        
        formatted_sources = []
        for src in sources:
            formatted_sources.append({
                "text": src.get("text", "")[:200] + "..." if len(src.get("text", "")) > 200 else src.get("text", ""),
                "source": src.get("source", "unknown"),
                "metadata": src.get("metadata", {}),
                "score": src.get("score", 0)
            })
        
        return {
            "answer": answer,
            "sources": formatted_sources,
            "count": len(formatted_sources)
        }
    except Exception as e:
        return {
            "error": str(e),
            "answer": "",
            "sources": []
        }


if __name__ == "__main__":
    main()