import json
import os
import random
import time
from typing import Dict, List

import httpx
import trafilatura
from duckduckgo_search import DDGS

# Path to offline cache
DATA_PATH = os.path.join(os.path.dirname(__file__), "../data/offline_cache.json")


# ──────────────────────────────────────────────────────────────
# LOAD & SAVE OFFLINE CACHE
# ──────────────────────────────────────────────────────────────


def _load_offline_cache() -> List[Dict]:
    """Load offline cache safely."""
    if not os.path.exists(DATA_PATH):
        return []

    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print("[WARN] Invalid offline cache. Resetting.")
        return []


def save_to_cache(topic: str, results: List[Dict]):
    """
    Save normalized search results (from any provider) into the offline cache.
    Used by multi_retriever.py.
    """
    cache = _load_offline_cache()
    existing_urls = {c["url"] for c in cache}

    added = 0
    for r in results:
        url = r.get("url")
        if not url or url in existing_urls:
            continue

        cache.append(
            {
                "topic": topic.lower().strip(),
                "title": r.get("title", "Untitled"),
                "url": url,
                "text": r.get("snippet") or r.get("text") or "",
            }
        )
        added += 1

    if added > 0:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        print(f"[CACHE] Added {added} new entries for '{topic}'")
    else:
        print(f"[CACHE] No new entries for '{topic}'")


def get_offline_results(topic: str) -> List[Dict]:
    """Return cached results for a given topic."""
    topic = topic.lower().strip()
    cache = _load_offline_cache()

    matches = [c for c in cache if topic in c.get("topic", "").lower()]

    if matches:
        print(f"[OFFLINE] Returning {len(matches)} cached results for '{topic}'.")
    else:
        print(f"[OFFLINE] No cached results found for '{topic}'.")

    return matches


# ──────────────────────────────────────────────────────────────
# HTML TEXT DOWNLOADER (USED BY LIVE DDG MODE)
# ──────────────────────────────────────────────────────────────


async def fetch_text(url: str) -> str:
    """Download webpage and extract readable text."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                url, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
            )
            r.raise_for_status()

        return (
            trafilatura.extract(r.text, include_comments=False, include_tables=False)
            or ""
        )
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────
# DUCKDUCKGO RETRIEVER (LIVE + OFFLINE FALLBACK)
# ──────────────────────────────────────────────────────────────


def search_and_extract(topic: str, max_results: int = 3, retries: int = 3):
    """
    DuckDuckGo live retriever + offline cache fallback.
    Used only when multi_retriever calls DDG.
    """
    for attempt in range(retries):
        try:
            ddg = DDGS()
            results = []

            for r in ddg.text(topic, max_results=max_results):
                url = r.get("href") or r.get("url")
                if not url:
                    continue

                downloaded = trafilatura.fetch_url(url)
                if not downloaded:
                    continue

                content = trafilatura.extract(
                    downloaded, include_comments=False, include_tables=False
                )

                if content and len(content.split()) > 50:
                    results.append(
                        {
                            "title": r.get("title") or "Untitled",
                            "url": url,
                            "text": content,
                        }
                    )

            if results:
                print(f"[DDG] Retrieved {len(results)} live results for '{topic}'.")
                save_to_cache(topic, results)  # <-- Cache live result
                return results

        except Exception as e:
            print(f"[DDG WARN] Attempt {attempt + 1}/{retries} failed: {e}")
            time.sleep(3 + random.randint(1, 3))

    # Offline fallback
    print(f"[DDG] Live search failed → Using offline cache for '{topic}'")
    return get_offline_results(topic)
