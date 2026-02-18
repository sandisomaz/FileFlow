"""
listener.py — The Folder Watcher
FileFlow Cognition V9

Watches one or more source folders for new files and automatically:
1. Stages them (via StagingManager)
2. Classifies them (via Judge)
3. Embeds them into Memory (via Inspector)

The Listener is the "always-on" mode of FileFlow — it turns the system
into a continuous document intelligence pipeline.

Design:
- Uses watchdog for cross-platform filesystem events
- Debounces rapid bursts (e.g. copying a folder of 50 files)
- Graceful shutdown on Ctrl+C
- Logs every event to the session logger
- Falls back to V8 staging if AI is unavailable

Usage:
    python main.py "C:\\Users\\sandi\\Desktop\\Downloads" --watch
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Set

logger = logging.getLogger(__name__)

# File extensions the Listener cares about
WATCHED_EXTENSIONS: Set[str] = {
    ".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls",
    ".pptx", ".ppt", ".odt", ".rtf", ".csv",
}

# How long to wait after the last event before processing a burst (seconds)
DEBOUNCE_SECONDS = 2.0


@dataclass
class ListenerEvent:
    """A single file event detected by the watcher."""
    file_path: Path
    event_type: str         # "created" | "modified" | "moved"
    detected_at: float      # time.time()
    processed: bool = False
    result: Optional[dict] = None


@dataclass
class ListenerStats:
    """Running statistics for the Listener session."""
    watched_folders: List[str] = field(default_factory=list)
    events_detected: int = 0
    files_staged: int = 0
    files_embedded: int = 0
    files_skipped: int = 0
    errors: int = 0
    started_at: float = field(default_factory=time.time)

    def uptime_seconds(self) -> float:
        return time.time() - self.started_at

    def summary(self) -> str:
        uptime = int(self.uptime_seconds())
        mins, secs = divmod(uptime, 60)
        return (
            f"⏱  Uptime: {mins}m {secs}s | "
            f"📥 Staged: {self.files_staged} | "
            f"🧠 Embedded: {self.files_embedded} | "
            f"⏭  Skipped: {self.files_skipped} | "
            f"❌ Errors: {self.errors}"
        )


class Listener:
    """
    The sovereign folder watcher for FileFlow Cognition.

    Monitors source folders for new documents and automatically
    runs them through the full V9 pipeline.

    Usage:
        listener = Listener(
            judge=judge,
            inspector=inspector,
            staging_manager=staging_manager,
        )
        listener.watch([Path("C:/Downloads")], on_event=my_callback)
        # Blocks until Ctrl+C
    """

    def __init__(
        self,
        judge=None,
        inspector=None,
        staging_manager=None,
        debounce: float = DEBOUNCE_SECONDS,
    ):
        """
        Args:
            judge:           Optional Judge for AI classification
            inspector:       Optional Inspector for embedding
            staging_manager: StagingManager for V8 staging
            debounce:        Seconds to wait before processing a burst of events
        """
        self.judge = judge
        self.inspector = inspector
        self.staging_manager = staging_manager
        self.debounce = debounce
        self.stats = ListenerStats()

        # Internal event queue (thread-safe via lock)
        self._pending: List[ListenerEvent] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Dedup: track recently seen paths to avoid double-processing
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def watch(
        self,
        folders: List[Path],
        on_event: Optional[Callable[[ListenerEvent], None]] = None,
        recursive: bool = True,
    ) -> None:
        """
        Starts watching the given folders. Blocks until stopped.

        Args:
            folders:    List of folders to watch
            on_event:   Optional callback called after each file is processed
            recursive:  Whether to watch subfolders too
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            raise RuntimeError(
                "watchdog is required for --watch mode.\n"
                "Install it with: pip install watchdog"
            )

        self.stats.watched_folders = [str(f) for f in folders]

        # Build the watchdog handler
        handler = self._make_handler()

        observer = Observer()
        for folder in folders:
            if not folder.exists():
                logger.warning(f"[Listener] Folder does not exist, skipping: {folder}")
                continue
            observer.schedule(handler, str(folder), recursive=recursive)
            logger.info(f"[Listener] Watching: {folder}")

        observer.start()
        logger.info("[Listener] Started. Press Ctrl+C to stop.")

        # Start the processing thread
        processor = threading.Thread(
            target=self._process_loop,
            args=(on_event,),
            daemon=True,
        )
        processor.start()

        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("[Listener] Ctrl+C received. Shutting down...")
        finally:
            self._stop_event.set()
            observer.stop()
            observer.join()
            processor.join(timeout=5)
            logger.info(f"[Listener] Stopped. {self.stats.summary()}")

    def stop(self) -> None:
        """Signals the listener to stop gracefully."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _make_handler(self):
        """Creates a watchdog FileSystemEventHandler that feeds our queue."""
        listener_ref = self

        try:
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            raise RuntimeError("watchdog is not installed. Run: pip install watchdog")

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    listener_ref._enqueue(Path(event.src_path), "created")

            def on_modified(self, event):
                if not event.is_directory:
                    listener_ref._enqueue(Path(event.src_path), "modified")

            def on_moved(self, event):
                if not event.is_directory:
                    listener_ref._enqueue(Path(event.dest_path), "moved")

        return _Handler()

    def _enqueue(self, file_path: Path, event_type: str) -> None:
        """Adds a file event to the pending queue (thread-safe)."""
        # Filter by extension
        if file_path.suffix.lower() not in WATCHED_EXTENSIONS:
            return

        # Dedup: skip if we've seen this path very recently
        key = str(file_path)
        with self._lock:
            if key in self._seen:
                return
            self._seen.add(key)
            self._pending.append(ListenerEvent(
                file_path=file_path,
                event_type=event_type,
                detected_at=time.time(),
            ))
            self.stats.events_detected += 1

        logger.debug(f"[Listener] Queued: {file_path.name} ({event_type})")

    def _process_loop(self, on_event: Optional[Callable]) -> None:
        """
        Background thread: drains the pending queue with debouncing.
        Waits until no new events have arrived for `debounce` seconds
        before processing the batch.
        """
        while not self._stop_event.is_set():
            time.sleep(0.25)

            with self._lock:
                if not self._pending:
                    continue

                # Debounce: only process if the last event was > debounce seconds ago
                last_event_time = max(e.detected_at for e in self._pending)
                if time.time() - last_event_time < self.debounce:
                    continue

                # Grab the batch
                batch = [e for e in self._pending if not e.processed]
                for e in batch:
                    e.processed = True

            # Process outside the lock
            for event in batch:
                self._process_event(event, on_event)

            # Clear seen cache periodically to allow re-processing modified files
            with self._lock:
                self._seen.clear()

    def _process_event(
        self,
        event: ListenerEvent,
        on_event: Optional[Callable],
    ) -> None:
        """
        Processes a single file event through the V9 pipeline:
        1. Stage (V8)
        2. Classify (Judge)
        3. Embed (Inspector)
        """
        fp = event.file_path

        # Wait briefly for the file to finish writing
        if not self._wait_for_file(fp):
            logger.warning(f"[Listener] File not ready after wait: {fp.name}")
            self.stats.files_skipped += 1
            return

        logger.info(f"[Listener] Processing: {fp.name}")
        result = {"file": str(fp), "event_type": event.event_type}

        try:
            # Step 1: Stage
            if self.staging_manager:
                self.staging_manager.stage_file(fp)
                self.stats.files_staged += 1
                result["staged"] = True

            # Step 2: Inspect + Embed
            if self.inspector:
                text = self._extract_text(fp)
                inspection = self.inspector.inspect(
                    file_path=fp,
                    text=text,
                    category="Unknown",
                )
                result["summary"] = inspection.summary
                result["embedded"] = inspection.embedded
                if inspection.embedded:
                    self.stats.files_embedded += 1

        except Exception as e:
            logger.error(f"[Listener] Error processing {fp.name}: {e}")
            self.stats.errors += 1
            result["error"] = str(e)

        event.result = result

        if on_event:
            try:
                on_event(event)
            except Exception as e:
                logger.debug(f"[Listener] on_event callback error: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wait_for_file(path: Path, timeout: float = 5.0, interval: float = 0.25) -> bool:
        """
        Waits until a file is fully written (stable size) before processing.
        Returns True if the file is ready, False if it timed out.
        """
        deadline = time.time() + timeout
        last_size = -1

        while time.time() < deadline:
            try:
                current_size = path.stat().st_size
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
            except OSError:
                pass
            time.sleep(interval)

        return False

    @staticmethod
    def _extract_text(file_path: Path) -> str:
        """
        Extracts text from a file for embedding.
        Supports PDF (via pdfplumber) and plain text files.
        Falls back to empty string on any error.
        """
        try:
            if file_path.suffix.lower() == ".pdf":
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    pages = [p.extract_text() or "" for p in pdf.pages[:10]]
                    return "\n".join(pages)
            elif file_path.suffix.lower() in {".txt", ".csv", ".rtf"}:
                return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"[Listener] Text extraction failed for {file_path.name}: {e}")
        return ""
