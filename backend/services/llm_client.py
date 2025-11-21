# services/llm_client.py

import logging
from typing import Dict

from config import settings
from openai import APIConnectionError, OpenAI, OpenAIError, RateLimitError

logger = logging.getLogger(__name__)

# ============================================================
# CONFIG
# ============================================================

OPENAI_API_KEY = settings.openai_api_key
MODEL = settings.summarizer_model  # "gpt-4.1-mini" by default

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing in .env file")

# Force correct endpoint (prevents conflicts from OPENAI_BASE_URL)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.openai.com/v1",
)

# ============================================================
# SUMMARIZER
# ============================================================


def summarize_text(text: str, max_words: int = 120) -> str:
    """Summarize using GPT in a safe and stable way."""
    if not text or not text.strip():
        return ""

    logger.info("[LLM] Summarizing text (%d chars)...", len(text))

    prompt = f"""
Summarize the following content in under {max_words} words.
Keep it factual, concise, structured, and avoid hallucinations.

TEXT:
{text}
"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()

    except APIConnectionError as e:
        logger.error("[LLM ERROR - summarize_text] APIConnectionError: %r", e)
    except RateLimitError as e:
        logger.error("[LLM ERROR - summarize_text] RateLimitError: %r", e)
    except OpenAIError as e:
        logger.error("[LLM ERROR - summarize_text] OpenAIError: %r", e)
    except Exception as e:
        logger.error("[LLM ERROR - summarize_text] Unexpected: %r", e)

    return "Summary unavailable due to API error."


# ============================================================
# CREDIBILITY SCORING
# ============================================================


def evaluate_source(url: str, content: str) -> float:
    """Evaluate credibility 0–1 using GPT."""
    logger.info("[LLM] Evaluating credibility for: %s", url)

    prompt = f"""
Return ONLY a number between 0 and 1 representing credibility.

URL: {url}

Content snippet:
{content[:500]}
"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        output = resp.choices[0].message.content.strip()

        # Convert to float safely
        try:
            value = float(output)
            return max(0.0, min(1.0, value))
        except ValueError:
            logger.warning("[LLM WARN] Non-numeric credibility output: %r", output)
            return 0.5

    except APIConnectionError as e:
        logger.error("[LLM ERROR - evaluate_source] APIConnectionError: %r", e)
    except RateLimitError as e:
        logger.error("[LLM ERROR - evaluate_source] RateLimitError: %r", e)
    except OpenAIError as e:
        logger.error("[LLM ERROR - evaluate_source] OpenAIError: %r", e)
    except Exception as e:
        logger.error("[LLM ERROR - evaluate_source] Unexpected: %r", e)

    return 0.5


# ============================================================
# GENERIC CHAT COMPLETION (KG + others)
# ============================================================


async def run_chat_completion(prompt: str, json_mode: bool = False) -> str:
    """
    Wrapper for async-style GPT calls.
    Safe for JSON-mode (used by Knowledge Graph).
    """
    try:
        if json_mode:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
        else:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )

        return resp.choices[0].message.content.strip()

    except APIConnectionError as e:
        logger.error("[LLM ERROR - run_chat_completion] APIConnectionError: %r", e)
    except RateLimitError as e:
        logger.error("[LLM ERROR - run_chat_completion] RateLimitError: %r", e)
    except OpenAIError as e:
        logger.error("[LLM ERROR - run_chat_completion] OpenAIError: %r", e)
    except Exception as e:
        logger.error("[LLM ERROR - run_chat_completion] Unexpected: %r", e)

    return ""


def diff_research_runs(latest: Dict, previous: Dict) -> str:
    """
    Use GPT-4.1-mini to explain the difference between two auto-research runs.
    Both dicts are rows from `auto_research_history`.

    Returns a short, structured natural-language diff.
    """
    # Safe extraction with fallbacks
    topic = latest.get("topic") or previous.get("topic") or "Unknown topic"

    # Ensure we always have strings
    latest_summary = (latest.get("full_summary_text") or "").strip()
    previous_summary = (previous.get("full_summary_text") or "").strip()

    # Hard length cap to avoid huge prompt
    max_chars = 4000
    latest_summary = latest_summary[:max_chars]
    previous_summary = previous_summary[:max_chars]

    meta_latest = {
        "status": latest.get("status"),
        "result_count": latest.get("result_count"),
        "kg_nodes": latest.get("kg_nodes"),
        "kg_edges": latest.get("kg_edges"),
        "run_finished_at": latest.get("run_finished_at"),
    }
    meta_previous = {
        "status": previous.get("status"),
        "result_count": previous.get("result_count"),
        "kg_nodes": previous.get("kg_nodes"),
        "kg_edges": previous.get("kg_edges"),
        "run_finished_at": previous.get("run_finished_at"),
    }

    meta_block = (
        f"TOPIC: {topic}\n\n"
        f"PREVIOUS RUN META:\n{meta_previous}\n\n"
        f"LATEST RUN META:\n{meta_latest}\n"
    )

    prompt = f"""
You are an assistant that compares two research runs on the same topic.

You are given:
- High-level metadata for the previous and latest runs
- Aggregated summaries of what each run found

Your job:
1. Explain in 5–8 bullet points what CHANGED between the previous and latest run.
2. Focus on:
   - New insights or sources that appear in the latest run
   - Insights that disappeared or became less prominent
   - Changes in knowledge graph complexity (nodes/edges)
   - Any change in reliability or confidence (if visible)
3. Keep it neutral, factual, and concise.
4. If there is very little difference, explicitly say that the runs are largely similar.

{meta_block}

----- PREVIOUS RUN SUMMARY -----
{previous_summary or "(no summary text)"}

----- LATEST RUN SUMMARY -----
{latest_summary or "(no summary text)"}
"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise, neutral research comparison assistant.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=350,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # On any error, fall back to a minimal string so the API still works
        logging.getLogger(__name__).error("[LLM DIFF] Error generating diff: %s", e)
        return (
            "Unable to generate semantic diff for these runs due to an internal error."
        )
