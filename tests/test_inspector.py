"""
Tests for inspector.py — The Document Reader
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fileflow.intelligence.inspector import Inspector, InspectionResult
from fileflow.intelligence.bridge import Bridge
from fileflow.intelligence.memory import Memory


def make_inspector(bridge_healthy=False, slm_response=None, memory_available=False):
    """Helper: creates an Inspector with mocked bridge and memory."""
    bridge = MagicMock(spec=Bridge)
    bridge.is_healthy.return_value = bridge_healthy
    bridge.generate.return_value = slm_response

    memory = MagicMock(spec=Memory)
    memory._available = memory_available
    memory.remember.return_value = memory_available

    return Inspector(bridge=bridge, memory=memory)


class TestInspectorSummarise:
    def test_returns_filename_summary_when_bridge_offline(self, tmp_path):
        f = tmp_path / "lease_agreement_2024.pdf"
        f.write_bytes(b"fake")
        inspector = make_inspector(bridge_healthy=False)
        result = inspector.inspect(f, text="", category="Life_Admin", sub_type="Lease", entity="")
        # Should fall back to filename-based summary
        assert "Lease Agreement 2024" in result.summary or "pdf" in result.summary.lower()
        assert result.embedded is False

    def test_returns_filename_summary_when_no_text(self, tmp_path):
        f = tmp_path / "cv_sandiso.pdf"
        f.write_bytes(b"fake")
        inspector = make_inspector(bridge_healthy=True, slm_response=None)
        result = inspector.inspect(f, text="", category="Professional")
        assert "Cv Sandiso" in result.summary or "pdf" in result.summary.lower()

    def test_uses_slm_summary_when_available(self, tmp_path):
        f = tmp_path / "z83_application.pdf"
        f.write_bytes(b"fake")
        inspector = make_inspector(
            bridge_healthy=True,
            slm_response="Z83 application by Sandiso Mazibuko for Judge's Secretary position.",
            memory_available=False,
        )
        result = inspector.inspect(
            f,
            text="APPLICATION FOR EMPLOYMENT Z83 FORM. Position: Judge's Secretary.",
            category="Professional",
        )
        assert "Z83" in result.summary or "Sandiso" in result.summary

    def test_slm_summary_is_cleaned(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake")
        # SLM returns with quotes and newlines
        inspector = make_inspector(
            bridge_healthy=True,
            slm_response='"Bank statement from FNB, January 2025."\n\nExtra text.',
        )
        result = inspector.inspect(f, text="FNB bank statement January 2025", category="Life_Admin")
        # Should be cleaned — no quotes, no extra lines
        assert result.summary.startswith("Bank statement")
        assert "\n" not in result.summary

    def test_very_long_summary_is_truncated(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake")
        inspector = make_inspector(
            bridge_healthy=True,
            slm_response="A" * 400,
        )
        result = inspector.inspect(f, text="some content", category="Unknown")
        assert len(result.summary) <= 300


class TestInspectorEmbedding:
    def test_embedded_true_when_memory_available(self, tmp_path):
        f = tmp_path / "lease.pdf"
        f.write_bytes(b"fake")
        inspector = make_inspector(
            bridge_healthy=True,
            slm_response="Lease agreement for 14 Acacia Street.",
            memory_available=True,
        )
        result = inspector.inspect(f, text="lease agreement rental R8500", category="Life_Admin")
        assert result.embedded is True
        inspector.memory.remember.assert_called_once()

    def test_not_embedded_when_bridge_offline(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake")
        inspector = make_inspector(bridge_healthy=False, memory_available=True)
        result = inspector.inspect(f, text="some text", category="Unknown")
        assert result.embedded is False


class TestInspectorChunking:
    def test_empty_text_returns_one_chunk(self):
        inspector = make_inspector()
        chunks = inspector._chunk("")
        assert chunks == []

    def test_short_text_returns_one_chunk(self):
        inspector = make_inspector()
        chunks = inspector._chunk("Hello world")
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_long_text_is_chunked(self):
        inspector = make_inspector()
        long_text = "word " * 1000  # 5000 chars
        chunks = inspector._chunk(long_text, size=1500, overlap=150)
        assert len(chunks) > 1
        # Each chunk should be at most 1500 chars
        for chunk in chunks:
            assert len(chunk) <= 1500


class TestInspectorBatch:
    def test_batch_handles_errors_gracefully(self, tmp_path):
        inspector = make_inspector(bridge_healthy=False)
        files = [
            {"file_path": str(tmp_path / "a.pdf"), "text": "content a", "category": "Professional"},
            {"file_path": str(tmp_path / "b.pdf"), "text": "content b", "category": "Education"},
        ]
        results = inspector.inspect_batch(files)
        assert len(results) == 2
        for r in results:
            assert isinstance(r, InspectionResult)

    def test_progress_callback_is_called(self, tmp_path):
        inspector = make_inspector(bridge_healthy=False)
        calls = []
        files = [{"file_path": str(tmp_path / "a.pdf"), "text": "", "category": "Unknown"}]
        inspector.inspect_batch(files, progress_callback=lambda c, t, n: calls.append((c, t, n)))
        assert len(calls) == 1
        assert calls[0] == (1, 1, "a.pdf")
