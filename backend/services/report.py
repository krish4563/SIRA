# services/report.py

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Dict, Optional, List

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
    ListFlowable,
    ListItem
)
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

SIRA_BLUE = colors.HexColor("#1a73e8")
SIRA_LIGHT_BLUE = colors.HexColor("#e8f1fb")
SIRA_GREY = colors.HexColor("#555555")
SIRA_LINK = colors.HexColor("#0000EE")


# ----------------------------------------------------
# Shared Helpers
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

    # --- CONVERSATION STYLES ---
    user_msg_style = ParagraphStyle(
        name="SIRA_UserMsg",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=SIRA_BLUE,
        spaceBefore=12,
        spaceAfter=6,
    )

    meta_style = ParagraphStyle(
        name="SIRA_Meta",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        textColor=SIRA_GREY,
    )

    # Styles for Research Results
    result_title_style = ParagraphStyle(
        name="SIRA_ResultTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=colors.black,
        spaceBefore=6,
    )

    result_url_style = ParagraphStyle(
        name="SIRA_ResultUrl",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        textColor=SIRA_LINK,
        spaceAfter=4,
    )

    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "section_header": section_header,
        "body": body,
        "mono": mono,
        "user": user_msg_style,
        "meta": meta_style,
        "result_title": result_title_style,
        "result_url": result_url_style
    }

# ----------------------------------------------------
# PART 1: TIMELINE REPORT GENERATION (Your Old Code)
# ----------------------------------------------------

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

def generate_report_for_job(job_id: str) -> bytes:
    """
    Build a SIRA-branded PDF report for a given job_id.
    """
    logger.info("[REPORT] Generating PDF report for job_id=%s", job_id)

    latest: Optional[Dict] = None
    previous: Optional[Dict] = None
    numeric_diff: Optional[Dict] = None
    llm_diff_text: Optional[str] = None

    try:
        from services.history_service import compute_numeric_diff, fetch_latest_two_runs
        from services.llm_diff import llm_compare_runs

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
        logger.info("[REPORT] Job report fallback or error: %s", e)
        latest = _get_latest_run_only(job_id)

    if not latest:
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
    story.append(Paragraph("SIRA Research Report", styles["title"]))
    story.append(_build_header_table(topic, job_id, latest))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Latest Summary", styles["section_header"]))
    story.append(Preformatted(full_summary, styles["mono"]))
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# ----------------------------------------------------
# PART 2: CONVERSATION REPORT GENERATION (UPDATED)
# ----------------------------------------------------

def _fetch_conversation_data(conversation_id: str):
    supabase = get_supabase()
    
    # 1. Get Conversation Meta
    conv_resp = supabase.table("conversations").select("*").eq("id", conversation_id).single().execute()
    if not conv_resp.data:
        raise ValueError("Conversation not found")
    
    # 2. Get Messages
    msg_resp = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("timestamp", desc=False) 
        .execute()
    )
    
    return conv_resp.data, msg_resp.data or []

def generate_report_for_conversation(conversation_id: str) -> bytes:
    """
    Generates a PDF transcript including DEEP research results from metadata.
    """
    logger.info(f"[REPORT] Generating Deep Conversation PDF for {conversation_id}")

    try:
        conversation, messages = _fetch_conversation_data(conversation_id)
    except Exception as e:
        logger.error(f"[REPORT] Failed to fetch data: {e}")
        return b""

    topic = conversation.get("topic_title") or "Untitled Research"
    created_at = conversation.get("created_at", "")[:10] 

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

    # --- Title Section ---
    story.append(Paragraph("SIRA Research Report", styles["title"]))
    story.append(Paragraph(f"Topic: {topic}", styles["user"]))
    story.append(Paragraph(f"Date: {created_at}", styles["meta"]))
    story.append(Spacer(1, 20))

    # --- Messages Loop ---
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        
        # Safe format
        formatted_content = content.replace("\n", "<br/>")

        if role == "user":
            # User Question
            story.append(Paragraph(f"❓ Query:", styles["user"]))
            story.append(Paragraph(content, styles["body"])) 
        
        elif role in ["agent", "assistant"]:
            # AI Intro Message
            story.append(Paragraph(f"💡 Insight:", styles["user"]))
            story.append(Paragraph(formatted_content, styles["body"]))
            
            # ----------------------------------------------------
            #  👇 NEW LOGIC: Extract Research Results from Metadata
            # ----------------------------------------------------
            meta = msg.get("meta") or {}
            results = meta.get("results", [])

            if results:
                story.append(Spacer(1, 8))
                story.append(Paragraph(f"Detailed Research Findings ({len(results)} Sources):", styles["section_header"]))
                
                for idx, item in enumerate(results, 1):
                    # Item usually has: title, summary, url, credibility
                    r_title = item.get("title", "No Title")
                    r_summary = item.get("summary") or item.get("content") or "No summary available."
                    r_url = item.get("url", "#")
                    
                    # Create a block for each result
                    story.append(Paragraph(f"{idx}. {r_title}", styles["result_title"]))
                    story.append(Paragraph(f"Source: {r_url}", styles["result_url"]))
                    story.append(Paragraph(r_summary, styles["body"]))
                    story.append(Spacer(1, 6))

        story.append(Spacer(1, 12))
        # Divider line
        story.append(Table([[""]], colWidths=[170*mm], style=[
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.lightgrey)
        ]))
        story.append(Spacer(1, 12))

    # --- Footer ---
    story.append(Spacer(1, 20))
    story.append(Paragraph("Generated by SIRA - Self Initiated Research Agent", styles["meta"]))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    
    return pdf_bytes