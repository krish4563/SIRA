import re
from urllib.parse import urlparse
from typing import Dict, Tuple, List

REPUTABLE_DOMAINS = {
    "arxiv.org": 0.9,
    "semanticscholar.org": 0.8,
    "acm.org": 0.9,
    "ieee.org": 0.95,
    "nature.com": 0.95,
    "science.org": 0.95,
    "springer.com": 0.9,
    "mdpi.com": 0.75,
    "medium.com": 0.5,
}

HEDGING = {"might","may","could","possibly","suggests","appears","we believe","we think"}
STRONG_EVIDENCE = {"dataset","benchmark","code","github","results","evaluation","experiment","reproducible","appendix","supplementary"}

def _domain_score(url: str) -> float:
    try:
        netloc = urlparse(url).netloc.lower()
        # remove subdomains
        parts = netloc.split(".")
        base = ".".join(parts[-2:]) if len(parts) >= 2 else netloc
        return REPUTABLE_DOMAINS.get(base, 0.6)  # default medium
    except Exception:
        return 0.5

def _evidence_score(text: str) -> float:
    t = text.lower()
    pos = sum(1 for k in STRONG_EVIDENCE if k in t)
    neg = sum(1 for k in HEDGING if k in t)
    # numbers hint at concrete claims
    nums = len(re.findall(r"\b\d+(\.\d+)?\b", t))
    score = 0.5 + min(pos * 0.08, 0.25) + min(nums * 0.01, 0.1) - min(neg * 0.05, 0.25)
    return max(0.1, min(score, 0.95))

def compute_credibility(doc: Dict) -> Tuple[float, List[str]]:
    """
    Heuristic v0:
      - source domain reputation
      - presence of evidence keywords / numbers
      - abstract length
    Returns: (score 0..1, reasons[])
    """
    url = doc.get("url", "") or ""
    abstract = (doc.get("abstract") or " ".join(doc.get("bullets", [])) or "")
    src = (doc.get("source") or "").lower()

    reasons = []
    score = 0.5

    # domain baseline
    dscore = _domain_score(url)
    score = 0.5 * score + 0.5 * dscore
    reasons.append(f"Domain score: {dscore:.2f}")

    # evidence
    escore = _evidence_score(abstract)
    score = 0.5 * score + 0.5 * escore
    reasons.append(f"Evidence score: {escore:.2f}")

    # abstract length bonus
    alen = len(abstract.split())
    if alen > 120:
        score += 0.05; reasons.append("Long abstract (+0.05)")
    elif alen < 30:
        score -= 0.05; reasons.append("Very short abstract (-0.05)")

    # source tag nudges
    if src == "arxiv":
        score += 0.05; reasons.append("Source=arXiv (+0.05)")
    if src in {"blog","unknown"}:
        score -= 0.05; reasons.append(f"Source={src} (-0.05)")

    score = float(max(0.0, min(score, 1.0)))
    return score, reasons
