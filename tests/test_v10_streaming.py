"""
test_v10_streaming.py — Sniffer + KnowledgeGraph integration/performance check.

CHANGED: this file previously had no `def test_*` functions — it was a
standalone script only, meaning `pytest` silently collected zero tests
from it despite the filename matching pytest's discovery pattern. It also
wrote to data/test_knowledge_graph.sqlite — a real path inside the
project's actual data/ directory, alongside the live audit ledger and
vector store, rather than a throwaway location.

Both fixed: the core logic is now a real pytest test using tmp_path (a
built-in pytest fixture giving a fresh, auto-cleaned temp directory per
test run), and the standalone `python test_v10_streaming.py` path uses
Python's tempfile module instead of a hardcoded data/ path.
"""

import tempfile
import time
from pathlib import Path

from app.brain.sniffer import Sniffer
from app.memory.knowledge_graph import KnowledgeGraph


TEST_CASES = [
    (Path("Candidate_CV.pdf"), "This is a Curriculum Vitae with ID 8701015009087"),
    (Path("Invoice_March.pdf"), "TAX INVOICE Total due: R1500"),
    (Path("Z83_Form_Signed.pdf"), "Z83 Application for Employment REF: BH-2024-X"),
    (Path("Unknown_Doc.txt"), "Just some random notes about grocery shopping."),
]


def run_performance_check(graph_db_path: Path) -> dict:
    """Core logic, parameterized on where the graph DB lives so callers
    (pytest with tmp_path, or a standalone run with tempfile) each supply
    their own throwaway location instead of a hardcoded project path."""
    sniffer = Sniffer()
    graph = KnowledgeGraph(graph_db_path)

    start_time = time.perf_counter()
    results = [(path.name, sniffer.sniff(path, text)) for path, text in TEST_CASES]
    duration_ms = (time.perf_counter() - start_time) * 1000

    for filename, result in results:
        if result.confidence > 0.8:
            fake_hash = f"hash_{filename}"
            graph.ingest_sniff_result(fake_hash, filename, {
                "confidence": result.confidence,
                "category": result.category,
                "sub_type": result.sub_type,
                "facts": result.facts,
            })

    linked = graph.get_related_files("SA_ID", "8701015009087")

    return {
        "results": results,
        "duration_ms": duration_ms,
        "avg_ms_per_file": duration_ms / len(TEST_CASES),
        "linked_by_sa_id": linked,
    }


class TestSnifferKnowledgeGraphIntegration:
    def test_sniffer_processes_all_test_cases(self, tmp_path):
        outcome = run_performance_check(tmp_path / "test_knowledge_graph.sqlite")
        assert len(outcome["results"]) == len(TEST_CASES)

    def test_high_confidence_facts_are_linkable_via_graph(self, tmp_path):
        outcome = run_performance_check(tmp_path / "test_knowledge_graph.sqlite")
        # The CV test case contains an SA ID number the Sniffer should
        # extract as a fact; the Knowledge Graph should then be able to
        # find that file again by querying for the same ID.
        assert len(outcome["linked_by_sa_id"]) >= 1

    def test_sniffer_throughput_is_reasonable(self, tmp_path):
        # Not a strict perf gate (CI hardware varies) — just guards
        # against something becoming pathologically slow (e.g. an
        # accidental network call or unbounded loop creeping in).
        outcome = run_performance_check(tmp_path / "test_knowledge_graph.sqlite")
        assert outcome["avg_ms_per_file"] < 1000


def _run_standalone():
    """Manual run: `python test_v10_streaming.py` — uses a real temp
    directory instead of a path inside the project's data/ folder."""
    print("--- FileFlow V10 Triage Performance Test ---")
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_performance_check(Path(tmp) / "test_knowledge_graph.sqlite")
        print(f"\n[Sniffer] Processed {len(TEST_CASES)} files in "
              f"{outcome['duration_ms']:.2f}ms "
              f"(Avg: {outcome['avg_ms_per_file']:.2f}ms/file)")
        for filename, result in outcome["results"]:
            print(f"  -> {filename}: [{result.confidence}] {result.category}/{result.sub_type}")
        print(f"\n[Knowledge Graph] Found {len(outcome['linked_by_sa_id'])} "
              f"files linked to SA ID 8701015009087")
    print("\nTest completed successfully.")


if __name__ == "__main__":
    _run_standalone()
