# routers/conversations.py

from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from services.conversations import (
    add_message,
    create_conversation,
    get_conversation,
    list_conversations_grouped,
    generate_and_update_title
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
def post_message(
    conversation_id: str, 
    payload: MessageRequest, 
    background_tasks: BackgroundTasks # <--- Inject BackgroundTasks
):
    """
    Add a message. If it's the first user message, auto-generate the title.
    """
    if payload.role not in ("user", "agent"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'agent'")

    msg_id = add_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
        meta=payload.meta,
    )

    # ---------------------------------------------------------
    # AUTO-TITLE CHECK
    # ---------------------------------------------------------
    if payload.role == "user":
        # Check current state of conversation
        data = get_conversation(conversation_id, limit=5)
        conversation = data.get("conversation", {})
        messages = data.get("messages", [])
        
        current_title = conversation.get("topic_title", "")
        
        # Count how many messages the user has sent
        user_message_count = sum(1 for m in messages if m.get("role") == "user")

        print(f"\n[DEBUG] Title Logic Check:")
        print(f" - Current Title: '{current_title}'")
        print(f" - User Msg Count: {user_message_count}")

        # LOGIC: Rename if title is generic OR if this is the very first user message
        is_generic_title = current_title.strip().lower() in ["new chat", "untitled", "new research"]
        is_first_message = user_message_count <= 1

        if is_generic_title or is_first_message:
            print("🚀 TRIGGERING Auto-Title Background Task!")
            background_tasks.add_task(
                generate_and_update_title, 
                conversation_id, 
                payload.content
            )
        else:
            print("🛑 SKIPPING Auto-Title (Title is set and conversation is ongoing)")

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