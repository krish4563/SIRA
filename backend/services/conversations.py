# services/conversations.py

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.supabase_client import get_supabase


# ─────────────────────────────────────
# CREATE CONVERSATION
# ─────────────────────────────────────
def create_conversation(user_id: str, topic_title: str) -> str:
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    resp = (
        supabase.table("conversations")
        .insert(
            {
                "user_id": user_id,
                "topic_title": topic_title,
                "created_at": now,
                "updated_at": now,
            }
        )
        .execute()
    )

    if not resp.data:
        raise RuntimeError("Failed to create conversation in Supabase.")

    return resp.data[0]["id"]


# ─────────────────────────────────────
# ADD MESSAGE (with meta + auto-update updated_at)
# ─────────────────────────────────────
def add_message(
    conversation_id: str,
    role: str,
    content: str,
    meta: Optional[dict] = None,
) -> str:
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    # Insert message
    resp = (
        supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "timestamp": now,
                "meta": meta or {},
            }
        )
        .execute()
    )

    if not resp.data:
        raise RuntimeError("Failed to insert message.")

    # Auto-update updated_at in conversations table
    supabase.table("conversations").update({"updated_at": now}).eq(
        "id", conversation_id
    ).execute()

    return resp.data[0]["id"]


# ─────────────────────────────────────
# GET FULL CONVERSATION (with pagination)
# ─────────────────────────────────────
def get_conversation(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    supabase = get_supabase()

    # Fetch conversation meta
    conv_resp = (
        supabase.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .single()
        .execute()
    )

    if not conv_resp.data:
        return {}

    # Fetch paginated messages
    msg_resp = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("timestamp", desc=False)
        .range(offset, offset + limit - 1)
        .execute()
    )

    return {
        "conversation": conv_resp.data,
        "messages": msg_resp.data or [],
        "pagination": {
            "limit": limit,
            "offset": offset,
        },
    }


# ─────────────────────────────────────
# LIST CONVERSATIONS GROUPED LIKE CHATGPT
# ─────────────────────────────────────
def list_conversations_grouped(user_id: str) -> Dict[str, List[Dict[str, Any]]]:
    supabase = get_supabase()

    resp = (
        supabase.table("conversations")
        .select("id, topic_title, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    rows = resp.data or []

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    grouped: Dict[str, List[Dict[str, Any]]] = {
        "Today": [],
        "Yesterday": [],
        "Previous 7 Days": [],
        "Older": [],
    }

    for row in rows:
        created_at = row["created_at"]
        # Normalize ISO strings
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        item = {
            "id": row["id"],
            "title": row["topic_title"],
            "created_at": created_at,
        }

        if created_dt >= today_start:
            grouped["Today"].append(item)
        elif yesterday_start <= created_dt < today_start:
            grouped["Yesterday"].append(item)
        elif week_start <= created_dt < yesterday_start:
            grouped["Previous 7 Days"].append(item)
        else:
            grouped["Older"].append(item)

    # Remove empty groups (ChatGPT-style)
    return {k: v for k, v in grouped.items() if v}
