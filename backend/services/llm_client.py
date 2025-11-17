# services/llm_client.py
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "gpt-4.1-mini")
CRITIC_MODEL = os.getenv("CRITIC_MODEL", "gpt-4.1-mini")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing in environment!")

client = OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────
# SUMMARIZER
# ─────────────────────────────────────────────


def summarize_text(text: str, max_words: int = 120) -> str:
    """Summarize long text into a compact summary."""
    logger.info("[LLM] Summarizing text (%d chars)...", len(text))

    prompt = f"""
    Summarize the following content in under {max_words} words,
    keeping only factual and essential information.
    Avoid fluff or generic statements.

    --- TEXT START ---
    {text}
    --- TEXT END ---
    """

    try:
        resp = client.chat.completions.create(
            model=SUMMARIZER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()

    except Exception as e:
        logger.error("[LLM ERROR - summarize_text] %s", e)
        return text[:max_words]


# ─────────────────────────────────────────────
# CREDIBILITY CRITIC
# ─────────────────────────────────────────────


def evaluate_source(url: str, content: str) -> float:
    """Return a credibility score between 0 and 1."""
    logger.info("[LLM] Evaluating credibility for %s", url)

    prompt = f"""
    Evaluate the credibility of the following source and give a
    score between 0 and 1 only. Do NOT explain.

    URL: {url}

    Content snippet:
    {content[:500]}

    Return ONLY a number between 0 and 1.
    """

    try:
        resp = client.chat.completions.create(
            model=CRITIC_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        output = resp.choices[0].message.content.strip()

        try:
            val = float(output)
            return max(0.0, min(1.0, val))
        except:
            return 0.5

    except Exception as e:
        logger.error("[LLM ERROR - evaluate_source] %s", e)
        return 0.5
