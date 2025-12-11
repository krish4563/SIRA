# services/embeddings.py
from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_embedder():
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_text(text: str) -> List[float]:
    """Synchronous embedding (your original function)."""
    model = get_embedder()
    return model.encode([text], normalize_embeddings=True)[0].tolist()


async def get_embedding(text: str) -> List[float]:
    """
    Async wrapper for RAG pipeline.
    (Since sentence-transformers is CPU-bound, we just call the sync version)
    """
    if not text or not text.strip():
        return [0.0] * 384

    # Truncate long text
    text = text[:8000]

    return embed_text(text)


async def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts."""
    model = get_embedder()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()
