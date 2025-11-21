# services/llm_diff.py

import logging

from services.llm_client import MODEL, client  # use shared GPT model

logger = logging.getLogger(__name__)


def llm_compare_runs(
    previous_summary: str, latest_summary: str, topic: str = "Unknown Topic"
) -> str:
    """
    Generate a meaningful diff between two research summaries using GPT-4.1-mini.
    """

    prompt = f"""
You are an expert analysis system comparing two research summaries from an automated research agent.

Topic: {topic}

Your job:
- Identify meaningful NEW information in the latest run
- Point out information that DISAPPEARED compared to the previous run
- Detect shifts in emphasis, tone, or sentiment
- Detect contradictions or corrections
- Summarize differences clearly in a professional bullet list
- Finish with a short 2–3 line conclusion

Previous Run Summary:
---------------------
{previous_summary}

Latest Run Summary:
-------------------
{latest_summary}

Now produce the structured comparison in this format:

### 🔹 New Insights
- ...

### 🔹 Missing / Removed Insights
- ...

### 🔹 Changes in Tone / Emphasis
- ...

### 🔹 Contradictions / Anomalies
- ...

### 🔹 Final Conclusion
- ...
"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
        )
        return resp.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"[LLM-DIFF] Error generating diff: {e}")
        return "LLM diff unavailable due to backend error."
