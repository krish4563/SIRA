# services/report_builder.py

import logging
from io import BytesIO
from typing import Dict, List, Optional, Tuple
from services.conversations import get_conversation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ----------------------------------------------------
# Supabase helpers
# ----------------------------------------------------


def _fetch_job(job_id: str) -> Optional[Dict]:
    sb = get_supabase()
    resp = (
        sb.table("auto_research_jobs")
        .select("id, user_id, topic, interval_seconds, created_at, last_run_at")
        .eq("id", job_id)
        .single()
        .execute()
    )
    return resp.data if resp and resp.data else None


def _fetch_history(job_id: str, limit: int = 10) -> List[Dict]:
    sb = get_supabase()
    resp = (
        sb.table("auto_research_history")
        .select("*")
        .eq("job_id", job_id)
        .order("run_finished_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def _safe_time_str(dt_str: Optional[str]) -> str:
    if not dt_str:
        return "-"
    # dt_str is ISO format from Supabase; make it nicer
    # "2025-11-22T05:36:25.833392+00:00" -> "2025-11-22 05:36:25"
    try:
        return dt_str.replace("T", " ").split("+")[0].split(".")[0]
    except Exception:
        return dt_str


def _extract_top_insights(summary: str, max_items: int = 5) -> List[str]:
    """
    Simple heuristic: take first non-empty lines from full_summary_text.
    No extra LLM call needed.
    """
    if not summary:
        return []

    lines = [ln.strip() for ln in summary.splitlines() if ln.strip()]
    return lines[:max_items]


def _compute_numeric_diff(latest: Dict, previous: Dict) -> Dict:
    def _safe_int(x):
        try:
            return int(x)
        except Exception:
            return 0

    return {
        "result_count_change": _safe_int(latest.get("result_count"))
        - _safe_int(previous.get("result_count")),
        "kg_node_change": _safe_int(latest.get("kg_nodes"))
        - _safe_int(previous.get("kg_nodes")),
        "kg_edge_change": _safe_int(latest.get("kg_edges"))
        - _safe_int(previous.get("kg_edges")),
    }


# ----------------------------------------------------
# Drawing helpers (blue-grey dashboard style)
# ----------------------------------------------------


def _draw_header(c: canvas.Canvas, title: str, subtitle: str = ""):
    width, height = A4

    # Top bar
    bar_height = 22 * mm
    c.setFillColorRGB(0.10, 0.16, 0.28)  # dark blue-grey
    c.rect(0, height - bar_height, width, bar_height, fill=1, stroke=0)

    # Title
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(25 * mm, height - 14 * mm, title)

    if subtitle:
        c.setFont("Helvetica", 10)
        c.drawString(25 * mm, height - 20 * mm, subtitle)


def _draw_section_title(c: canvas.Canvas, text: str, y: float) -> float:
    c.setFillColorRGB(0.15, 0.25, 0.40)  # blue-ish
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, y, text)
    return y - 6 * mm


def _draw_label_value(
    c: canvas.Canvas, label: str, value: str, x: float, y: float
) -> float:
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.black)
    c.drawString(x, y, f"{label}:")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.darkgray)
    c.drawString(x + 35 * mm, y, value)
    return y - 5 * mm


def _wrap_text(
    c: canvas.Canvas, text: str, max_width: float, x: float, y: float
) -> float:
    """
    Very simple word wrapping for paragraphs.
    """
    if not text:
        return y

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)

    words = text.split()
    line = ""
    for word in words:
        test_line = f"{line} {word}".strip()
        w = c.stringWidth(test_line, "Helvetica", 10)
        if w <= max_width:
            line = test_line
        else:
            c.drawString(x, y, line)
            y -= 4 * mm
            line = word
    if line:
        c.drawString(x, y, line)
        y -= 4 * mm

    return y


def _arrow_text(delta: int) -> Tuple[str, colors.Color]:
    if delta > 0:
        return f"↑ +{delta}", colors.green
    if delta < 0:
        return f"↓ {delta}", colors.red
    return "→ 0", colors.gray


def _draw_run_card(
    c: canvas.Canvas,
    run: Dict,
    diff: Optional[Dict],
    x: float,
    y: float,
    width: float,
    height: float,
):
    # Card background
    c.setFillColorRGB(0.96, 0.97, 0.99)
    c.roundRect(x, y - height, width, height, 6, fill=1, stroke=0)

    # Border
    c.setLineWidth(0.5)
    c.setStrokeColorRGB(0.80, 0.84, 0.90)
    c.roundRect(x, y - height, width, height, 6, fill=0, stroke=1)

    inner_x = x + 4 * mm
    inner_y = y - 6 * mm

    # Run timestamp
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.black)
    c.drawString(inner_x, inner_y, _safe_time_str(run.get("run_finished_at")))
    inner_y -= 5 * mm

    # Status line
    status = run.get("status", "unknown")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.darkgray)
    c.drawString(inner_x, inner_y, f"Status: {status}")
    inner_y -= 4 * mm

    # Metrics
    result_count = run.get("result_count", 0)
    kg_nodes = run.get("kg_nodes", 0)
    kg_edges = run.get("kg_edges", 0)

    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)

    # Result count
    c.drawString(inner_x, inner_y, f"Results: {result_count}")
    if diff:
        arrow_txt, arrow_color = _arrow_text(diff["result_count_change"])
        c.setFillColor(arrow_color)
        c.drawString(inner_x + 32 * mm, inner_y, arrow_txt)
        c.setFillColor(colors.black)
    inner_y -= 4 * mm

    # KG nodes
    c.drawString(inner_x, inner_y, f"KG Nodes: {kg_nodes}")
    if diff:
        arrow_txt, arrow_color = _arrow_text(diff["kg_node_change"])
        c.setFillColor(arrow_color)
        c.drawString(inner_x + 32 * mm, inner_y, arrow_txt)
        c.setFillColor(colors.black)
    inner_y -= 4 * mm

    # KG edges
    c.drawString(inner_x, inner_y, f"KG Edges: {kg_edges}")
    if diff:
        arrow_txt, arrow_color = _arrow_text(diff["kg_edge_change"])
        c.setFillColor(arrow_color)
        c.drawString(inner_x + 32 * mm, inner_y, arrow_txt)
        c.setFillColor(colors.black)


# ----------------------------------------------------
# Public entrypoint
# ----------------------------------------------------


def build_job_report(job_id: str) -> bytes:
    """
    Build a PDF report (blue-grey dashboard style) for a given job_id.
    Returns raw PDF bytes.
    """

    job = _fetch_job(job_id)
    history = _fetch_history(job_id, limit=10)

    if not history:
        raise ValueError("No history found for the given job_id.")

    # Sort history ascending by time so earliest first, latest last
    history_sorted = sorted(
        history, key=lambda r: r.get("run_finished_at") or r.get("run_started_at")
    )
    total_runs = len(history_sorted)
    latest_run = history_sorted[-1]
    first_run = history_sorted[0]

    topic = (job and job.get("topic")) or latest_run.get("topic") or "Unknown Topic"
    user_id = (job and job.get("user_id")) or latest_run.get("user_id") or "unknown"
    interval_seconds = (job and job.get("interval_seconds")) or "-"
    first_run_time = _safe_time_str(first_run.get("run_finished_at"))
    latest_run_time = _safe_time_str(latest_run.get("run_finished_at"))

    latest_summary = latest_run.get("full_summary_text") or ""
    top_insights = _extract_top_insights(latest_summary, max_items=5)

    # Pre-compute diffs between consecutive runs (for cards)
    diffs: Dict[str, Dict] = {}
    if total_runs >= 2:
        for prev, cur in zip(history_sorted[:-1], history_sorted[1:]):
            diffs[cur["id"]] = _compute_numeric_diff(cur, prev)

    # ---------------------------------------------
    # PDF generation
    # ---------------------------------------------
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # ---------------
    # PAGE 1 — Cover
    # ---------------
    _draw_header(c, "SIRA Research Report", subtitle="Automated Research Timeline")

    y = height - 30 * mm
    y = _draw_section_title(c, "Job Overview", y)

    y = _draw_label_value(c, "Topic", topic, 25 * mm, y)
    y = _draw_label_value(c, "User ID", str(user_id), 25 * mm, y)
    y = _draw_label_value(c, "Job ID", job_id, 25 * mm, y)
    y = _draw_label_value(c, "Interval", f"{interval_seconds} seconds", 25 * mm, y)
    y = _draw_label_value(c, "First Run", first_run_time, 25 * mm, y)
    y = _draw_label_value(c, "Latest Run", latest_run_time, 25 * mm, y)
    y = _draw_label_value(c, "Total Runs (in report)", str(total_runs), 25 * mm, y)

    c.showPage()

    # -------------------------
    # PAGE 2 — Exec Summary
    # -------------------------
    _draw_header(c, "Executive Summary", subtitle=topic)

    y = height - 30 * mm
    y = _draw_section_title(c, "Latest Aggregated Summary", y)
    y -= 2 * mm
    y = _wrap_text(
        c,
        latest_summary or "No summary text available for the latest run.",
        max_width=width - 40 * mm,
        x=25 * mm,
        y=y,
    )

    y -= 6 * mm
    y = _draw_section_title(c, "Top Insights", y)
    y -= 2 * mm

    if top_insights:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        for insight in top_insights:
            bullet_line = f"• {insight}"
            y = _wrap_text(
                c,
                bullet_line,
                max_width=width - 45 * mm,
                x=30 * mm,
                y=y,
            )
            y -= 1 * mm
            if y < 40 * mm:
                c.showPage()
                _draw_header(c, "Executive Summary (cont.)", subtitle=topic)
                y = height - 30 * mm
    else:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.darkgray)
        c.drawString(25 * mm, y, "No insights available.")
        y -= 5 * mm

    c.showPage()

    # -------------------------
    # PAGE 3 — Run Timeline
    # -------------------------
    _draw_header(c, "Run-by-Run Timeline", subtitle=topic)
    y = height - 30 * mm
    y = _draw_section_title(c, "Recent Runs", y)
    y -= 4 * mm

    card_x = 20 * mm
    card_width = width - 2 * card_x
    card_height = 24 * mm

    # Draw cards from latest to oldest within this report
    for run in reversed(history_sorted):
        if y - card_height < 20 * mm:
            c.showPage()
            _draw_header(c, "Run-by-Run Timeline (cont.)", subtitle=topic)
            y = height - 30 * mm

        run_id = run.get("id")
        diff = diffs.get(run_id)
        _draw_run_card(
            c,
            run,
            diff=diff,
            x=card_x,
            y=y,
            width=card_width,
            height=card_height,
        )
        y -= card_height + 5 * mm

    # -------------------------
    # PAGE 4 — Raw Data (Latest)
    # -------------------------
    c.showPage()
    _draw_header(c, "Latest Run — Raw Summary", subtitle=topic)
    y = height - 30 * mm
    y = _draw_section_title(c, "Full Summary Text", y)
    y -= 2 * mm

    y = _wrap_text(
        c,
        latest_summary or "No summary available.",
        max_width=width - 40 * mm,
        x=25 * mm,
        y=y,
    )

    # Finalize
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()
def build_conversation_report(conversation_id: str) -> bytes:
    """
    Build a timeline-style PDF report for a given conversation_id.
    Uses the conversations + messages stored in Supabase.
    """
    data = get_conversation(conversation_id, limit=1000, offset=0)
    if not data or not data.get("conversation"):
        raise ValueError("Conversation not found.")

    conv = data["conversation"]
    messages = data.get("messages") or []

    topic = conv.get("topic_title") or "Untitled Conversation"
    user_id = conv.get("user_id", "unknown")
    created_at = _safe_time_str(conv.get("created_at"))
    total_messages = len(messages)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # ---------------
    # PAGE 1 — Cover
    # ---------------
    _draw_header(c, "SIRA Conversation Report", subtitle="Research Timeline")

    y = height - 30 * mm
    y = _draw_section_title(c, "Conversation Overview", y)

    y = _draw_label_value(c, "Topic", topic, 25 * mm, y)
    y = _draw_label_value(c, "User ID", str(user_id), 25 * mm, y)
    y = _draw_label_value(c, "Conversation ID", conversation_id, 25 * mm, y)
    y = _draw_label_value(c, "Created At", created_at, 25 * mm, y)
    y = _draw_label_value(c, "Total Messages", str(total_messages), 25 * mm, y)

    c.showPage()

    # -------------------------
    # PAGE 2+ — Message Timeline
    # -------------------------
    _draw_header(c, "Message Timeline", subtitle=topic)
    y = height - 30 * mm
    y = _draw_section_title(c, "Messages", y)
    y -= 4 * mm

    for msg in messages:
        ts = _safe_time_str(msg.get("timestamp"))
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")

        # Timestamp + role line
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.black)
        c.drawString(25 * mm, y, f"[{ts}] {role}")
        y -= 5 * mm

        # Content wrapped
        y = _wrap_text(
            c,
            content or "(empty message)",
            max_width=width - 40 * mm,
            x=30 * mm,
            y=y,
        )
        y -= 3 * mm

        # New page if needed
        if y < 30 * mm:
            c.showPage()
            _draw_header(c, "Message Timeline (cont.)", subtitle=topic)
            y = height - 30 * mm

    # Finalize
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()