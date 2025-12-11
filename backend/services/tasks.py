# services/tasks.py

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

# EMAIL HOOKS
from services.email_service import (
    send_research_failure_email,
    send_research_success_email,
    send_scheduler_update_email,
)
from services.knowledge_graph import extract_triplets_from_texts
from services.llm_client import MODEL, client, evaluate_source, summarize_text
from services.memory_manager import MemoryManager
from services.multi_retriever import search_and_extract
from services.realtime_retriever import fetch_realtime  # NEW IMPORT
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
memory = MemoryManager()


# ----------------------------------------------------
# Helpers
# ----------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _format_human_time(dt: datetime) -> str:
    """Convert UTC → IST pretty string."""
    try:
        ist = dt.astimezone(ZoneInfo("Asia/Kolkata"))
        return ist.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return dt.strftime("%d %b %Y, %H:%M UTC")


def _extract_top_insights_from_summaries(
    summaries: list[str], max_items: int = 3
) -> list[str]:
    if not summaries:
        return []

    text = " ".join(summaries).replace("\r", " ")
    chunks = re.split(r"[\n\.]", text)

    out = []
    for c in chunks:
        s = c.strip()
        if s:
            out.append(s)
            if len(out) >= max_items:
                break
    return out


def _get_last_summary(job_id: Optional[str]) -> Optional[str]:
    """
    Fetch the *previous* run's summary, not the current one.
    This is required to correctly compute diff in scheduler.
    """
    if not job_id:
        return None

    sb = get_supabase()

    # Fetch the second most recent entry:
    # skip the latest (offset=1)
    resp = (
        sb.table("auto_research_history")
        .select("full_summary_text")
        .eq("job_id", job_id)
        .order("run_finished_at", desc=True)
        .offset(1)  # <-- THE KEY FIX (skip latest run)
        .limit(1)
        .execute()
    )

    rows = resp.data or []
    if not rows:
        return None

    return rows[0].get("full_summary_text", "")


def _compute_diff(old: str, new: str) -> Optional[str]:
    """LLM-based diff detection (2025 OpenAI API compatible)."""
    if not old:
        return None
    if old.strip() == new.strip():
        return None

    try:
        result = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Compare Text A and Text B. "
                        "Return ONLY meaningful differences as bullet points. "
                        "If no meaningful difference, return exactly: NO_CHANGES"
                    ),
                },
                {
                    "role": "user",
                    "content": f"Text A:\n\n{old}\n\nText B:\n\n{new}",
                },
            ],
        )

        # --- FIX: new OpenAI response format ---
        msg = result.choices[0].message

        # content may be a list of content-parts or a plain string depending on model
        if isinstance(msg.content, list):
            # usually: [{"type":"text","text":"..."}]
            content = "".join(
                part.text for part in msg.content if hasattr(part, "text")
            )
        else:
            content = msg.content or ""

        diff = content.strip()

        if diff.lower() in ("no_changes", "no changes"):
            return None

        return diff

    except Exception as e:
        logger.error("[DIFF] Error computing diff: %s", e)
        return None


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
    full_summary_text: str,
):
    sb = get_supabase()

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
            "full_summary_text": full_summary_text,
        }
    ).execute()

    if job_id:
        sb.table("auto_research_jobs").update(
            {
                "last_run_at": run_finished_at.isoformat(),
                "last_status": status,
            }
        ).eq("id", job_id).execute()


# ----------------------------------------------------
# REAL-TIME TOPIC DETECTOR
# ----------------------------------------------------


def is_real_time_topic(topic: str) -> bool:
    """
    Real-time topics = crypto, markets, forex, weather, AQI, news, earthquakes, etc.
    These should bypass the search pipeline entirely.
    """
    rt_keywords = [
        "live",
        "price",
        "crypto",
        "bitcoin",
        "btc",
        "eth",
        "market",
        "stocks",
        "nifty",
        "sensex",
        "forex",
        "currency",
        "usd",
        "inr",
        "gold",
        "xau",
        "weather",
        "temperature",
        "aqi",
        "pollution",
        "earthquake",
        "quake",
        "seismic",
        "news",
        "headlines",
        "trending",
    ]

    t = topic.lower()
    return any(k in t for k in rt_keywords)


# ----------------------------------------------------
# MAIN PIPELINE
# ----------------------------------------------------


def run_research_task(topic: str, user_id: str, job_id: Optional[str] = None):
    start_ts = _now_utc()
    logger.info(
        "[TASK] Research started for '%s' (user=%s, job_id=%s)", topic, user_id, job_id
    )

    status = "running"
    error_message = None
    result_count = 0
    kg_nodes = 0
    kg_edges = 0
    summaries_for_history: list[str] = []

    try:
        # ----------------------------------------------------
        # 1. SEARCH PHASE (Real-time override logic)
        # ----------------------------------------------------
        if is_real_time_topic(topic):
            logger.info("[TASK] Real-time topic detected → using live APIs.")
            articles = fetch_realtime(topic)
        else:
            logger.info("[TASK] Normal topic → using search providers.")
            articles = search_and_extract(topic)

        if not articles:
            status = "success"
            return

        # ----------------------------------------------------
        # 2. PER-ARTICLE SUMMARIZATION
        # ----------------------------------------------------
        results_out = []
        texts_for_kg = []

        for art in articles:
            raw_text = art.get("snippet") or art.get("text") or ""
            if not raw_text:
                continue

            summary = summarize_text(raw_text)
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

            summaries_for_history.append(summary)
            texts_for_kg.append(summary)

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
                logger.error("[MEMORY] Save error: %s", e)

        result_count = len(results_out)

        # ----------------------------------------------------
        # 3. KNOWLEDGE GRAPH EXTRACTION
        # ----------------------------------------------------
        kg = extract_triplets_from_texts(texts_for_kg)
        kg_nodes = kg.get("counts", {}).get("nodes", 0)
        kg_edges = kg.get("counts", {}).get("edges", 0)

        status = "success"

    except Exception as e:
        logger.exception("[TASK] Fatal error: %s", e)
        status = "error"
        error_message = str(e)

    finally:
        end_ts = _now_utc()
        combined_summary_text = "\n\n".join(summaries_for_history)

        # ----------------------------------------------------
        # 4. SAVE HISTORY
        # ----------------------------------------------------
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
                full_summary_text=combined_summary_text,
            )
        except Exception as e:
            logger.error("[TASK] History insert error: %s", e)

        # ----------------------------------------------------
        # 5. EMAIL NOTIFICATIONS
        # ----------------------------------------------------
        # ----------------------------------------------------
        # 5. EMAIL NOTIFICATIONS
        # ----------------------------------------------------
        try:
            # Fetch user's email from Supabase Auth
            sb = get_supabase()
            user_resp = (
                sb.table("users").select("email").eq("id", user_id).single().execute()
            )

            if not user_resp.data or "email" not in user_resp.data:
                logger.error("[EMAIL] Could not find email for user_id=%s", user_id)
                return

            user_email = user_resp.data["email"]
            human_time = _format_human_time(end_ts)

            # FAILURE email
            if status == "error":
                send_research_failure_email(
                    user_email=user_email,
                    topic=topic,
                    error_message=error_message or "Unknown error",
                    run_time_human=human_time,
                )
                return

            # DIFF LOGIC
            previous_summary = _get_last_summary(job_id)
            diff_summary = (
                _compute_diff(previous_summary, combined_summary_text)
                if previous_summary
                else None
            )

            # FIRST RUN EMAIL
            if previous_summary is None:
                top_insights = _extract_top_insights_from_summaries(
                    summaries_for_history, max_items=3
                )
                send_research_success_email(
                    user_email=user_email,
                    topic=topic,
                    result_count=result_count,
                    run_time_human=human_time,
                    top_insights=top_insights,
                    conversation_url=None,
                )
                return

            # NO CHANGES → SKIP EMAIL
            if diff_summary is None:
                logger.info("[EMAIL] No diff → skipping email.")
                return

            # SEND DIFF UPDATE EMAIL
            send_scheduler_update_email(
                user_email=user_email,
                topic=topic,
                summary=combined_summary_text,
                diff_summary=diff_summary,
                conversation_url=None,
            )

        except Exception as e:
            logger.error("[EMAIL] Error sending notification: %s", e)
