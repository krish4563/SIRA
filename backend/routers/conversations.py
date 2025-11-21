# routers/conversations.py

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.conversations import (
    add_message,
    create_conversation,
    get_conversation,
    list_conversations_grouped,
)
from services.supabase_client import get_supabase

router = APIRouter(tags=["conversations"])


# ------------------------------
# Pydantic Schemas
# ------------------------------
class StartConversationRequest(BaseModel):
    user_id: str
    topic_title: str


class MessageRequest(BaseModel):
    role: str  # "user" or "agent"
    content: str
    meta: Optional[dict] = None  # citations / KG pointers / metadata


class RenameConversationRequest(BaseModel):
    new_title: str


# ------------------------------
# Endpoints
# ------------------------------


@router.post("/start")
def start_conversation(payload: StartConversationRequest):
    """
    Create a new conversation.
    """
    conv_id = create_conversation(
        user_id=payload.user_id,
        topic_title=payload.topic_title,
    )
    return {"conversation_id": conv_id}


@router.post("/{conversation_id}/message")
def post_message(conversation_id: str, payload: MessageRequest):
    """
    Add a message to a conversation.
    Supports: role, content, meta (citations / KG / etc).
    Auto-updates conversation.updated_at.
    """
    if payload.role not in ("user", "agent"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'agent'")

    msg_id = add_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
        meta=payload.meta,
    )

    return {"message_id": msg_id}


@router.get("/list")
def list_conversations(user_id: str):
    """
    Return grouped conversation list:
    Today / Yesterday / Previous 7 days / Older.
    """
    return list_conversations_grouped(user_id)


@router.get("/{conversation_id}")
def conversation_details(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
):
    """
    Get full conversation with paginated messages.
    """
    data = get_conversation(conversation_id, limit=limit, offset=offset)
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return data


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str):
    """
    Delete a conversation.
    Messages auto-delete due to foreign key cascade.
    """
    supabase = get_supabase()

    resp = supabase.table("conversations").delete().eq("id", conversation_id).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"status": "deleted", "conversation_id": conversation_id}


@router.post("/{conversation_id}/rename")
def rename_conversation(conversation_id: str, payload: RenameConversationRequest):
    """
    Rename a conversation title.
    """
    supabase = get_supabase()

    resp = (
        supabase.table("conversations")
        .update({"topic_title": payload.new_title})
        .eq("id", conversation_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "status": "renamed",
        "conversation_id": conversation_id,
        "new_title": payload.new_title,
    }
