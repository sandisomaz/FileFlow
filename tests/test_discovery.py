"""
Tests for discovery.py — Semantic Search
"""

import pytest
from unittest.mock import MagicMock

from fileflow.intelligence.discovery import Discovery, SearchResult
from fileflow.intelligence.bridge import Bridge
from fileflow.intelligence.memory import Memory


def make_discovery(bridge_healthy=True, memory_available=True, recall_results=None):
    """Helper: creates a Discovery with mocked bridge and memory."""
    bridge = MagicMock(spec=Bridge)
    bridge.is_healthy.return_value = bridge_healthy

    memory = MagicMock(spec=Memory)
    memory._available = memory_available
    memory.recall.return_value = recall_results or []
    memory.get_stats.return_value = {"available": memory_available, "total_records": 5}

    return Discovery(bridge=bridge, memory=memory)


SAMPLE_RECALL = [
    {
        "file_path": "C:/Users/sandi/Desktop/lease_2024.pdf",
        "file_name": "lease_2024.pdf",
        "category": "Life_Admin",
        "entity": "Landlord_Tenant",
        "summary": "Lease agreement for 14 Acacia Street, monthly rental R8,500.",
        "score": 0.12,
    },
    {
        "file_path": "C:/Users/sandi/Desktop/rental_jan2025.pdf",
        "file_name": "rental_jan2025.pdf",
        "category": "Life_Admin",
        "entity": "Landlord_Tenant",
        "summary": "Rental contract for January 2025.",
        "score": 0.25,
    },
]


class TestDiscoverySearch:
    def test_returns_empty_for_blank_query(self):
        discovery = make_discovery()
        assert discovery.search("") == []
        assert discovery.search("   ") == []

    def test_returns_empty_when_bridge_offline(self):
        discovery = make_discovery(bridge_healthy=False)
        results = discovery.search("find my lease")
        assert results == []

    def test_returns_empty_when_memory_unavailable(self):
        discovery = make_discovery(memory_available=False)
        results = discovery.search("find my lease")
        assert results == []

    def test_returns_ranked_results(self):
        discovery = make_discovery(recall_results=SAMPLE_RECALL)
        results = discovery.search("lease agreement")
        assert len(results) == 2
        assert results[0].rank == 1
        assert results[1].rank == 2
        assert results[0].file_name == "lease_2024.pdf"

    def test_result_fields_populated(self):
        discovery = make_discovery(recall_results=SAMPLE_RECALL)
        results = discovery.search("lease")
        r = results[0]
        assert r.file_path == "C:/Users/sandi/Desktop/lease_2024.pdf"
        assert r.category == "Life_Admin"
        assert "Acacia" in r.summary
        assert isinstance(r.score, float)

    def test_memory_recall_called_with_query(self):
        discovery = make_discovery(recall_results=[])
        discovery.search("find my CV", top_k=5)
        discovery.memory.recall.assert_called_once_with(query="find my CV", top_k=5)


class TestDiscoverySearchByCategory:
    def test_search_by_category_uses_expanded_query(self):
        discovery = make_discovery(recall_results=[])
        discovery.search_by_category("Life_Admin")
        # Should have called recall with an expanded query, not just "Life_Admin"
        call_args = discovery.memory.recall.call_args
        query_used = call_args[1]["query"] if call_args[1] else call_args[0][0]
        assert "bank" in query_used.lower() or "lease" in query_used.lower()

    def test_unknown_category_falls_back_to_category_name(self):
        discovery = make_discovery(recall_results=[])
        discovery.search_by_category("SomeUnknownCategory")
        call_args = discovery.memory.recall.call_args
        query_used = call_args[1]["query"] if call_args[1] else call_args[0][0]
        assert "SomeUnknownCategory" in query_used


class TestDiscoveryFormatResults:
    def test_formats_results_correctly(self):
        discovery = make_discovery(recall_results=SAMPLE_RECALL)
        results = discovery.search("lease")
        output = discovery.format_results(results, query="lease")
        assert "lease" in output.lower()
        assert "lease_2024.pdf" in output
        assert "[Life_Admin]" in output
        assert "Acacia" in output

    def test_no_results_shows_helpful_message(self):
        discovery = make_discovery(recall_results=[])
        results = discovery.search("something")
        output = discovery.format_results(results, query="something")
        assert "No results" in output
        assert "--embed" in output  # Tip to build the index

    def test_format_without_query(self):
        discovery = make_discovery(recall_results=SAMPLE_RECALL)
        results = discovery.search("test")
        output = discovery.format_results(results)
        assert "results" in output.lower()


class TestDiscoveryStats:
    def test_stats_returns_dict(self):
        discovery = make_discovery()
        stats = discovery.stats()
        assert "available" in stats
        assert "total_records" in stats
