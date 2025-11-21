# services/schedule_repository.py

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .supabase_client import get_supabase


@dataclass
class ScheduleRecord:
    id: str
    user_id: str
    topic: str
    interval_seconds: int
    is_active: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]


TABLE = "research_schedules"


def _row_to_record(row: dict) -> ScheduleRecord:
    return ScheduleRecord(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        topic=row["topic"],
        interval_seconds=row["interval_seconds"],
        is_active=row["is_active"],
        last_run_at=row.get("last_run_at"),
        next_run_at=row.get("next_run_at"),
    )


def create_schedule(user_id: str, topic: str, interval_seconds: int) -> ScheduleRecord:
    now = datetime.now(timezone.utc)
    next_run = now + timedelta(seconds=interval_seconds)

    supabase = get_supabase()
    res = (
        supabase.table(TABLE)
        .insert(
            {
                "user_id": user_id,
                "topic": topic,
                "interval_seconds": interval_seconds,
                "is_active": True,
                "last_run_at": None,
                "next_run_at": next_run.isoformat(),
            }
        )
        .select("*")
        .single()
        .execute()
    )
    row = res.data
    return _row_to_record(row)


def list_active_schedules() -> List[ScheduleRecord]:
    supabase = get_supabase()
    res = supabase.table(TABLE).select("*").eq("is_active", True).execute()
    rows = res.data or []
    return [_row_to_record(r) for r in rows]


def mark_run_completed(schedule_id: str, interval_seconds: int):
    now = datetime.now(timezone.utc)
    next_run = now + timedelta(seconds=interval_seconds)

    supabase = get_supabase()
    supabase.table(TABLE).update(
        {
            "last_run_at": now.isoformat(),
            "next_run_at": next_run.isoformat(),
            "updated_at": now.isoformat(),
        }
    ).eq("id", schedule_id).execute()


def deactivate_schedule(schedule_id: str):
    now = datetime.now(timezone.utc)
    supabase = get_supabase()
    supabase.table(TABLE).update(
        {"is_active": False, "updated_at": now.isoformat()}
    ).eq("id", schedule_id).execute()
