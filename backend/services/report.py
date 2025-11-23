# services/report.py

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Dict, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from services.history_service import compute_numeric_diff, fetch_latest_two_runs
from services.llm_diff import llm_compare_runs
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

SIRA_BLUE = colors.HexColor("#1a73e8")
SIRA_LIGHT_BLUE = colors.HexColor("#e8f1fb")
SIRA_GREY = colors.HexColor("#555555")


# ----------------------------------------------------
# Helpers
# ----------------------------------------------------


def _parse_iso(ts: Optional[str]) -> str:
    """Convert ISO timestamp to a nicer string, fallback to as-is."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return ts


def _get_latest_run_only(job_id: str) -> Optional[Dict]:
    """Fallback when there is only one run for a job."""
    sb = get_supabase()
    resp = (
        sb.table("auto_research_history")
        .select("*")
        .eq("job_id", job_id)
        .order("run_finished_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _build_styles():
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        name="SIRA_Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=SIRA_BLUE,
        alignment=1,  # center
        spaceAfter=12,
    )

    subtitle_style = ParagraphStyle(
        name="SIRA_Subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=SIRA_GREY,
        leading=14,
        spaceAfter=6,
    )

    section_header = ParagraphStyle(
        name="SIRA_SectionHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=SIRA_BLUE,
        spaceBefore=12,
        spaceAfter=6,
    )

    body = ParagraphStyle(
        name="SIRA_Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.black,
    )

    mono = ParagraphStyle(
        name="SIRA_Mono",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=9,
        leading=11,
        textColor=colors.black,
    )

    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "section_header": section_header,
        "body": body,
        "mono": mono,
    }


def _build_header_table(topic: str, job_id: str, latest_run: Dict) -> Table:
    """Top bar with topic, job id, status, timestamp."""
    run_time = _parse_iso(latest_run.get("run_finished_at"))
    status = latest_run.get("status", "unknown").upper()
    result_count = latest_run.get("result_count", 0)

    data = [
        [
            f"Topic: {topic}",
            f"Job ID: {job_id}",
        ],
        [
            f"Last Run: {run_time}",
            f"Status: {status}  |  Results: {result_count}",
        ],
    ]

    table = Table(data, colWidths=[260, 260])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SIRA_LIGHT_BLUE),
                ("TEXTCOLOR", (0, 0), (-1, -1), SIRA_GREY),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.whitesmoke),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_numeric_diff_table(numeric_diff: Optional[Dict]) -> Optional[Table]:
    if not numeric_diff:
        return None

    rows = []

    def arrow_and_color(delta: int):
        if delta > 0:
            return f"↑ +{delta}", colors.green
        if delta < 0:
            return f"↓ {delta}", colors.red
        return "→ 0", colors.grey

    metrics = [
        ("Result Count", "result_count_change"),
        ("KG Nodes", "kg_node_change"),
        ("KG Edges", "kg_edge_change"),
    ]

    data = [["Metric", "Change (Δ)"]]
    color_map = {}  # row index -> color

    for idx, (label, key) in enumerate(metrics, start=1):
        delta = numeric_diff.get(key, 0)
        arrow, color = arrow_and_color(int(delta))
        data.append([label, arrow])
        color_map[idx] = color

    table = Table(data, colWidths=[200, 100])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), SIRA_LIGHT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), SIRA_BLUE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.whitesmoke),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.whitesmoke),
    ]

    # color code the Δ column
    for row_idx, color in color_map.items():
        style_cmds.append(("TEXTCOLOR", (1, row_idx), (1, row_idx), color))

    table.setStyle(TableStyle(style_cmds))
    return table


# ----------------------------------------------------
# Main entrypoint
# ----------------------------------------------------


def generate_report_for_job(job_id: str) -> bytes:
    """
    Build a SIRA-branded PDF report for a given job_id.
    Returns raw PDF bytes (or b"" if job not found).
    """
    logger.info("[REPORT] Generating PDF report for job_id=%s", job_id)

    latest: Optional[Dict] = None
    previous: Optional[Dict] = None
    numeric_diff: Optional[Dict] = None
    llm_diff_text: Optional[str] = None

    # Try to get 2 runs (for diff). If not available, fall back to single run.
    try:
        latest, previous = fetch_latest_two_runs(job_id)
        numeric_diff = compute_numeric_diff(latest, previous)

        prev_summary = previous.get("full_summary_text") or ""
        latest_summary = latest.get("full_summary_text") or ""
        if prev_summary and latest_summary:
            llm_diff_text = llm_compare_runs(
                previous_summary=prev_summary,
                latest_summary=latest_summary,
                topic=(latest.get("topic") or previous.get("topic") or "Unknown"),
            )
    except Exception as e:
        logger.info(
            "[REPORT] Fewer than 2 runs for job %s or diff error: %s. "
            "Falling back to single-run report.",
            job_id,
            e,
        )
        latest = _get_latest_run_only(job_id)

    if not latest:
        logger.warning("[REPORT] No history found for job_id=%s", job_id)
        return b""

    topic = latest.get("topic") or "Untitled Topic"
    full_summary = latest.get("full_summary_text") or "No summary available."
    kg_nodes = latest.get("kg_nodes", 0)
    kg_edges = latest.get("kg_edges", 0)

    styles = _build_styles()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        title=f"SIRA Report — {topic}",
    )

    story = []

    # --- Title ---
    story.append(Paragraph("SIRA Research Report", styles["title"]))
    story.append(
        Paragraph(
            "Self-Initiated Research Agent (SIRA) — Auto-generated report",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 6))

    # --- Header card ---
    story.append(_build_header_table(topic, job_id, latest))
    story.append(Spacer(1, 12))

    # --- Summary Section ---
    story.append(Paragraph("Latest Summary", styles["section_header"]))
    story.append(
        Paragraph(
            "This is the most recent consolidated summary generated by SIRA for this topic.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 4))
    story.append(Preformatted(full_summary, styles["mono"]))
    story.append(Spacer(1, 10))

    # --- Graph / KG Section (textual for now) ---
    story.append(Paragraph("Knowledge Graph Snapshot", styles["section_header"]))
    story.append(
        Paragraph(
            f"Graph complexity based on the latest run: <b>{kg_nodes}</b> nodes and <b>{kg_edges}</b> edges.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 8))

    # --- Numeric Diff (if available) ---
    if numeric_diff:
        story.append(Paragraph("Run-to-Run Changes", styles["section_header"]))
        story.append(
            Paragraph(
                "Below is a compact, color-coded view of how this run differs numerically from the previous one.",
                styles["body"],
            )
        )
        story.append(Spacer(1, 4))

        diff_table = _build_numeric_diff_table(numeric_diff)
        if diff_table:
            story.append(diff_table)
            story.append(Spacer(1, 8))

    # --- LLM Diff (semantic) ---
    if llm_diff_text:
        story.append(
            Paragraph(
                "Semantic Diff (Latest vs Previous Run)", styles["section_header"]
            )
        )
        story.append(
            Paragraph(
                "SIRA’s LLM comparison highlights what changed, disappeared, or shifted between the two runs.",
                styles["body"],
            )
        )
        story.append(Spacer(1, 4))
        story.append(Preformatted(llm_diff_text, styles["mono"]))
        story.append(Spacer(1, 10))

    # --- Footer / branding ---
    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "Report generated automatically by <b>SIRA</b>. For best results, schedule recurring research jobs and compare changes over time.",
            styles["body"],
        )
    )

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
