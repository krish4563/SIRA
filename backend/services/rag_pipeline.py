# services/rag_pipeline.py

import logging
from typing import Dict, List, Optional, Tuple

from services.embeddings import get_embedding
from services.llm_client import run_chat_completion  # ✅ Use LLM for query rewriting
from services.memory_manager import MemoryManager
from services.multi_retriever import search_and_extract
from services.realtime_retriever import fetch_realtime

logger = logging.getLogger(__name__)

THRESHOLD_HIGH = 0.82
THRESHOLD_MEDIUM = 0.70
THRESHOLD_MINIMUM = 0.40  # 🔴 Drop irrelevant results (Fixes Bitcoin showing in Galaxy)


class RAGPipeline:
    def _init_(self):
        self.mm = MemoryManager()

    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_history: Optional[List[Dict]] = None,
        max_results: int = 5,
    ) -> Dict:
        logger.info(f"[RAG] Retrieving for: {query}")

        # 1. Smart Query Rewriting (Fixes Context Pollution)
        enhanced_query = await self._rewrite_query(query, conversation_history)

        # 2. Vector Search (With Threshold Filter)
        vector_results = await self._search_vectordb(enhanced_query, user_id, top_k=8)

        # 🔴 FILTER: Remove low-score junk
        valid_vectors = [
            r for r in vector_results if r.get("score", 0) > THRESHOLD_MINIMUM
        ]

        # 3. Strategy Decision
        strategy, sources = await self._decide_strategy(
            query, valid_vectors, max_results
        )

        return {
            "sources": sources,
            "retrieval_strategy": strategy,
            "context_used": enhanced_query != query,
        }

    async def _rewrite_query(self, query: str, history: Optional[List[Dict]]) -> str:
        """
        Uses LLM to clarify the query based on history, instead of just appending text.
        """
        if not history or len(history) < 2:
            return query

        # Get last 2 turns
        short_history = history[-4:]
        history_text = "\n".join(
            [f"{m['role']}: {m['content']}" for m in short_history]
        )

        prompt = f"""
        Given the chat history, rewrite the user's latest query to be standalone and clear.
        If the new query is unrelated to the history, return it exactly as is.
        Do NOT answer the question. Just rewrite the query.

        Chat History:
        {history_text}

        Latest Query: {query}

        Standalone Query:
        """

        # Use fast LLM model
        rewritten = await run_chat_completion(prompt)
        cleaned = rewritten.strip().replace('"', "")

        logger.info(f"[RAG] Rewrote '{query}' -> '{cleaned}'")
        return cleaned

    async def _search_vectordb(
        self, query: str, user_id: str, top_k: int
    ) -> List[Dict]:
        try:
            emb = await get_embedding(query)
            return await self.mm.search(user_id, emb, top_k)
        except:
            return []

    async def _decide_strategy(
        self, query: str, vector_results: List[Dict], max_results: int
    ) -> Tuple[str, List[Dict]]:
        # If vectors are empty (or filtered out), force Web Search
        if not vector_results:
            return await self._web_search_strategy(query, max_results)

        top_score = vector_results[0].get("score", 0)

        if top_score >= THRESHOLD_HIGH:
            return self._cached_strategy(vector_results, max_results)
        elif top_score >= THRESHOLD_MEDIUM:
            return await self._hybrid_strategy(query, vector_results, max_results)
        else:
            # Low relevance? Prefer Web, but keep 1-2 cached if they aren't terrible
            return await self._hybrid_strategy(query, vector_results, max_results)

    def _cached_strategy(self, vector_results, max_results):
        return ("cached", self._format_sources(vector_results[:max_results], "cached"))

    async def _hybrid_strategy(self, query, vector_results, max_results):
        sources = []
        # Keep max 2 cached
        sources.extend(self._format_sources(vector_results[:2], "cached"))

        needed = max_results - len(sources)
        if needed > 0:
            web_results = search_and_extract(query, needed)
            sources.extend(self._format_sources(web_results, "web"))

        return ("hybrid", sources)

    async def _web_search_strategy(self, query, max_results):
        # Try realtime first, then standard web
        sources = []
        realtime = fetch_realtime(query)

        if realtime:
            sources.extend(self._format_sources(realtime[:max_results], "realtime"))

        if len(sources) < max_results:
            web = search_and_extract(query, max_results - len(sources))
            sources.extend(self._format_sources(web, "web"))

        return ("web", sources)

    def _format_sources(self, raw_list: List[Dict], source_type: str) -> List[Dict]:
        """Standardize source format."""
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
