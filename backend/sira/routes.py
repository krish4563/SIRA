from fastapi import APIRouter, Query
from .fetcher import fetch_arxiv
from .summarizer import note_style_summary
from .critic import compute_credibility
from .memory import VectorMemory


vm = VectorMemory()

router = APIRouter(prefix="/api", tags=["core"])

@router.get("/hello")
def hello():
    return {"msg": "SIRA backend alive"}

from fastapi import APIRouter, Query
from .fetcher import fetch_arxiv

router = APIRouter(prefix="/api", tags=["core"])

@router.get("/hello")
def hello():
    return {"msg": "SIRA backend alive"}

@router.get("/fetch")
async def fetch(topic: str = Query(..., description="Research topic"),
                max_results: int = 5):
    """
    Fetch research papers from arXiv for a given topic.
    Example: /api/fetch?topic=kubernetes+autoscaling&max_results=3
    """
    docs = await fetch_arxiv(topic, max_results)
    return {"count": len(docs), "docs": docs}

@router.post("/summarize")
def summarize(doc: dict):
    """
    Summarize a single document into note-style bullets.
    Pass in JSON with {title, abstract, url, source}.
    """
    return note_style_summary(doc)

@router.post("/critic")
def critic(doc: dict):
    """
    Compute a heuristic credibility score for a document or summary.
    Accepts either {title, abstract, url, source} or {title, bullets[], url, source}.
    """
    score, reasons = compute_credibility(doc)
    return {"credibility": score, "reasons": reasons}

@router.get("/pipeline/research")
async def pipeline_research(topic: str, max_results: int = 3):
    """
    Run: fetch -> summarize -> critic -> add to memory
    """
    docs = await fetch_arxiv(topic, max_results)
    outputs = []

    for d in docs:
        # summarize
        s = note_style_summary(d)

        # critic
        score, reasons = compute_credibility({**d, **s})
        s["credibility"] = score
        s["credibility_reasons"] = reasons

        # add to memory
        vm.add(s)
        outputs.append(s)

    return {"topic": topic, "count": len(outputs), "items": outputs}



@router.post("/memory/add")
def memory_add(doc: dict):
    """
    Add a summarized document to vector memory.
    Expect {title, bullets[] or abstract, url, source, ...}
    """
    vm.add(doc)
    return {"ok": True, "count": len(vm.docs)}

@router.get("/memory/search")
def memory_search(q: str, k: int = 5):
    """
    Vector search over stored summaries.
    """
    return vm.search(q, k)
