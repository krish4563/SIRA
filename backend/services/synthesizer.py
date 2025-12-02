# services/synthesizer.py
from typing import List, Dict
from services.llm_client import run_chat_completion

async def synthesize_answer(
    query: str, 
    sources: List[Dict], 
    conversation_history: List[Dict] = []
) -> str:
    # 1. Format Context
    context_text = ""
    for idx, source in enumerate(sources, 1):
        content = source.get("summary") or source.get("text") or ""
        context_text += f"SOURCE [{idx}]: {source.get('url')}\nCONTENT: {content[:1000]}\n\n"

    # 2. Format History
    history_text = ""
    if conversation_history:
        for msg in conversation_history[-3:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_text += f"{role.upper()}: {content}\n"

    # 3. Prompt
    prompt = f"""
    You are a deep research assistant. Answer the user's query based STRICTLY on the provided sources.
    
    USER QUERY: {query}
    
    CONVERSATION HISTORY:
    {history_text}
    
    AVAILABLE SOURCES:
    {context_text}
    
    INSTRUCTIONS:
    1. Answer the query comprehensively.
    2. Use Markdown (bold, headers, lists).
    3. CITE sources inline using brackets like [1].
    4. If sources are insufficient, admit it.
    """

    # 4. Call
    return await run_chat_completion(prompt)