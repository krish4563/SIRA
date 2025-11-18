import json
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from services.tasks import run_research_task

logger = logging.getLogger(__name__)

SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), "../data/scheduled_jobs.json")

scheduler = BackgroundScheduler()
scheduler_started = False


# --------------------------------------------
# Load & Save Scheduled Jobs
# --------------------------------------------


def _load_jobs():
    if not os.path.exists(SCHEDULE_PATH):
        return {}

    try:
        with open(SCHEDULE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_jobs(jobs):
    with open(SCHEDULE_PATH, "w") as f:
        json.dump(jobs, f, indent=2)


# --------------------------------------------
# Register Job at Startup
# --------------------------------------------


def restore_jobs_from_disk():
    jobs = _load_jobs()

    for job_id, data in jobs.items():
        topic = data["topic"]
        interval = data["interval"]
        user_id = data["user_id"]

        scheduler.add_job(
            run_research_task,
            trigger=IntervalTrigger(seconds=interval),
            id=job_id,
            args=[topic, user_id],
            replace_existing=True,
        )
        logger.info(f"[SCHEDULER] Restored job '{job_id}' ({topic})")

    return jobs


# --------------------------------------------
# Public APIs
# --------------------------------------------


def start_scheduler():
    global scheduler_started
    if not scheduler_started:
        scheduler.start()
        scheduler_started = True
        logger.info("[SCHEDULER] Started background scheduler")


def schedule_new_job(topic: str, user_id: str, interval_seconds: int):
    job_id = f"{user_id}-{topic.replace(' ', '_')}"
    jobs = _load_jobs()

    # Save to disk
    jobs[job_id] = {
        "topic": topic,
        "user_id": user_id,
        "interval": interval_seconds,
    }
    _save_jobs(jobs)

    # Register with scheduler
    scheduler.add_job(
        run_research_task,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id=job_id,
        args=[topic, user_id],
        replace_existing=True,
    )

    logger.info(f"[SCHEDULER] Added new auto-job {job_id}")
    return job_id


def cancel_job(job_id: str):
    jobs = _load_jobs()

    if job_id in jobs:
        scheduler.remove_job(job_id)
        del jobs[job_id]
        _save_jobs(jobs)
        logger.info(f"[SCHEDULER] Removed job {job_id}")
        return True
    return False


def list_jobs():
    return _load_jobs()
