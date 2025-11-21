# routers/history.py

from typing import Dict

from fastapi import APIRouter, HTTPException
from services.llm_diff import llm_compare_runs  # NEW LLM diff helper
from services.supabase_client import get_supabase

router = APIRouter(tags=["history"])


def _numeric_diff(latest: Dict, previous: Dict) -> Dict:
    """Compute simple numeric deltas."""

    def _safe(x):
        try:
            return int(x)
        except:
            return 0

    return {
        "result_count_change": _safe(latest.get("result_count"))
        - _safe(previous.get("result_count")),
        "kg_node_change": _safe(latest.get("kg_nodes"))
        - _safe(previous.get("kg_nodes")),
        "kg_edge_change": _safe(latest.get("kg_edges"))
        - _safe(previous.get("kg_edges")),
        "latest_status": latest.get("status"),
        "previous_status": previous.get("status"),
        "latest_run_at": latest.get("run_finished_at"),
        "previous_run_at": previous.get("run_finished_at"),
    }


@router.get("/job/{job_id}/diff")
def diff_last_two_runs(job_id: str):
    """
    Compare the latest 2 runs of an auto-research job.
    Returns:
      - metadata of both runs
      - numeric diff
      - semantic LLM diff (if summaries exist)
    """

    sb = get_supabase()

    resp = (
        sb.table("auto_research_history")
        .select("*")
        .eq("job_id", job_id)
        .order("run_started_at", desc=True)
        .limit(2)
        .execute()
    )

    rows = resp.data or []
    if len(rows) < 2:
        raise HTTPException(400, "Not enough runs to compare")

    latest, previous = rows[0], rows[1]

    # Prepare numeric diff for frontend graphs
    numeric = _numeric_diff(latest, previous)

    # Extract summaries for LLM diff
    previous_summary = previous.get("full_summary_text") or ""
    latest_summary = latest.get("full_summary_text") or ""

    # If summaries missing → return numeric-only diff with warning
    if not previous_summary or not latest_summary:
        return {
            "job_id": job_id,
            "latest": latest,
            "previous": previous,
            "numeric_diff": numeric,
            "llm_diff": "Summary text missing in history — semantic diff unavailable.",
        }

    # Semantic LLM comparison
    llm_diff_text = llm_compare_runs(
        previous_summary=previous_summary,
        latest_summary=latest_summary,
        topic=(latest.get("topic") or previous.get("topic") or "Unknown"),
    )

    return {
        "job_id": job_id,
        "latest": latest,
        "previous": previous,
        "numeric_diff": numeric,
        "llm_diff": llm_diff_text,
    }
