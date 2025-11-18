import asyncio
import logging

from services.knowledge_graph import extract_triplets_from_texts
from services.llm_client import evaluate_source, summarize_text
from services.memory_manager import MemoryManager
from services.multi_retriever import search_and_extract

logger = logging.getLogger(__name__)

memory = MemoryManager()


def run_research_task(topic: str, user_id: str):
    """
    Full auto-research pipeline run by APScheduler (sync).
    Async functions are wrapped using asyncio.run().
    """
    logger.info(f"[TASK] Running auto-research for '{topic}' (user={user_id})")

    # -------- 1. Search & Extraction --------
    articles = search_and_extract(topic)
    if not articles:
        logger.warning(f"[TASK] No articles found for '{topic}'")
        return

    results_out = []
    texts_for_kg = []

    # -------- 2. Process each article --------
    for art in articles:
        raw_text = art.get("snippet", "") or art.get("text", "")

        # Summarize (sync) through LLM
        summary = summarize_text(raw_text)

        # Evaluate credibility (sync)
        credibility = evaluate_source(art.get("url", ""), raw_text)

        results_out.append(
            {
                "title": art.get("title"),
                "url": art.get("url"),
                "summary": summary,
                "credibility": credibility,
                "provider": art.get("provider"),
            }
        )

        texts_for_kg.append(summary)

        # -------- 3. Save into Pinecone Memory --------
        try:
            asyncio.run(
                memory.upsert_text(
                    user_id=user_id,
                    text=summary,
                    url=art.get("url", ""),
                    title=art.get("title", ""),
                )
            )
        except Exception as e:
            logger.error(f"[TASK:MEMORY] Error saving memory: {e}")

    # -------- 4. Generate Knowledge Graph --------
    kg = extract_triplets_from_texts(texts_for_kg)

    logger.info(
        f"[TASK] Completed research for '{topic}': "
        f"{len(results_out)} articles, "
        f"KG nodes={kg['counts']['nodes']}, edges={kg['counts']['edges']}"
    )
