"""
Tests for judge.py — The Decision Engine
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fileflow.intelligence.judge import Judge, Ruling, VALID_CATEGORIES
from fileflow.intelligence.bridge import Bridge
from fileflow.intelligence.extractor import UnifiedExtractor


def make_judge(bridge_healthy=False, slm_response=None):
    """Helper: creates a Judge with a mocked bridge and real extractor."""
    bridge = MagicMock(spec=Bridge)
    bridge.is_healthy.return_value = bridge_healthy
    bridge.generate.return_value = slm_response
    extractor = UnifiedExtractor()
    return Judge(bridge=bridge, extractor=extractor)


class TestJudgeFastPath:
    """Tests that the V8 rule engine handles known patterns without calling the SLM."""

    def test_judges_secretary_fast_path(self, tmp_path):
        f = tmp_path / "Application_for_Judges_Secretary.pdf"
        f.write_bytes(b"fake")
        judge = make_judge(bridge_healthy=False)
        ruling = judge.rule(f, extracted_text="", folder_hint="job_applications")
        assert ruling.path in ("fast", "fallback")
        assert ruling.category == "Professional"

    def test_quarantine_fast_path(self, tmp_path):
        f = tmp_path / "corrupted.pdf"
        f.write_bytes(b"fake")
        judge = make_judge(bridge_healthy=False)
        # Simulate extractor returning quarantine entity
        judge.extractor.extract_metadata = MagicMock(return_value={"entity": "_Quarantine"})
        ruling = judge.rule(f, extracted_text="", folder_hint="downloads")
        assert ruling.category == "Waste"

    def test_no_slm_call_on_high_confidence(self, tmp_path):
        f = tmp_path / "Z83_form.pdf"
        f.write_bytes(b"fake")
        bridge = MagicMock(spec=Bridge)
        bridge.is_healthy.return_value = True
        extractor = UnifiedExtractor()
        judge = Judge(bridge=bridge, extractor=extractor)

        # Force high-confidence V8 result
        judge.extractor.extract_metadata = MagicMock(return_value={"entity": "JUDGES_SECRETARY"})
        ruling = judge.rule(f, extracted_text="Z83 application", folder_hint="jobs")

        # SLM should NOT have been called
        bridge.generate.assert_not_called()
        assert ruling.path == "fast"


class TestJudgeSlowPath:
    """Tests that ambiguous files get escalated to the SLM."""

    def test_slm_called_for_unknown_file(self, tmp_path):
        f = tmp_path / "document_scan_003.pdf"
        f.write_bytes(b"fake")

        slm_json = '{"category": "Life_Admin", "confidence": 0.88, "reasoning": "Looks like a bank statement."}'
        judge = make_judge(bridge_healthy=True, slm_response=slm_json)

        # Force low-confidence V8 result
        judge.extractor.extract_metadata = MagicMock(return_value={})
        ruling = judge.rule(f, extracted_text="Account balance R5000", folder_hint="downloads")

        assert ruling.category == "Life_Admin"
        assert ruling.confidence == pytest.approx(0.88)
        assert ruling.path == "slow"

    def test_slm_invalid_json_falls_back(self, tmp_path):
        f = tmp_path / "mystery.pdf"
        f.write_bytes(b"fake")

        judge = make_judge(bridge_healthy=True, slm_response="not valid json at all")
        judge.extractor.extract_metadata = MagicMock(return_value={})
        ruling = judge.rule(f, extracted_text="", folder_hint="downloads")

        # Should fall back gracefully
        assert ruling.path == "fallback"
        assert ruling.category in VALID_CATEGORIES

    def test_slm_invalid_category_normalised(self, tmp_path):
        f = tmp_path / "weird.pdf"
        f.write_bytes(b"fake")

        slm_json = '{"category": "TOTALLY_MADE_UP", "confidence": 0.9, "reasoning": "test"}'
        judge = make_judge(bridge_healthy=True, slm_response=slm_json)
        judge.extractor.extract_metadata = MagicMock(return_value={})
        ruling = judge.rule(f, extracted_text="", folder_hint="")

        assert ruling.category == "Unknown"


class TestJudgeFallback:
    """Tests graceful fallback when Ollama is offline."""

    def test_fallback_when_bridge_offline(self, tmp_path):
        f = tmp_path / "unknown_file.pdf"
        f.write_bytes(b"fake")
        judge = make_judge(bridge_healthy=False)
        judge.extractor.extract_metadata = MagicMock(return_value={})
        ruling = judge.rule(f, extracted_text="", folder_hint="downloads")
        assert ruling.path == "fallback"
        assert ruling.category in VALID_CATEGORIES

    def test_ruling_always_returns_valid_category(self, tmp_path):
        """The Judge must always return a valid category, no matter what."""
        f = tmp_path / "test.pdf"
        f.write_bytes(b"fake")
        judge = make_judge(bridge_healthy=False)
        ruling = judge.rule(f, extracted_text="", folder_hint="")
        assert ruling.category in VALID_CATEGORIES
        assert 0.0 <= ruling.confidence <= 1.0
        assert isinstance(ruling.reasoning, str)


class TestJudgeEntityToCategory:
    def test_known_mappings(self):
        judge = make_judge()
        assert judge._entity_to_category("JUDGES_SECRETARY") == "Professional"
        assert judge._entity_to_category("CANDIDATE_ATTORNEY") == "Professional"
        assert judge._entity_to_category("LEGAL_BOARD_EXAMS") == "Education"
        assert judge._entity_to_category("_Quarantine") == "Waste"
        assert judge._entity_to_category("Ghost_Files") == "Waste"
        assert judge._entity_to_category("") == "Unknown"
