"""
Tests for listener.py — The Folder Watcher

Note: We do NOT test the watchdog observer itself (that's watchdog's job).
We test the Listener's own logic:
  - Event queuing and deduplication
  - Extension filtering
  - Debounce logic
  - File processing pipeline
  - Stats tracking
  - _wait_for_file helper
  - _extract_text helper
"""

import time
import threading
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.brain.listener import (
    Listener,
    ListenerEvent,
    ListenerStats,
    WATCHED_EXTENSIONS,
    DEBOUNCE_SECONDS,
)
from app.brain.bridge import Bridge
from app.brain.inspector import Inspector


def make_listener(with_inspector=False, with_staging=False):
    """Helper: creates a Listener with optional mocked dependencies."""
    inspector = None
    if with_inspector:
        inspector = MagicMock(spec=Inspector)
        inspector.inspect.return_value = MagicMock(
            summary="Test summary.",
            embedded=True,
        )

    staging = MagicMock() if with_staging else None

    return Listener(
        inspector=inspector,
        staging_manager=staging,
        debounce=0.1,  # Short debounce for tests
    )


# =============================================================================
# Extension Filtering
# =============================================================================

class TestListenerExtensionFilter:
    def test_pdf_is_watched(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "doc.pdf"
        listener._enqueue(f, "created")
        assert len(listener._pending) == 1

    def test_docx_is_watched(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "brief.docx"
        listener._enqueue(f, "created")
        assert len(listener._pending) == 1

    def test_exe_is_ignored(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "setup.exe"
        listener._enqueue(f, "created")
        assert len(listener._pending) == 0

    def test_jpg_is_watched(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "photo.jpg"
        listener._enqueue(f, "created")
        assert len(listener._pending) == 1

    def test_mp3_is_ignored(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "music.mp3"
        listener._enqueue(f, "created")
        assert len(listener._pending) == 0

    def test_all_watched_extensions_accepted(self, tmp_path):
        listener = make_listener()
        for ext in WATCHED_EXTENSIONS:
            f = tmp_path / f"file{ext}"
            listener._enqueue(f, "created")
        assert len(listener._pending) == len(WATCHED_EXTENSIONS)


# =============================================================================
# Event Deduplication
# =============================================================================

class TestListenerDeduplication:
    def test_same_file_not_queued_twice(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "doc.pdf"
        listener._enqueue(f, "created")
        listener._enqueue(f, "modified")  # Same file — should be ignored
        assert len(listener._pending) == 1

    def test_different_files_both_queued(self, tmp_path):
        listener = make_listener()
        listener._enqueue(tmp_path / "a.pdf", "created")
        listener._enqueue(tmp_path / "b.pdf", "created")
        assert len(listener._pending) == 2

    def test_seen_cache_cleared_allows_requeue(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "doc.pdf"
        listener._enqueue(f, "created")
        # Manually clear seen cache (simulates what _process_loop does)
        listener._seen.clear()
        listener._enqueue(f, "modified")
        assert len(listener._pending) == 2


# =============================================================================
# Stats
# =============================================================================

class TestListenerStats:
    def test_stats_initial_state(self):
        listener = make_listener()
        assert listener.stats.events_detected == 0
        assert listener.stats.files_staged == 0
        assert listener.stats.files_embedded == 0
        assert listener.stats.errors == 0

    def test_enqueue_increments_events_detected(self, tmp_path):
        listener = make_listener()
        listener._enqueue(tmp_path / "a.pdf", "created")
        listener._enqueue(tmp_path / "b.pdf", "created")
        assert listener.stats.events_detected == 2

    def test_stats_summary_contains_key_fields(self):
        stats = ListenerStats()
        summary = stats.summary()
        assert "Staged" in summary
        assert "Embedded" in summary
        assert "Uptime" in summary

    def test_uptime_increases(self):
        stats = ListenerStats()
        t1 = stats.uptime_seconds()
        time.sleep(0.05)
        t2 = stats.uptime_seconds()
        assert t2 > t1


# =============================================================================
# Event Processing
# =============================================================================

class TestListenerProcessEvent:
    def test_process_event_calls_inspector(self, tmp_path):
        listener = make_listener(with_inspector=True)
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake pdf")

        event = ListenerEvent(
            file_path=f,
            event_type="created",
            detected_at=time.time(),
        )

        with patch.object(listener, "_wait_for_file", return_value=True), \
             patch.object(listener, "_extract_text", return_value="some text"):
            listener._process_event(event, on_event=None)

        listener.inspector.inspect.assert_called_once()

    def test_process_event_calls_staging_manager(self, tmp_path):
        listener = make_listener(with_inspector=False, with_staging=True)
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake pdf")

        event = ListenerEvent(
            file_path=f,
            event_type="created",
            detected_at=time.time(),
        )

        with patch.object(listener, "_wait_for_file", return_value=True), \
             patch.object(listener, "_extract_text", return_value=""):
            listener._process_event(event, on_event=None)

        listener.staging_manager.stage_file.assert_called_once_with(f)
        assert listener.stats.files_staged == 1

    def test_process_event_skips_when_file_not_ready(self, tmp_path):
        listener = make_listener(with_inspector=True)
        f = tmp_path / "doc.pdf"

        event = ListenerEvent(
            file_path=f,
            event_type="created",
            detected_at=time.time(),
        )

        with patch.object(listener, "_wait_for_file", return_value=False):
            listener._process_event(event, on_event=None)

        listener.inspector.inspect.assert_not_called()
        assert listener.stats.files_skipped == 1

    def test_on_event_callback_is_called(self, tmp_path):
        listener = make_listener()
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake")

        event = ListenerEvent(file_path=f, event_type="created", detected_at=time.time())
        callback_calls = []

        with patch.object(listener, "_wait_for_file", return_value=True), \
             patch.object(listener, "_extract_text", return_value=""):
            listener._process_event(event, on_event=lambda e: callback_calls.append(e))

        assert len(callback_calls) == 1
        assert callback_calls[0] is event

    def test_errors_are_counted(self, tmp_path):
        listener = make_listener(with_inspector=True)
        listener.inspector.inspect.side_effect = RuntimeError("Boom")
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake")

        event = ListenerEvent(file_path=f, event_type="created", detected_at=time.time())

        with patch.object(listener, "_wait_for_file", return_value=True), \
             patch.object(listener, "_extract_text", return_value="text"):
            listener._process_event(event, on_event=None)

        assert listener.stats.errors == 1


# =============================================================================
# Helpers
# =============================================================================

class TestListenerHelpers:
    def test_wait_for_file_returns_true_for_stable_file(self, tmp_path):
        f = tmp_path / "stable.pdf"
        f.write_bytes(b"content")
        result = Listener._wait_for_file(f, timeout=2.0, interval=0.1)
        assert result is True

    def test_wait_for_file_returns_false_for_missing_file(self, tmp_path):
        f = tmp_path / "missing.pdf"
        result = Listener._wait_for_file(f, timeout=0.3, interval=0.1)
        assert result is False

    def test_extract_text_from_txt(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("Hello from a text file.", encoding="utf-8")
        text = Listener._extract_text(f)
        assert "Hello from a text file." in text

    def test_extract_text_from_unknown_ext_returns_empty(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        text = Listener._extract_text(f)
        assert text == ""

    def test_stop_sets_stop_event(self):
        listener = make_listener()
        assert not listener._stop_event.is_set()
        listener.stop()
        assert listener._stop_event.is_set()
