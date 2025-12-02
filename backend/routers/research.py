# routers/research.py

from fastapi import APIRouter, Query
from typing import Optional, List, Dict

# Services
from services.knowledge_graph import extract_knowledge_graph
from services.memory_manager import MemoryManager
from services.rag_pipeline import RAGPipeline
from services.conversations import get_conversation
from services.synthesizer import synthesize_answer 
from services.llm_client import summarize_text, evaluate_source 

router = APIRouter()
mm = MemoryManager()
rag = RAGPipeline()

# --- Helper to Merge KGs ---
def merge_knowledge_graphs(old_kg: Dict, new_kg: Dict) -> Dict:
    """Merges two Knowledge Graphs (Nodes and Edges)."""
    # If one is missing, return the other
    if not old_kg: return new_kg
    if not new_kg: return old_kg

    # 1. Merge Nodes (Deduplicate by ID)
    node_map = {n["data"]["id"]: n for n in old_kg.get("nodes", [])}
    for n in new_kg.get("nodes", []):
        node_map[n["data"]["id"]] = n # Overwrite/Add
    
    # 2. Merge Edges (Deduplicate by source+target+label)
    edge_set = set()
    final_edges = []
    
    # Add old edges
    for e in old_kg.get("edges", []):
        key = (e["data"]["source"], e["data"]["target"], e["data"]["label"])
        edge_set.add(key)
        final_edges.append(e)
        
    # Add new edges
    for e in new_kg.get("edges", []):
        key = (e["data"]["source"], e["data"]["target"], e["data"]["label"])
        if key not in edge_set:
            edge_set.add(key)
            final_edges.append(e)

    return {
        "nodes": list(node_map.values()),
        "edges": final_edges,
        "counts": {"nodes": len(node_map), "edges": len(final_edges)}
    }

@router.get("/research", tags=["pipeline"])
async def run_research(
    topic: str = Query(...), 
    user_id: str = Query("demo"),
    conversation_id: Optional[str] = Query(None),
    deep_research: bool = Query(False)
):
    # 1. Get Context & Previous KG
    conversation_history = []
    previous_kg = {}
    
    if conversation_id:
        try:
            conv_data = get_conversation(conversation_id, limit=10)
            conversation_history = conv_data.get("messages", [])
            # Find the last KG in history to merge with
            for msg in reversed(conversation_history):
                if msg.get("role") == "agent" and msg.get("meta", {}).get("kg"):
                    previous_kg = msg["meta"]["kg"]
                    break
        except Exception as e:
            print(f"[WARN] Failed to load history: {e}")

    # 2. RAG Retrieval
    max_results = 10 if deep_research else 4
    rag_result = await rag.retrieve(topic, user_id, conversation_history, max_results)
    articles = rag_result["sources"]
    
    processed_sources = []
    
    # 3. Process & Evaluate Sources
    for art in articles:
        raw_text = art.get("text") or art.get("snippet") or art.get("summary") or ""
        
        # Summary & Credibility
        if art.get("source") == "cached" and art.get("summary"):
            summary_text = art["summary"]
            credibility = art.get("score", 0.5)
        else:
            summary_text = summarize_text(raw_text)
            credibility = evaluate_source(
                url=art.get("url", ""),
                content=raw_text,
                title=art.get("title", ""),
                topic=topic
            )

        # Upsert with Context
        if art.get("source") != "cached":
            await mm.upsert_text(
                user_id=user_id, 
                text=summary_text, 
                url=art.get("url", ""), 
                title=art.get("title", ""),
                conversation_id=conversation_id or "global",
                topic=topic
            )

        processed_sources.append({
            "title": art.get("title"),
            "url": art.get("url"),
            "summary": summary_text, 
            "credibility": credibility, 
            "source": art.get("source"),
            "provider": art.get("source") 
        })

    # 4. Generate & Merge Knowledge Graph (Fixed)
    # ---------------------------------------------------------
    combined_text = "\n".join([p["summary"] for p in processed_sources])
    
    # Extract KG from the new text
    new_kg = await extract_knowledge_graph(combined_text[:6000])
    
    # Merge with the previous conversation KG so the graph grows
    final_kg = merge_knowledge_graphs(previous_kg, new_kg)
    # ---------------------------------------------------------

    # 5. Synthesize Answer
    final_answer = await synthesize_answer(topic, processed_sources, conversation_history)

    return {
        "topic": topic,
        "answer": final_answer,
        "results": processed_sources,
        "knowledge_graph": final_kg, # ✅ Now contains the merged graph
        "metadata": {"strategy": rag_result["retrieval_strategy"]}
    }