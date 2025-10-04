import httpx
from typing import List, Dict

ARXIV_API = "http://export.arxiv.org/api/query"

async def fetch_arxiv(topic: str, max_results: int = 5) -> List[Dict]:
    """
    Fetch papers from arXiv API for a given topic.
    Returns a list of dicts with title, abstract, url, and source.
    """
    query = f"search_query=all:{topic}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{ARXIV_API}?{query}")

    text = response.text
    entries = []

    # Simple string parsing (arXiv returns Atom XML)
    for block in text.split("<entry>")[1:]:
        try:
            title = block.split("<title>")[1].split("</title>")[0].strip()
            summary = block.split("<summary>")[1].split("</summary>")[0].strip()
            link = block.split("<id>")[1].split("</id>")[0].strip()
            entries.append({
                "title": title,
                "abstract": summary,
                "url": link,
                "source": "arXiv"
            })
        except Exception:
            continue

    return entries
