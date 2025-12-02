# services/llm_client.py

import logging
import re
import os
from openai import OpenAI

# Load Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o-mini" 

if not OPENAI_API_KEY:
    print("⚠️ WARNING: OPENAI_API_KEY is missing. LLM features will default to fallbacks.")

client = OpenAI(api_key=OPENAI_API_KEY)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 1. CORE COMPLETION 
# ------------------------------------------------------------------
async def run_chat_completion(prompt: str, json_mode: bool = False) -> str:
    """Generic wrapper for OpenAI chat completions."""
    if not OPENAI_API_KEY:
        return ""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if json_mode else {"type": "text"},
            temperature=0.3, 
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"[LLM] Completion failed: {e}")
        return ""

# ------------------------------------------------------------------
# 2. SUMMARIZER 
# ------------------------------------------------------------------
def summarize_text(text: str, max_words: int = 150) -> str:
    """Summarizes raw text into a concise paragraph."""
    if not text or not OPENAI_API_KEY:
        return text[:500] + "..." 

    prompt = f"""
    Summarize the following text in under {max_words} words. 
    Focus on facts, dates, and key outcomes.
    
    TEXT:
    {text[:4000]}
    """
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"[LLM] Summarization failed: {e}")
        return text[:500] + "..."

# ------------------------------------------------------------------
# 3. EVALUATOR / CRITIC (Renamed back to evaluate_source)
# ------------------------------------------------------------------
def evaluate_source(url: str, content: str = "", title: str = "", topic: str = "") -> float:
    """
    Returns a float 0.0 - 1.0 representing credibility/relevance.
    Updated signature to support old calls (url, content) and new calls (title, topic).
    """
    if not OPENAI_API_KEY:
        return 0.5

    # Construct a robust prompt regardless of missing fields
    prompt = f"""
    Evaluate the credibility and relevance of this source.
    Topic: "{topic}"
    Title: {title}
    URL: {url}
    Content Snippet: {content[:500]}
    
    CRITERIA:
    - Official docs/gov/edu = High (0.9-1.0)
    - Reputable blogs/news = Medium (0.7-0.9)
    - Forums/Unknown = Low (0.1-0.4)
    - Irrelevant to topic = 0.0
    
    OUTPUT:
    Return ONLY a single number between 0.0 and 1.0.
    """
    
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10
        )
        resp_text = resp.choices[0].message.content.strip()
        
        # ✅ ROBUST PARSING (Finds number inside text)
        match = re.search(r"0\.\d+|1\.0|0|1", resp_text)
        if match:
            return float(match.group())
        
        return 0.5 
        
    except Exception as e:
        logger.error(f"[LLM] Eval failed: {e}")
        return 0.5

# ------------------------------------------------------------------
# 4. TITLE GENERATOR 
# ------------------------------------------------------------------
def generate_chat_title(first_message: str) -> str:
    """Generates a 3-5 word title."""
    if not first_message: return "New Chat"
    
    if OPENAI_API_KEY:
        try:
            prompt = f"Generate a 3-5 word concise title. No quotes.\n\nMessage: {first_message[:200]}"
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=15
            )
            return resp.choices[0].message.content.strip().replace('"', '')
        except Exception:
            pass 
    
    words = first_message.strip().split()
    return " ".join(words[:5]) + "..." if len(words) > 5 else first_message