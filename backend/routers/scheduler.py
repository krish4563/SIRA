from fastapi import APIRouter

from services.scheduler import (
    cancel_job,
    list_jobs,
    schedule_new_job,
)

router = APIRouter()


@router.post("/start")
def start_job(topic: str, user_id: str, interval_seconds: int = 3600):
    job_id = schedule_new_job(topic, user_id, interval_seconds)
    return {"status": "scheduled", "job_id": job_id}


@router.post("/stop")
def stop_job(job_id: str):
    ok = cancel_job(job_id)
    return {"removed": ok}


@router.get("/list")
def get_jobs():
    return list_jobs()
