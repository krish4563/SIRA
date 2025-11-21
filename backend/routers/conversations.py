# routers/conversations.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.conversations import (
    add_message,
    create_conversation,
    get_conversation,
    list_conversations_grouped,
)

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


# ------------------------------
# Endpoints
# ------------------------------


@router.post("/start")
def start_conversation(payload: StartConversationRequest):
    conv_id = create_conversation(
        user_id=payload.user_id,
        topic_title=payload.topic_title,
    )
    return {"conversation_id": conv_id}


@router.post("/{conversation_id}/message")
def post_message(conversation_id: str, payload: MessageRequest):
    if payload.role not in ("user", "agent"):
        raise HTTPException(status_code=400, detail="Role must be user or agent")

    msg_id = add_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
    )
    return {"message_id": msg_id}


@router.get("/list")
def list_conversations(user_id: str):
    return list_conversations_grouped(user_id)


@router.get("/{conversation_id}")
def conversation_details(conversation_id: str):
    data = get_conversation(conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return data
