from typing import List, Dict
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

class VectorMemory:
    """
    Minimal in-process vector store:
      - add(dict) → stores doc + embedding
      - search(query, k) → returns top-k docs with scores
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()
        # cosine similarity via inner product on normalized vectors
        self.index = faiss.IndexFlatIP(self.dim)
        self.docs: List[Dict] = []

    def _embed(self, texts: List[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True)
        return np.array(vecs, dtype="float32")

    def add(self, doc: Dict):
        # Build a dense text field from title + bullets/abstract
        text = " ".join([
            doc.get("title", ""),
            " ".join(doc.get("bullets", [])) or doc.get("abstract", "") or "",
        ]).strip()
        if not text:
            return
        vec = self._embed([text])
        self.index.add(vec)
        self.docs.append(doc)

    def search(self, query: str, k: int = 5) -> List[Dict]:
        qvec = self._embed([query])
        scores, idxs = self.index.search(qvec, k)
        results = []
        for i in range(len(idxs[0])):
            idx = int(idxs[0][i])
            if idx < 0 or idx >= len(self.docs):
                continue
            results.append({
                "score": float(scores[0][i]),
                "doc": self.docs[idx]
            })
        return results
