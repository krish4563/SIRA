# backend/services/embeddings.py

from typing import List

from openai import OpenAI

client = OpenAI()

EMBED_MODEL = "text-embedding-3-large"
MAX_INPUT_CHARS = 8000


async def get_embedding(text: str) -> List[float]:
    """
    Generate a single embedding using OpenAI's embedding model.
    Safe for Render deployment (no heavy local models).
    """
    if not text or not text.strip():
        # OpenAI embedding size for this model is 3072
        return [0.0] * 3072

    # Truncate long text to avoid API issues
    text = text[:MAX_INPUT_CHARS]

    response = client.embeddings.create(model=EMBED_MODEL, input=text)

    return response.data[0].embedding


async def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for multiple documents at once.
    More efficient than calling single embeddings in a loop.
    """
    # Clean & truncate each input
    cleaned = [(t[:MAX_INPUT_CHARS] if t else "") for t in texts]

    response = client.embeddings.create(model=EMBED_MODEL, input=cleaned)

    return [item.embedding for item in response.data]
