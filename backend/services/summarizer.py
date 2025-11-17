# services/summarizer.py

"""
Summarizer module for SIRA.
Replaces:
- Ollama local inference
- HuggingFace BART pipeline

Uses OpenAI GPT-4.1-mini for fast, accurate summarization.
"""

import logging

from services.llm_client import summarize_text

logger = logging.getLogger(__name__)


def summarize_article(text: str, max_words: int = 120) -> str:
    """
    Summarize long text into a short, factual summary using GPT-4.1-mini.
    """
    if not text or len(text.strip()) == 0:
        return ""

    logger.info("[SUMMARY] Summarizing article (%d chars)", len(text))
    return summarize_text(text, max_words=max_words)
