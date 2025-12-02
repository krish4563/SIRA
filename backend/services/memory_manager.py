# services/memory_manager.py

import os
import logging
from typing import List, Dict, Optional
from pinecone import Pinecone, ServerlessSpec

logger = logging.getLogger(__name__)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "sira-memory")

class MemoryManager:
    def __init__(self):
        if not PINECONE_API_KEY:
            self.index = None
            logger.warning("⚠️ Pinecone API Key missing. Memory will be disabled.")
            return

        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Create index if not exists
        existing_indexes = [i.name for i in self.pc.list_indexes()]
        if PINECONE_INDEX not in existing_indexes:
            try:
                self.pc.create_index(
                    name=PINECONE_INDEX,
                    dimension=384, # Matches all-MiniLM-L6-v2
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
            except Exception as e:
                logger.error(f"[MEMORY] Failed to create index: {e}")

        self.index = self.pc.Index(PINECONE_INDEX)

    async def upsert_text(
        self, 
        user_id: str, 
        text: str, 
        url: str, 
        title: str,
        conversation_id: str = "global",  # ✅ NEW: Context tracking
        topic: str = "general"            # ✅ NEW: Context tracking
    ):
        """
        Stores text in VectorDB with rich metadata for filtering.
        """
        if not self.index: return

        try:
            from services.embeddings import get_embedding
            vector = await get_embedding(text)
            
            # Create a unique ID based on URL or content hash
            vector_id = str(hash(url + text[:50])) 

            metadata = {
                "user_id": user_id,
                "text": text[:1000], # Store snippet for context
                "url": url,
                "title": title,
                "conversation_id": conversation_id,
                "topic": topic
            }

            self.index.upsert(vectors=[(vector_id, vector, metadata)])
            logger.info(f"[MEMORY] Stored vector for: {title[:30]}... (Topic: {topic})")
            
        except Exception as e:
            logger.error(f"[MEMORY] Upsert failed: {e}")

    async def search(
        self, 
        user_id: str, 
        query_embedding: List[float], 
        top_k: int = 5,
        filter_metadata: Optional[Dict] = None # ✅ NEW: Allow filtering
    ) -> List[Dict]:
        """
        Search for similar vectors.
        """
        if not self.index: return []

        try:
            # Base filter: Always restrict to current user
            query_filter = {"user_id": {"$eq": user_id}}
            
            # Apply extra filters (e.g. topic) if provided
            if filter_metadata:
                query_filter.update(filter_metadata)

            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=query_filter
            )

            return [
                {
                    "score": match["score"],
                    "text": match["metadata"].get("text", ""),
                    "url": match["metadata"].get("url", ""),
                    "title": match["metadata"].get("title", "Untitled"),
                    "source": "cached"
                }
                for match in results["matches"]
            ]
        except Exception as e:
            logger.error(f"[MEMORY] Search failed: {e}")
            return []