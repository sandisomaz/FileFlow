"""
Tests for librarian.py — Smart Naming Engine
Tests for executor.py — Semantic Dedup additions
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from app.muscle.librarian import Librarian, RenameProposal
from app.muscle.executor import AtomicExecutor
from app.brain.bridge import Bridge


# =============================================================================
# Librarian Tests
# =============================================================================

def make_librarian(bridge_healthy=False, ai_response=None):
    bridge = MagicMock(spec=Bridge)
    bridge.is_healthy.return_value = bridge_healthy
    bridge.generate.return_value = ai_response
    return Librarian(bridge=bridge)


class TestLibrarianRuleBasedNaming:
    def test_rule_name_from_entity_and_subtype(self, tmp_path):
        librarian = make_librarian(bridge_healthy=False)
        f = tmp_path / "random_scan_001.pdf"
        f.write_bytes(b"fake")
        meta = {"entity": "JUDGES_SECRETARY", "sub_type": "Z83"}
        proposal = librarian.propose_name(f, meta, tmp_path / "dest")
        assert "JUDGES_SECRETARY" in proposal.proposed_name
        assert "Z83" in proposal.proposed_name
        assert proposal.method == "rule"

    def test_version_bump_when_no_metadata(self, tmp_path):
        librarian = make_librarian(bridge_healthy=False)
        f = tmp_path / "document.pdf"
        f.write_bytes(b"fake")
        dest = tmp_path / "dest"
        dest.mkdir()
        meta = {}  # No entity or sub_type
        proposal = librarian.propose_name(f, meta, dest)
        assert proposal.method == "version_bump"
        assert "_v1" in proposal.proposed_name

    def test_version_bump_increments_when_file_exists(self, tmp_path):
        librarian = make_librarian(bridge_healthy=False)
        f = tmp_path / "document.pdf"
        f.write_bytes(b"fake")
        dest = tmp_path / "dest"
        dest.mkdir()
        # Pre-create v1
        (dest / "document_v1.pdf").write_bytes(b"existing")
        meta = {}
        proposal = librarian.propose_name(f, meta, dest)
        assert "_v2" in proposal.proposed_name

    def test_extension_preserved(self, tmp_path):
        librarian = make_librarian(bridge_healthy=False)
        f = tmp_path / "brief.docx"
        f.write_bytes(b"fake")
        meta = {"entity": "WERKSMANS", "sub_type": "Brief"}
        proposal = librarian.propose_name(f, meta, tmp_path / "dest")
        assert proposal.proposed_name.endswith(".docx")


class TestLibrarianAINaming:
    def test_ai_name_used_when_bridge_healthy(self, tmp_path):
        librarian = make_librarian(
            bridge_healthy=True,
            ai_response="WERKSMANS_CoverLetter_2024",
        )
        f = tmp_path / "scan_003.pdf"
        f.write_bytes(b"fake")
        meta = {"entity": "WERKSMANS", "sub_type": "CoverLetter"}
        proposal = librarian.propose_name(f, meta, tmp_path / "dest")
        assert proposal.method == "ai"
        assert "WERKSMANS" in proposal.proposed_name

    def test_falls_back_to_rule_when_ai_returns_none(self, tmp_path):
        librarian = make_librarian(bridge_healthy=True, ai_response=None)
        f = tmp_path / "scan_003.pdf"
        f.write_bytes(b"fake")
        meta = {"entity": "WERKSMANS", "sub_type": "CoverLetter"}
        proposal = librarian.propose_name(f, meta, tmp_path / "dest")
        assert proposal.method == "rule"

    def test_ai_name_with_spaces_rejected(self, tmp_path):
        """AI names with spaces should be rejected and fall back to rule."""
        librarian = make_librarian(
            bridge_healthy=True,
            ai_response="Werksmans Cover Letter 2024",  # spaces — invalid
        )
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"fake")
        meta = {"entity": "WERKSMANS", "sub_type": "CoverLetter"}
        proposal = librarian.propose_name(f, meta, tmp_path / "dest")
        assert proposal.method == "rule"  # Should fall back


class TestLibrarianSanitise:
    def test_spaces_become_underscores(self):
        assert Librarian._sanitise("Hello World") == "Hello_World"

    def test_special_chars_removed(self):
        assert Librarian._sanitise("File/Name:Test") == "FileNameTest"

    def test_multiple_underscores_collapsed(self):
        assert Librarian._sanitise("Hello___World") == "Hello_World"

    def test_truncated_to_50_chars(self):
        long = "A" * 100
        assert len(Librarian._sanitise(long)) <= 50


# =============================================================================
# Executor Semantic Dedup Tests
# =============================================================================

class TestExecutorSemanticDedup:
    def test_exact_text_match_is_duplicate(self):
        executor = AtomicExecutor(dry_run=True)
        text = "This is a test document with identical content."
        assert executor.is_semantic_duplicate(text, text) is True

    def test_different_text_is_not_duplicate(self):
        executor = AtomicExecutor(dry_run=True)
        assert executor.is_semantic_duplicate(
            "This is a lease agreement for 14 Acacia Street.",
            "This is a Z83 application for Judge's Secretary.",
        ) is False

    def test_md5_match_is_duplicate(self):
        executor = AtomicExecutor(dry_run=True)
        text = "Same content, same hash."
        assert executor.is_semantic_duplicate(text, text) is True

    def test_empty_texts_not_duplicate(self):
        executor = AtomicExecutor(dry_run=True)
        assert executor.is_semantic_duplicate("", "") is False

    def test_semantic_dedup_with_bridge(self):
        bridge = MagicMock(spec=Bridge)
        bridge.is_healthy.return_value = True
        # Return very similar embeddings (cosine sim ≈ 1.0)
        bridge.embed.return_value = [1.0, 0.0, 0.0]

        executor = AtomicExecutor(dry_run=True, bridge=bridge)
        result = executor.is_semantic_duplicate(
            "Document A content",
            "Document B content",
            threshold=0.95,
        )
        assert result is True  # Both embeddings are [1,0,0] → sim = 1.0

    def test_find_semantic_duplicates_returns_pairs(self):
        executor = AtomicExecutor(dry_run=True)
        # Two identical texts
        file_texts = {
            "file_a.pdf": "Identical content here.",
            "file_b.pdf": "Identical content here.",
            "file_c.pdf": "Completely different document about leases.",
        }
        dupes = executor.find_semantic_duplicates(file_texts)
        assert len(dupes) == 1
        paths = {dupes[0][0], dupes[0][1]}
        assert "file_a.pdf" in paths
        assert "file_b.pdf" in paths


class TestExecutorCosine:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert AtomicExecutor._cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert AtomicExecutor._cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert AtomicExecutor._cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert AtomicExecutor._cosine_similarity(a, b) == 0.0

    def test_different_length_vectors_truncated(self):
        a = [1.0, 0.0, 0.0, 0.0]
        b = [1.0, 0.0]
        # Should not raise — truncates to shorter
        result = AtomicExecutor._cosine_similarity(a, b)
        assert result == pytest.approx(1.0)
