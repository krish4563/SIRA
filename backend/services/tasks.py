# services/tasks.py

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from services.knowledge_graph import extract_triplets_from_texts
from services.llm_client import evaluate_source, summarize_text
from services.memory_manager import MemoryManager
from services.multi_retriever import search_and_extract
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

memory = MemoryManager()

# ----------------------------------------------------
# Helpers
# ----------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _insert_history_row(
    user_id: str,
    topic: str,
    job_id: Optional[str],
    status: str,
    result_count: int,
    kg_nodes: int,
    kg_edges: int,
    error_message: Optional[str],
    run_started_at: datetime,
    run_finished_at: datetime,
    full_summary_text: str,  # <-- NEW
):
    """Insert history row + update job metadata."""

    sb = get_supabase()

    # Insert row in history table
    sb.table("auto_research_history").insert(
        {
            "job_id": job_id,
            "user_id": user_id,
            "topic": topic,
            "status": status,
            "result_count": result_count,
            "kg_nodes": kg_nodes,
            "kg_edges": kg_edges,
            "error_message": error_message,
            "run_started_at": run_started_at.isoformat(),
            "run_finished_at": run_finished_at.isoformat(),
            "full_summary_text": full_summary_text,  # <-- NEW field stored
        }
    ).execute()

    # Update job table with last run metadata
    if job_id:
        sb.table("auto_research_jobs").update(
            {
                "last_run_at": run_finished_at.isoformat(),
                "last_status": status,
            }
        ).eq("id", job_id).execute()


# ----------------------------------------------------
# Main Pipeline Task
# ----------------------------------------------------


def run_research_task(topic: str, user_id: str, job_id: Optional[str] = None):
    """
    Full auto-research pipeline.
    Called via APScheduler with args (topic, user_id, job_id).
    """
    start_ts = _now_utc()
    logger.info(
        "[TASK] Auto-research started for '%s' (user=%s, job_id=%s)",
        topic,
        user_id,
        job_id,
    )

    status = "running"
    error_message: Optional[str] = None
    result_count = 0
    kg_nodes = 0
    kg_edges = 0

    # We will store all summaries here for later LLM diff
    summaries_for_history: list[str] = []

    try:
        # -------- 1. Search & Extraction --------
        articles = search_and_extract(topic)

        if not articles:
            logger.warning("[TASK] No articles found for '%s'", topic)
            status = "success"  # run technically succeeded
            return

        results_out = []
        texts_for_kg = []

        # -------- 2. Process each article --------
        for art in articles:
            raw_text = art.get("snippet", "") or art.get("text", "")
            if not raw_text:
                continue

            # Summarization
            summary = summarize_text(raw_text)

            # Evaluation
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

            # For knowledge graph + history record
            texts_for_kg.append(summary)
            summaries_for_history.append(summary)

            # -------- 3. Push into Pinecone Memory --------
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
                logger.error("[TASK:MEMORY] Error saving memory: %s", e)

        result_count = len(results_out)

        # -------- 4. Knowledge Graph --------
        kg = extract_triplets_from_texts(texts_for_kg)
        kg_nodes = kg.get("counts", {}).get("nodes", 0)
        kg_edges = kg.get("counts", {}).get("edges", 0)

        logger.info(
            "[TASK] Completed research for '%s': %d articles | KG nodes=%d edges=%d",
            topic,
            result_count,
            kg_nodes,
            kg_edges,
        )

        status = "success"

    except Exception as e:
        logger.exception("[TASK] Error during auto-research for '%s': %s", topic, e)
        status = "error"
        error_message = str(e)

    finally:
        end_ts = _now_utc()

        # Store combined summaries for LLM diff
        combined_summary_text = "\n\n".join(summaries_for_history)

        # Save to DB
        try:
            _insert_history_row(
                user_id=user_id,
                topic=topic,
                job_id=job_id,
                status=status,
                result_count=result_count,
                kg_nodes=kg_nodes,
                kg_edges=kg_edges,
                error_message=error_message,
                run_started_at=start_ts,
                run_finished_at=end_ts,
                full_summary_text=combined_summary_text,  # <-- NEW
            )
        except Exception as e:
            logger.error("[TASK] Failed to insert history row: %s", e)
