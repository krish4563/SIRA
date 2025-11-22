# services/email_service.py

import logging
import smtplib
from email.message import EmailMessage
from typing import Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

# ----------------------------------------------------
# Low-level builder
# ----------------------------------------------------


def _build_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email

    msg.set_content(text_body)

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    return msg


# ----------------------------------------------------
# Low-level sender
# ----------------------------------------------------


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> bool:
    """Send mail using Gmail SMTP STARTTLS."""
    if not settings.smtp_user or not settings.smtp_password:
        logger.error("[EMAIL] Missing SMTP creds, cannot send email.")
        return False

    msg = _build_email(to_email, subject, text_body, html_body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        logger.info("[EMAIL] Sent → %s | subject='%s'", to_email, subject)
        return True

    except Exception as e:
        logger.exception("[EMAIL] Failed to send → %s: %s", to_email, e)
        return False


# ----------------------------------------------------
# Utility HTML wrappers
# ----------------------------------------------------


def _container(content: str) -> str:
    """Beautiful centered card layout."""
    return f"""
    <div style="
        font-family: Arial, sans-serif;
        max-width: 720px;
        margin: 20px auto;
        padding: 20px 30px;
        background: #ffffff;
        border-radius: 12px;
        border: 1px solid #ececec;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    ">
        {content}
    </div>
    """


def _heading(text: str) -> str:
    return f"""
    <h2 style="color:#1a73e8;margin-bottom:12px;">
        {text}
    </h2>
    """


def _paragraph(text: str) -> str:
    return f"""
    <p style="font-size:15px;color:#333;line-height:1.6;">
        {text}
    </p>
    """


def _list(items: list[str]) -> str:
    html = "<ul style='font-size:15px;color:#333;line-height:1.6;'>"
    for item in items:
        html += f"<li>{item}</li>"
    html += "</ul>"
    return html


def _codeblock(text: str) -> str:
    return f"""
    <pre style="
        background:#f7f7f7;
        padding:12px;
        border-radius:6px;
        font-size:14px;
        white-space:pre-wrap;
        line-height:1.4;
        border:1px solid #eee;
    ">{text}</pre>
    """


# ----------------------------------------------------
# NEW: METRICS TABLE + ARROWS
# ----------------------------------------------------


def _metric_row(label: str, previous, latest) -> str:
    """Render a metric row with change arrows + colors."""
    try:
        prev_val = float(previous)
        latest_val = float(latest)
        delta = latest_val - prev_val

        if delta > 0:
            arrow = "↑"
            color = "#0c9f40"  # green
        elif delta < 0:
            arrow = "↓"
            color = "#d93025"  # red
        else:
            arrow = "→"
            color = "#888888"  # grey
    except Exception:
        arrow = "→"
        color = "#888888"
        delta = ""

    return f"""
    <tr>
        <td style="padding:6px 10px;border-bottom:1px solid #f0f0f0;">{label}</td>
        <td style="padding:6px 10px;border-bottom:1px solid #f0f0f0;text-align:right;">{previous}</td>
        <td style="padding:6px 10px;border-bottom:1px solid #f0f0f0;text-align:right;">{latest}</td>
        <td style="padding:6px 10px;border-bottom:1px solid #f0f0f0;text-align:right;color:{color};">
            {arrow} {delta if isinstance(delta, (int, float)) and delta != 0 else ""}
        </td>
    </tr>
    """


def _metrics_table(metrics: Dict[str, Dict[str, float]]) -> str:
    if not metrics:
        return ""

    rows = "".join(
        _metric_row(label, vals.get("previous"), vals.get("latest"))
        for label, vals in metrics.items()
    )

    return f"""
    <table style="
        width:100%;
        border-collapse:collapse;
        margin:16px 0;
        font-size:14px;
        color:#333;
    ">
        <thead>
            <tr>
                <th style="padding:6px 10px;border-bottom:2px solid #e0e0e0;text-align:left;">Metric</th>
                <th style="padding:6px 10px;border-bottom:2px solid #e0e0e0;text-align:right;">Previous</th>
                <th style="padding:6px 10px;border-bottom:2px solid #e0e0e0;text-align:right;">Latest</th>
                <th style="padding:6px 10px;border-bottom:2px solid #e0e0e0;text-align:right;">Change</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
    """


# ----------------------------------------------------
# EMAIL TEMPLATES
# ----------------------------------------------------


def send_scheduler_started_email(user_email: str, topic: str, interval_seconds: int):
    subject = f"SIRA Scheduler Activated: '{topic}'"

    text = (
        f"Your SIRA scheduler has started.\n"
        f"Topic: {topic}\n"
        f"Interval: {interval_seconds} seconds\n"
    )

    html = _container(
        _heading("SIRA Scheduler Activated")
        + _paragraph(
            f"Your automated research scheduler has been <b>started</b> for <b>{topic}</b>."
        )
        + _list([f"Interval: every {interval_seconds} sec"])
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)


# ----------------------------------------------------
# UPDATED DIFF EMAIL (GRAPHICAL + METRICS)
# ----------------------------------------------------


def send_scheduler_update_email(
    user_email: str,
    topic: str,
    summary: str,
    diff_summary: Optional[str],
    conversation_url: Optional[str] = None,
    metrics: Optional[Dict[str, Dict[str, float]]] = None,
):
    subject = f"New Insights — {topic}"

    text = (
        f"New research changes detected.\n"
        f"Topic: {topic}\n"
        f"Diff:\n{diff_summary}\n\n"
        f"Summary:\n{summary}"
    )

    html = _container(
        _heading(f"New Insights — {topic}")
        + _paragraph("SIRA detected <b>new updates</b> since your last run.")
        + (
            _paragraph("<b>Metrics at a Glance:</b>") + _metrics_table(metrics)
            if metrics
            else ""
        )
        + (
            _paragraph("<b>What changed:</b>") + _codeblock(diff_summary)
            if diff_summary
            else ""
        )
        + _paragraph("<b>Updated Summary:</b>")
        + _codeblock(summary)
        + (
            f'<p><a href="{conversation_url}" '
            'style="color:#1a73e8;font-size:15px;">Open in SIRA</a></p>'
            if conversation_url
            else ""
        )
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)


# ----------------------------------------------------
# FIRST-RUN SUCCESS EMAIL
# ----------------------------------------------------


def send_research_success_email(
    user_email: str,
    topic: str,
    result_count: int,
    run_time_human: str,
    top_insights: list[str],
    conversation_url: Optional[str] = None,
):
    subject = f"SIRA Research Completed: '{topic}'"

    text = (
        f"SIRA research completed for {topic}\n"
        f"Articles: {result_count}\n"
        f"Completed: {run_time_human}\n"
    )

    html = _container(
        _heading(f"SIRA Research Summary — {topic}")
        + _paragraph("Your research task has completed <b>successfully</b>.")
        + _paragraph("<b>Run Summary:</b>")
        + _list(
            [
                f"Articles analyzed: {result_count}",
                f"Completed at: {run_time_human}",
            ]
        )
        + _paragraph("<b>Top Insights:</b>")
        + _list(top_insights)
        + (
            f'<p><a href="{conversation_url}" style="color:#1a73e8;">Open in SIRA</a></p>'
            if conversation_url
            else ""
        )
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)


# ----------------------------------------------------
# FAILURE EMAIL
# ----------------------------------------------------


def send_research_failure_email(
    user_email: str,
    topic: str,
    error_message: str,
    run_time_human: str,
):
    subject = f"SIRA Research FAILED: '{topic}'"

    text = (
        f"SIRA run failed for {topic}\nError: {error_message}\nAt: {run_time_human}\n"
    )

    html = _container(
        _heading(f"Research Failed — {topic}")
        + _paragraph(
            "Your scheduled research run has <b style='color:red;'>failed</b>."
        )
        + _paragraph("<b>Error Details:</b>")
        + _codeblock(error_message)
        + _paragraph(f"<b>Timestamp:</b> {run_time_human}")
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)


# ----------------------------------------------------
# SCHEDULER STOPPED
# ----------------------------------------------------


def send_scheduler_cancelled_email(user_email: str, topic: str):
    subject = f"SIRA Scheduler Stopped: '{topic}'"

    text = f"SIRA scheduler stopped for topic: {topic}"

    html = _container(
        _heading("Scheduler Stopped")
        + _paragraph(f"Your SIRA scheduler for <b>{topic}</b> has been stopped.")
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)


# ----------------------------------------------------
# WELCOME EMAIL
# ----------------------------------------------------


def send_welcome_email(user_email: str):
    subject = "Welcome to SIRA"

    text = "Welcome to SIRA!"

    html = _container(
        _heading("Welcome to SIRA 👋")
        + _paragraph("Start creating automated research topics today.")
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)


# ----------------------------------------------------
# DIGEST EMAILS
# ----------------------------------------------------


def send_daily_digest_email(user_email: str, digest_text: str):
    subject = "SIRA Daily Digest"

    text = f"Your daily digest:\n{digest_text}"

    html = _container(
        _heading("Daily Digest")
        + _paragraph("Here are your consolidated research updates for today:")
        + _codeblock(digest_text)
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)


def send_weekly_digest_email(user_email: str, digest_text: str):
    subject = "SIRA Weekly Digest"

    text = f"Your weekly summary:\n{digest_text}"

    html = _container(
        _heading("Weekly Digest")
        + _paragraph("Your weekly research highlights:")
        + _codeblock(digest_text)
        + _paragraph("- SIRA Research Agent")
    )

    return send_email(user_email, subject, text, html)
