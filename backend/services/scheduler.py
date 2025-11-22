# services/scheduler.py

import logging
from typing import Dict

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# NEW IMPORTS FOR EMAIL NOTIFICATIONS
from services.email_service import (
    send_scheduler_cancelled_email,
    send_scheduler_started_email,
)
from services.supabase_client import get_supabase
from services.tasks import run_research_task

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
scheduler_started = False


# --------------------------------------------
# Load jobs from Supabase at startup
# --------------------------------------------


def restore_jobs_from_db() -> Dict[str, dict]:
    """
    Load all active jobs from Supabase and register them with APScheduler.
    Returns a dict {job_id: {...}} mainly for debugging.
    """
    sb = get_supabase()

    resp = (
        sb.table("auto_research_jobs")
        .select("id, user_id, topic, interval_seconds")
        .eq("is_active", True)
        .execute()
    )

    rows = resp.data or []
    out: Dict[str, dict] = {}

    for row in rows:
        job_id = row["id"]
        topic = row["topic"]
        user_id = row["user_id"]
        interval = row["interval_seconds"]

        # Register job with APScheduler
        scheduler.add_job(
            run_research_task,
            trigger=IntervalTrigger(seconds=interval),
            id=job_id,
            args=[topic, user_id, job_id],
            replace_existing=True,
        )

        out[job_id] = {
            "topic": topic,
            "user_id": user_id,
            "interval": interval,
        }

        logger.info("[SCHEDULER] Restored job '%s' (%s)", job_id, topic)

    return out


# --------------------------------------------
# Public APIs
# --------------------------------------------


def start_scheduler():
    global scheduler_started
    if not scheduler_started:
        scheduler.start()
        scheduler_started = True
        logger.info("[SCHEDULER] Started background scheduler")

        # Restore persisted jobs from Supabase
        restored = restore_jobs_from_db()
        logger.info("[SCHEDULER] Restored %d jobs from DB", len(restored))


def schedule_new_job(topic: str, user_id: str, interval_seconds: int) -> str:
    """
    Create + persist a new auto-research job for this user/topic.
    Returns the DB job_id (uuid).
    """
    sb = get_supabase()

    # Soft delete old active jobs for same user + topic
    sb.table("auto_research_jobs").update({"is_active": False}).match(
        {"user_id": user_id, "topic": topic, "is_active": True}
    ).execute()

    # Insert new job into DB
    resp = (
        sb.table("auto_research_jobs")
        .insert(
            {
                "user_id": user_id,
                "topic": topic,
                "interval_seconds": interval_seconds,
                "is_active": True,
            }
        )
        .execute()
    )

    row = (resp.data or [])[0]
    job_id = row["id"]

    # Register with APScheduler
    scheduler.add_job(
        run_research_task,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id=job_id,
        args=[topic, user_id, job_id],
        replace_existing=True,
    )

    logger.info(
        "[SCHEDULER] Added job %s for user=%s topic='%s' every %ss",
        job_id,
        user_id,
        topic,
        interval_seconds,
    )

    # --------------------------------------------
    # SEND EMAIL: Scheduler Started
    # --------------------------------------------
    try:
        # TODO: Replace with real user email when users table exists
        user_email = "indrranil7@gmail.com"
        send_scheduler_started_email(
            user_email,
            topic,
            interval_seconds,
        )
    except Exception as e:
        logger.warning("[EMAIL] Failed to send job-started email: %s", e)

    return job_id


def cancel_job(job_id: str) -> bool:
    """
    Soft delete a job: mark is_active=false in DB and remove from scheduler.
    """
    sb = get_supabase()

    # Fetch the job topic for email notification
    topic_resp = (
        sb.table("auto_research_jobs")
        .select("topic")
        .eq("id", job_id)
        .single()
        .execute()
    )

    topic = None
    if topic_resp and topic_resp.data:
        topic = topic_resp.data.get("topic")

    # Soft delete job in DB
    sb.table("auto_research_jobs").update({"is_active": False}).eq(
        "id", job_id
    ).execute()

    # Remove from in-memory scheduler
    try:
        scheduler.remove_job(job_id)
        logger.info("[SCHEDULER] Removed job %s", job_id)
    except Exception as e:
        logger.warning("[SCHEDULER] remove_job failed for %s: %s", job_id, e)

    # --------------------------------------------
    # SEND EMAIL: Scheduler Cancelled
    # --------------------------------------------
    try:
        if topic:
            user_email = "indrranil7@gmail.com"
            send_scheduler_cancelled_email(
                user_email=user_email,
                topic=topic,
            )
    except Exception as e:
        logger.warning("[EMAIL] Failed to send cancellation email: %s", e)

    return True


def list_jobs() -> Dict[str, dict]:
    """
    Return mapping {job_id: {topic, user_id, interval}} of active jobs.
    """
    sb = get_supabase()

    resp = (
        sb.table("auto_research_jobs")
        .select("id, user_id, topic, interval_seconds, is_active")
        .eq("is_active", True)
        .execute()
    )

    rows = resp.data or []
    out: Dict[str, dict] = {}

    for row in rows:
        job_id = row["id"]
        out[job_id] = {
            "topic": row["topic"],
            "user_id": row["user_id"],
            "interval": row["interval_seconds"],
        }

    return out
