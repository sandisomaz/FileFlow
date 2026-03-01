"""
discovery.py — Semantic Search
FileFlow Cognition V9

The Discovery module answers natural language questions about your file system.

"Find my ID document"
"Where are all my lease agreements?"
"Show me everything related to Werksmans"

It works by embedding the query and finding the closest matches in Memory.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from fileflow.intelligence.bridge import Bridge
from fileflow.intelligence.memory import Memory

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result returned by Discovery."""
    file_path: str
    file_name: str
    category: str
    entity: str
    summary: str
    score: float            # Distance score — lower = more similar
    rank: int               # 1-indexed rank in results


class Discovery:
    """
    The sovereign semantic search engine for FileFlow.

    Converts a natural language query into a vector, then finds the
    most semantically similar documents in Memory.

    Usage:
        discovery = Discovery(bridge=bridge, memory=memory)
        results = discovery.search("find my lease agreement")
        for r in results:
            print(r.rank, r.file_name, r.summary)
    """

    def __init__(self, bridge: Bridge, memory: Memory):
        self.bridge = bridge
        self.memory = memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """
        Searches Memory for documents semantically similar to the query.

        Args:
            query:  Natural language search query
            top_k:  Maximum number of results to return

        Returns:
            List of SearchResult, ordered by relevance (best first)
        """
        if not query or not query.strip():
            return []

        if not self.bridge.is_healthy():
            logger.warning("[Discovery] Bridge offline — cannot perform semantic search")
            return []

        if not self.memory._available:
            logger.warning("[Discovery] Memory unavailable — index may not be built yet")
            return []

        raw_results = self.memory.recall(query=query, top_k=top_k)

        results = []
        for i, r in enumerate(raw_results):
            results.append(SearchResult(
                file_path=r["file_path"],
                file_name=r["file_name"],
                category=r["category"],
                entity=r.get("entity", ""),
                summary=r.get("summary", ""),
                score=r.get("score", 0.0),
                rank=i + 1,
            ))

        logger.debug(f"[Discovery] '{query}' → {len(results)} results")
        return results

    def search_by_category(self, category: str, top_k: int = 20) -> List[SearchResult]:
        """
        Finds all documents in a specific archive category.
        Uses the category name as the query for broad semantic matching.
        """
        category_queries = {
            "Professional": "job application CV cover letter legal brief court",
            "Education": "study guide exam paper course certificate transcript",
            "Development": "code script project technical documentation",
            "Life_Admin": "bank statement invoice receipt lease agreement ID document",
            "Waste": "duplicate empty corrupted temporary junk",
        }
        query = category_queries.get(category, category)
        return self.search(query, top_k=top_k)

    def stats(self) -> dict:
        """Returns stats about the current memory index."""
        return self.memory.get_stats()

    def format_results(self, results: List[SearchResult], query: str = "") -> str:
        """
        Formats search results as a human-readable string for the terminal.

        Example output:
            🔍 Results for "find my lease agreement" (3 found)
            ─────────────────────────────────────────────────
            1. lease_agreement_2024.pdf          [Life_Admin]
               Lease agreement for 14 Acacia Street, monthly rental R8,500.
               📁 C:/Users/sandi/Desktop/Downloads/lease_agreement_2024.pdf

            2. rental_contract_jan2025.pdf       [Life_Admin]
               ...
        """
        if not results:
            header = f'🔍 No results found for "{query}"' if query else "🔍 No results found"
            return f"{header}\n\nTip: Run --embed first to build the search index."

        header = f'🔍 Results for "{query}" ({len(results)} found)' if query else f"🔍 {len(results)} results"
        lines = [header, "─" * 60]

        for r in results:
            # Category badge
            badge = f"[{r.category}]"
            lines.append(f"\n{r.rank}. {r.file_name:<40} {badge}")

            if r.summary and r.summary != "Unreadable document — no text extracted.":
                lines.append(f"   {r.summary}")

            lines.append(f"   📁 {r.file_path}")

        return "\n".join(lines)
