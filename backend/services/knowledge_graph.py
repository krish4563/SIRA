# backend/services/knowledge_graph.py
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

# ❌ spaCy removed (Render cannot compile blis/thinc)
# import spacy
from services.llm_client import run_chat_completion

# ====================================================
# ===================  GPT KG PROMPT  =================
# ====================================================

KG_PROMPT = """
You are an expert Knowledge Graph extractor.

Your task:
1. Extract **entities** with labels and types.
2. Extract **relationships** between entities (subject → relation → object).
3. Output strictly **valid JSON only**, following the required schema.

ENTITY TYPES allowed:
PERSON, ORG, PRODUCT, TECH, FRAMEWORK, COUNTRY, EVENT,
TOOL, CONCEPT, SKILL, METRIC, POLICY, DATASET, UNKNOWN

RELATION RULES:
- Keep relation labels short, 1–4 words max.
- No long sentences.
- No duplicate relations.

STRICT OUTPUT SCHEMA:
{
  "nodes": [
    { "id": "kubernetes", "label": "Kubernetes", "type": "TECH" }
  ],
  "edges": [
    { "source": "kubernetes", "target": "cloud-native", "label": "enables" }
  ]
}

Rules:
- IDs must be lowercase, hyphen-separated.
- JSON only — no explanations, no markdown.
- If unsure, classify entity type as "UNKNOWN".

Now extract the knowledge graph from this text:

TEXT:
-----
{TEXT}
-----
"""


# ====================================================
# =========  GPT-BASED KNOWLEDGE GRAPH EXTRACTOR  =====
# ====================================================


async def extract_knowledge_graph(text: str) -> Dict:
    """Build a knowledge graph using GPT (strict JSON mode)."""
    if not text or not text.strip():
        return empty_graph()

    prompt = KG_PROMPT.replace("{TEXT}", text[:15000])

    completion = await run_chat_completion(prompt, json_mode=True)

    if not completion:
        return empty_graph()

    try:
        kg = json.loads(completion)
        return finalize_graph(kg)
    except Exception:
        # Try JSON repair path
        try:
            cleaned = completion.strip().split("```json")[-1].split("```")[0].strip()
            kg = json.loads(cleaned)
            return finalize_graph(kg)
        except Exception:
            return empty_graph()


def empty_graph():
    return {"nodes": [], "edges": [], "counts": {"nodes": 0, "edges": 0}}


def normalize_id(text: str) -> str:
    return text.lower().replace(" ", "-").replace(":", "").strip()


def finalize_graph(kg: Dict) -> Dict:
    """Deduplicate, sanitize, and convert into cytoscape format."""
    if not isinstance(kg, dict):
        return empty_graph()

    raw_nodes = kg.get("nodes", [])
    raw_edges = kg.get("edges", [])

    node_map = {}
    edge_set = set()
    final_nodes = []
    final_edges = []

    # ---- NODES ----
    for n in raw_nodes[:100]:
        if not isinstance(n, dict):
            continue

        nid = normalize_id(n.get("id", ""))
        label = n.get("label") or n.get("id") or ""
        etype = n.get("type", "UNKNOWN")

        if not nid:
            continue

        if nid not in node_map:
            node_map[nid] = {"data": {"id": nid, "label": label, "type": etype}}

        if len(node_map) >= 50:
            break

    final_nodes = list(node_map.values())

    # ---- EDGES ----
    for e in raw_edges[:200]:
        if not isinstance(e, dict):
            continue

        src = normalize_id(e.get("source", ""))
        tgt = normalize_id(e.get("target", ""))
        rel = e.get("label", "").strip()

        if not (src and tgt and rel):
            continue

        if src not in node_map or tgt not in node_map:
            continue

        key = (src, tgt, rel)
        if key not in edge_set:
            edge_set.add(key)
            final_edges.append({"data": {"source": src, "target": tgt, "label": rel}})

        if len(final_edges) >= 100:
            break

    return {
        "nodes": final_nodes,
        "edges": final_edges,
        "counts": {"nodes": len(final_nodes), "edges": len(final_edges)},
    }


# ====================================================
# ==========  SPACY TRIPLET EXTRACTOR (DISABLED) =====
# ====================================================

"""
⚠️ spaCy-based extractor is disabled for deployment.

Render cannot install spaCy 3.x due to native dependencies (blis, thinc).
We keep the code commented for future local use / research extension.
"""

# ENTITY_LABELS = {
#     "PERSON", "ORG", "GPE", "LOC", "PRODUCT",
#     "EVENT", "WORK_OF_ART", "FAC", "NORP",
# }

# def _get_nlp():
#     try:
#         return spacy.load("en_core_web_sm")
#     except Exception:
#         raise RuntimeError("spaCy model not installed.")

# @dataclass(frozen=True)
# class Node:
#     id: str
#     label: str
#     type: str
#
# @dataclass(frozen=True)
# class Edge:
#     source: str
#     target: str
#     relation: str
#
# def _normalize(text: str) -> str:
#     return re.sub(r"\s+", " ", text.strip()).lower()
#
# def _extract_entities(doc) -> List[Node]:
#     nodes = {}
#     for ent in doc.ents:
#         if ent.label_ in ENTITY_LABELS:
#             nid = _normalize(ent.text)
#             if nid not in nodes:
#                 nodes[nid] = Node(id=nid, label=ent.text.strip(), type=ent.label_)
#     return list(nodes.values())
#
# def _relation_from_span(text: str) -> str:
#     txt = re.sub(r"[^a-z0-9\s\-_/]", "", text.lower()).strip()
#     txt = re.sub(r"\s+", " ", txt)
#     return txt[:40] if txt else "related_to"
#
# def _extract_sentence_edges(doc) -> List[Edge]:
#     edges = []
#     for sent in doc.sents:
#         ents = [e for e in sent.ents if e.label_ in ENTITY_LABELS]
#         if len(ents) < 2:
#             continue
#         ents_sorted = sorted(ents, key=lambda e: e.start_char)
#         for a, b in zip(ents_sorted, ents_sorted[1:]):
#             between = sent.text[a.end_char - sent.start_char : b.start_char - sent.start_char]
#             rel = _relation_from_span(between)
#             edges.append(Edge(source=_normalize(a.text), target=_normalize(b.text), relation=rel))
#     return edges
#
# def extract_triplets_from_texts(texts: List[str]) -> Dict:
#     nlp = _get_nlp()
#     node_map = {}
#     edges = []
#     for t in texts:
#         if not t.strip():
#             continue
#         doc = nlp(t)
#         nodes = _extract_entities(doc)
#         for n in nodes:
#             node_map.setdefault(n.id, n)
#         sent_edges = _extract_sentence_edges(doc)
#         edges.extend(sent_edges)
#
#     return {
#         "nodes": [{"data": {"id": n.id, "label": n.label, "type": n.type}} for n in node_map.values()],
#         "edges": [{"data": {"source": e.source, "target": e.target, "label": e.relation}} for e in edges],
#         "counts": {"nodes": len(node_map), "edges": len(edges)},
#     }
