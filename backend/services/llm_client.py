# services/llm_client.py

import logging

from openai import APIConnectionError, OpenAI, OpenAIError, RateLimitError

from config import settings

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
