"""
multi_retriever.py
--------------------------------------------------------
Adaptive multi-provider retriever for SIRA.
Routes search queries across APIs
(SerpAPI → Brave → DuckDuckGo → Offline Cache)
with:
- Weight-based provider selection
- Automatic quota tracking
- Simple rate limiting
--------------------------------------------------------
"""

import logging
import os
import time
from typing import Any, Dict, List

import requests

from services.retriever import get_offline_results, save_to_cache

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────
# ENV VARS
# ────────────────────────────────────────────────────────

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
BRAVE_KEY = os.getenv("BRAVE_KEY")

# ────────────────────────────────────────────────────────
# PROVIDER CONFIG + QUOTA + RATE LIMIT
# ────────────────────────────────────────────────────────

SEARCH_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "serpapi": {"weight": 1.0, "quota": 100, "healthy": True},
    "brave": {"weight": 0.8, "quota": 2000, "healthy": True},
    "duckduckgo": {"weight": 0.5, "quota": None, "healthy": True},
}

RATE_LIMITS: Dict[str, Dict[str, float]] = {
    # min_interval in seconds
    "serpapi": {"min_interval": 1.0, "last_call": 0.0},
    "brave": {"min_interval": 0.5, "last_call": 0.0},
    "duckduckgo": {"min_interval": 0.5, "last_call": 0.0},
}

# ────────────────────────────────────────────────────────
# PROVIDER IMPLEMENTATIONS
# ────────────────────────────────────────────────────────


def serpapi_search(topic: str) -> List[Dict[str, Any]]:
    """Fetch results from SerpAPI (Google Search)."""
    try:
        if not SERPAPI_KEY:
            raise ValueError("SERPAPI_KEY missing in env")

        url = "https://serpapi.com/search"
        params = {
            "q": topic,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": 5,
        }

        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        results: List[Dict[str, Any]] = []
        for item in data.get("organic_results", []):
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "snippet": item.get("snippet", ""),
                }
            )

        logger.info("[SERPAPI] %d results for '%s'", len(results), topic)
        return results
    except Exception as e:
        logger.warning("[SERPAPI ERROR] %s", e)
        return []


def brave_search(topic: str) -> List[Dict[str, Any]]:
    """Fetch results from Brave Search."""
    try:
        if not BRAVE_KEY:
            raise ValueError("BRAVE_KEY missing in env")

        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": BRAVE_KEY,
        }
        params = {"q": topic, "count": 5}

        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        results: List[Dict[str, Any]] = []
        for item in data.get("web", {}).get("results", []):
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("description", ""),
                }
            )

        logger.info("[BRAVE] %d results for '%s'", len(results), topic)
        return results
    except Exception as e:
        logger.warning("[BRAVE ERROR] %s", e)
        return []


def ddg_search(topic: str) -> List[Dict[str, Any]]:
    """DuckDuckGo 'logical' provider – actually just offline cache here."""
    logger.info("[DDG] Using offline fallback for '%s'", topic)
    return get_offline_results(topic)


PROVIDER_FUNCTIONS = {
    "serpapi": serpapi_search,
    "brave": brave_search,
    "duckduckgo": ddg_search,
}

# ────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ────────────────────────────────────────────────────────


def normalize(results: List[Dict[str, Any]], provider: str) -> List[Dict[str, Any]]:
    """Normalize field names and attach provider info."""
    norm: List[Dict[str, Any]] = []
    for r in results:
        norm.append(
            {
                "title": r.get("title") or "Untitled",
                "url": r.get("url") or "",
                "snippet": r.get("snippet") or r.get("text") or "",
                "provider": provider,
            }
        )
    return dedupe(norm)


def dedupe(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in results:
        key = (r["url"], r["title"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def pick_provider() -> str:
    """Pick highest-weight healthy provider with remaining quota."""
    candidates = []
    for name, meta in SEARCH_PROVIDERS.items():
        quota_ok = meta["quota"] is None or meta["quota"] > 0
        if meta["healthy"] and quota_ok:
            candidates.append((name, meta["weight"]))

    if not candidates:
        # If everything looks dead, fall back to DDG/offline
        return "duckduckgo"

    # highest weight
    return max(candidates, key=lambda x: x[1])[0]


def mark_success(provider: str):
    provider_meta = SEARCH_PROVIDERS[provider]
    provider_meta["weight"] = min(1.0, provider_meta["weight"] + 0.05)
    provider_meta["healthy"] = True

    if provider_meta["quota"] is not None:
        provider_meta["quota"] -= 1
        if provider_meta["quota"] <= 0:
            provider_meta["healthy"] = False
            logger.warning(
                "[QUOTA] Provider '%s' has exhausted its quota; marking unhealthy.",
                provider,
            )


def mark_failure(provider: str):
    provider_meta = SEARCH_PROVIDERS[provider]
    provider_meta["weight"] = max(0.1, provider_meta["weight"] - 0.1)
    provider_meta["healthy"] = False
    logger.warning("[HEALTH] Provider '%s' marked unhealthy", provider)


def apply_rate_limit(provider: str):
    """Simple per-provider rate limiting."""
    rl = RATE_LIMITS.get(provider)
    if not rl:
        return
    now = time.time()
    elapsed = now - rl["last_call"]
    wait = rl["min_interval"] - elapsed
    if wait > 0:
        time.sleep(wait)
    rl["last_call"] = time.time()


# ────────────────────────────────────────────────────────
# MAIN ENTRYPOINT
# ────────────────────────────────────────────────────────


def search_and_extract(topic: str) -> List[Dict[str, Any]]:
    """
    Unified search entrypoint for the pipeline.
    - Picks best provider (SerpAPI → Brave → DDG/Offline)
    - Applies rate limiting
    - Tracks quota & provider health
    - Saves successful results to offline cache
    """
    provider = pick_provider()
    logger.info("[RETRIEVER] Using provider '%s' for topic '%s'", provider, topic)

    apply_rate_limit(provider)

    try:
        raw_results = PROVIDER_FUNCTIONS[provider](topic)

        if not raw_results:
            raise ValueError("Empty results from provider")

        # Track success & quota
        mark_success(provider)

        # Save full results (snippets or text) into offline cache (which will expand to full HTML where needed)
        save_to_cache(topic, raw_results)

        # Normalize for downstream pipeline (summarizer, critic, KG)
        return normalize(raw_results, provider)

    except Exception as e:
        logger.warning(
            "[RETRIEVER] Provider '%s' failed for '%s': %s", provider, topic, e
        )
        mark_failure(provider)
        # recursive retry with another provider
        return search_and_extract(topic)
