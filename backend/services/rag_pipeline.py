# backend/services/rag_pipeline.py

import logging
from typing import Dict, List, Optional, Tuple

# Uses NEW OpenAI-based embedding functions
from services.embeddings import get_embedding
from services.llm_client import run_chat_completion

# Internal modules
from services.memory_manager import MemoryManager
from services.multi_retriever import search_and_extract
from services.realtime_retriever import fetch_realtime

logger = logging.getLogger(__name__)

# Thresholds for relevance
THRESHOLD_HIGH = 0.82
THRESHOLD_MEDIUM = 0.70
THRESHOLD_MINIMUM = 0.40  # drop irrelevant results


class RAGPipeline:
    def __init__(self):
        self.mm = MemoryManager()

    # -------------------------------------------------------------
    # MAIN RETRIEVAL PIPELINE
    # -------------------------------------------------------------
    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_history: Optional[List[Dict]] = None,
        max_results: int = 5,
    ) -> Dict:
        logger.info(f"[RAG] Retrieving for: {query}")

        # 1. Query Rewriting Based on Context
        enhanced_query = await self._rewrite_query(query, conversation_history)

        # 2. Vector Search
        vector_results = await self._search_vectordb(enhanced_query, user_id, top_k=8)

        # 3. Remove junk
        valid_vectors = [
            r for r in vector_results if r.get("score", 0) > THRESHOLD_MINIMUM
        ]

        # 4. Decide strategy
        strategy, sources = await self._decide_strategy(
            query, valid_vectors, max_results
        )

        return {
            "sources": sources,
            "retrieval_strategy": strategy,
            "context_used": (enhanced_query != query),
        }

    # -------------------------------------------------------------
    # QUERY REWRITING
    # -------------------------------------------------------------
    async def _rewrite_query(self, query: str, history: Optional[List[Dict]]) -> str:
        """Uses LLM to convert query into a standalone question."""

        if not history or len(history) < 2:
            return query

        short_history = history[-4:]
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in short_history)

        prompt = f"""
        Rewrite the user's latest query to be standalone and self-contained.
        Only rewrite. Do NOT answer the question.

        History:
        {history_text}

        Query: {query}

        Standalone Query:
        """

        rewritten = await run_chat_completion(prompt)
        cleaned = rewritten.strip().replace('"', "")

        logger.info(f"[RAG] Query rewritten to: {cleaned}")

        return cleaned

    # -------------------------------------------------------------
    # VECTOR SEARCH
    # -------------------------------------------------------------
    async def _search_vectordb(self, query: str, user_id: str, top_k: int):
        """Embed the query using OpenAI + search Pinecone memory."""
        try:
            emb = await get_embedding(query)
            return await self.mm.search(user_id, emb, top_k)
        except Exception as e:
            logger.error(f"[RAG] Vector search failed: {e}")
            return []

    # -------------------------------------------------------------
    # STRATEGY DECISION LOGIC
    # -------------------------------------------------------------
    async def _decide_strategy(
        self, query: str, vector_results: List[Dict], max_results: int
    ) -> Tuple[str, List[Dict]]:
        # No memory results → must do Web Search
        if not vector_results:
            return await self._web_search_strategy(query, max_results)

        top_score = vector_results[0].get("score", 0)

        if top_score >= THRESHOLD_HIGH:
            return self._cached_strategy(vector_results, max_results)

        elif top_score >= THRESHOLD_MEDIUM:
            return await self._hybrid_strategy(query, vector_results, max_results)

        else:
            # Low relevance → hybrid fallback
            return await self._hybrid_strategy(query, vector_results, max_results)

    # -------------------------------------------------------------
    # STRATEGY IMPLEMENTATION
    # -------------------------------------------------------------
    def _cached_strategy(self, vector_results, max_results):
        """Only memory results."""
        return ("cached", self._format_sources(vector_results[:max_results], "cached"))

    async def _hybrid_strategy(self, query, vector_results, max_results):
        """Mix of memory + web search."""
        sources = []
        sources.extend(self._format_sources(vector_results[:2], "cached"))

        needed = max_results - len(sources)
        if needed > 0:
            web_results = search_and_extract(query, needed)
            sources.extend(self._format_sources(web_results, "web"))

        return ("hybrid", sources)

    async def _web_search_strategy(self, query, max_results):
        """Fallback: Realtime API + Web search."""
        sources = []

        realtime = fetch_realtime(query)
        if realtime:
            sources.extend(self._format_sources(realtime[:max_results], "realtime"))

        if len(sources) < max_results:
            web = search_and_extract(query, max_results - len(sources))
            sources.extend(self._format_sources(web, "web"))

        return ("web", sources)

    # -------------------------------------------------------------
    # FORMAT RESULTS
    # -------------------------------------------------------------
    def _format_sources(self, raw_list: List[Dict], source_type: str) -> List[Dict]:
        formatted = []

        for r in raw_list:
            formatted.append(
                {
                    "title": r.get("title", "Untitled"),
                    "url": r.get("url", ""),
                    "summary": r.get("text") or r.get("snippet") or "",
                    "score": r.get("score", 0),
                    "source": source_type,
                }
            )

        return formatted
