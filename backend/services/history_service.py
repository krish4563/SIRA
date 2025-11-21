# services/history_service.py

import logging
from typing import Dict, List, Tuple

from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def fetch_latest_two_runs(job_id: str) -> Tuple[Dict, Dict]:
    """
    Fetch the latest two runs for a given job_id from auto_research_history.

    Returns (latest, previous).

    Raises ValueError if fewer than 2 runs exist.
    """
    sb = get_supabase()

    resp = (
        sb.table("auto_research_history")
        .select("*")
        .eq("job_id", job_id)
        .order("run_finished_at", desc=True)
        .limit(2)
        .execute()
    )

    rows: List[Dict] = resp.data or []
    if len(rows) < 2:
        raise ValueError("Not enough history to compute diff (need at least 2 runs).")

    latest = rows[0]
    previous = rows[1]
    return latest, previous


def compute_numeric_diff(latest: Dict, previous: Dict) -> Dict:
    """
    Simple numeric diff (not LLM-based) so frontend can plot changes quickly.
    """

    def _safe_int(x):
        try:
            return int(x)
        except Exception:
            return 0

    diff = {
        "result_count_change": _safe_int(latest.get("result_count"))
        - _safe_int(previous.get("result_count")),
        "kg_node_change": _safe_int(latest.get("kg_nodes"))
        - _safe_int(previous.get("kg_nodes")),
        "kg_edge_change": _safe_int(latest.get("kg_edges"))
        - _safe_int(previous.get("kg_edges")),
        "latest_status": latest.get("status"),
        "previous_status": previous.get("status"),
        "latest_run_at": latest.get("run_finished_at"),
        "previous_run_at": previous.get("run_finished_at"),
    }
    return diff
