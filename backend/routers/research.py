from fastapi import APIRouter, Query

from services.critic import evaluate_source
from services.knowledge_graph import extract_triplets_from_texts
from services.memory_manager import MemoryManager

# Unified multi-provider retriever
from services.multi_retriever import search_and_extract

# Updated imports
from services.summarizer import summarize_article

router = APIRouter()
mm = MemoryManager()


@router.get("/research", tags=["pipeline"])
async def run_research(topic: str = Query(...), user_id: str = Query("demo")):
    """
    Full Research Pipeline:
    1. Search topic
    2. Summarize content using new summarizer
    3. Evaluate credibility
    4. Store in vector memory
    5. Generate Knowledge Graph
    """
    articles = search_and_extract(topic)
    processed, summaries = [], []

    for art in articles:
        # Safely extract text
        text_to_summarize = (
            art.get("summary") or art.get("text") or art.get("snippet") or ""
        )

        if not text_to_summarize:
            print(f"[WARN] Skipping article without text: {art.get('title')}")
            continue

        # 🔄 NEW Summarization function
        summary = summarize_article(text_to_summarize)

        # Credibility evaluation
        credibility = evaluate_source(art.get("url", ""), summary)

        # Store in memory (vector DB or Pinecone)
        await mm.upsert_text(
            user_id, summary, art.get("url", ""), art.get("title", "Untitled")
        )

        processed.append(
            {
                "title": art.get("title", "Untitled"),
                "url": art.get("url", ""),
                "summary": summary,
                "credibility": credibility,
            }
        )
        summaries.append(summary)

    # Generate Knowledge Graph
    kg = []
    if summaries:
        try:
            kg = extract_triplets_from_texts(summaries)
        except Exception as e:
            print(f"[ERROR] Knowledge Graph extraction failed: {e}")
            kg = []

    return {
        "topic": topic,
        "results": processed,
        "count": len(processed),
        "knowledge_graph": kg,
    }
