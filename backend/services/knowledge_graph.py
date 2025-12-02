# backend/services/knowledge_graph.py
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

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
    """
    Build an advanced knowledge graph using GPT-4.1-mini with strict JSON output.
    """
    if not text or not text.strip():
        return {"nodes": [], "edges": [], "counts": {"nodes": 0, "edges": 0}}

    prompt = KG_PROMPT.replace("{TEXT}", text[:15000])  # safe limit

    completion = await run_chat_completion(prompt, json_mode=True)

    if not completion:
        return empty_graph()

    # Try strict JSON load
    try:
        kg = json.loads(completion)
        return finalize_graph(kg)
    except Exception:
        # Try auto-repair
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
    """
    Validate & deduplicate nodes/edges.
    Convert into Cytoscape-format structure (with .data wrapper).
    """
    if not isinstance(kg, dict):
        return empty_graph()

    raw_nodes = kg.get("nodes", [])
    raw_edges = kg.get("edges", [])

    node_map = {}
    edge_set = set()
    final_nodes = []
    final_edges = []

    # ---- NODES ---- (limit to 50 for performance)
    for n in raw_nodes[:100]:  # ✅ Limit input
        if not isinstance(n, dict):
            continue

        nid = normalize_id(n.get("id", ""))
        label = n.get("label") or n.get("id") or ""
        etype = n.get("type", "UNKNOWN")

        if not nid:
            continue

        if nid not in node_map:
            node_map[nid] = {"data": {"id": nid, "label": label, "type": etype}}
            
        # ✅ Stop if we have enough nodes
        if len(node_map) >= 50:
            break

    final_nodes = list(node_map.values())

    # ---- EDGES ---- (limit to 100)
    for e in raw_edges[:200]:  # ✅ Limit input
        if not isinstance(e, dict):
            continue

        src = normalize_id(e.get("source", ""))
        tgt = normalize_id(e.get("target", ""))
        rel = e.get("label", "").strip()

        if not (src and tgt and rel):
            continue
        
        # Only add edges between existing nodes
        if src not in node_map or tgt not in node_map:
            continue

        edge_key = (src, tgt, rel)
        if edge_key not in edge_set:
            edge_set.add(edge_key)
            final_edges.append({"data": {"source": src, "target": tgt, "label": rel}})
        
        # ✅ Stop if we have enough edges
        if len(final_edges) >= 100:
            break

    return {
        "nodes": final_nodes,
        "edges": final_edges,
        "counts": {
            "nodes": len(final_nodes),
            "edges": len(final_edges),
        },
    }


# ====================================================
# ==========  SPACY-BASED TRIPLET EXTRACTOR  =========
# ====================================================

import spacy

# Allowed spaCy entity labels
ENTITY_LABELS = {
    "PERSON",
    "ORG",
    "GPE",
    "LOC",
    "PRODUCT",
    "EVENT",
    "WORK_OF_ART",
    "FAC",
    "NORP",
}


def _get_nlp():
    try:
        return spacy.load("en_core_web_sm")
    except Exception:
        raise RuntimeError(
            "spaCy model 'en_core_web_sm' not found. Install it using:\n"
            "python -m spacy download en_core_web_sm"
        )


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    type: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _extract_entities(doc) -> List[Node]:
    nodes: Dict[str, Node] = {}
    for ent in doc.ents:
        if ent.label_ in ENTITY_LABELS:
            nid = _normalize(ent.text)
            if nid not in nodes:
                nodes[nid] = Node(id=nid, label=ent.text.strip(), type=ent.label_)
    return list(nodes.values())


def _relation_from_span(span_text: str) -> str:
    text = span_text.strip().lower()
    text = re.sub(r"[^a-z0-9\s\-_/]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"\b(the|a|an|of|and|to|in|for|with|on|as|by|from)\b", "", text
    ).strip()
    if not text:
        return "related_to"
    return text[:40]


def _extract_sentence_edges(doc) -> List[Edge]:
    edges: List[Edge] = []
    for sent in doc.sents:
        ents = [e for e in sent.ents if e.label_ in ENTITY_LABELS]
        if len(ents) < 2:
            continue

        ents_sorted = sorted(ents, key=lambda e: e.start_char)

        for i in range(len(ents_sorted) - 1):
            a, b = ents_sorted[i], ents_sorted[i + 1]
            between = sent.text[
                a.end_char - sent.start_char : b.start_char - sent.start_char
            ]
            rel = _relation_from_span(between)
            src = _normalize(a.text)
            tgt = _normalize(b.text)

            if src != tgt:
                edges.append(Edge(source=src, target=tgt, relation=rel))

    return edges


def _cooccurrence_edges(nodes: List[Node]) -> List[Edge]:
    out: List[Edge] = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            out.append(
                Edge(source=nodes[i].id, target=nodes[j].id, relation="co_occurs")
            )
    return out


def dedup_edges(edges: List[Edge]) -> List[Edge]:
    seen: Set[Tuple[str, str, str]] = set()
    out: List[Edge] = []
    for e in edges:
        key = (e.source, e.target, e.relation)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def extract_triplets_from_texts(texts: List[str]) -> Dict:
    """
    Input: list of doc strings (e.g., summaries).
    Output: { nodes: [{id,label,type}], edges: [{source,target,relation}] }
    """
    nlp = _get_nlp()
    node_map: Dict[str, Node] = {}
    all_edges: List[Edge] = []

    for t in texts:
        if not t or not t.strip():
            continue

        doc = nlp(t)
        nodes = _extract_entities(doc)

        for n in nodes:
            if n.id not in node_map:
                node_map[n.id] = n

        edges = _extract_sentence_edges(doc)
        if not edges and len(nodes) >= 2:
            edges = _cooccurrence_edges(nodes)

        all_edges.extend(edges)

    final_nodes = list(node_map.values())
    final_edges = dedup_edges(all_edges)

    return {
        "nodes": [
            {"data": {"id": n.id, "label": n.label, "type": n.type}}
            for n in final_nodes
        ],
        "edges": [
            {"data": {"source": e.source, "target": e.target, "label": e.relation}}
            for e in final_edges
        ],
        "counts": {"nodes": len(final_nodes), "edges": len(final_edges)},
    }
