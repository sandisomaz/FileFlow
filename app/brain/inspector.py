"""
inspector.py — The Document Reader
FileFlow Cognition V9

Reads every document, generates a one-sentence summary,
and feeds it into Memory for later retrieval via Discovery.

Flow:
    file → read text → summarise (SLM) → embed → Memory.remember()
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .bridge import Bridge
from app.memory.memory import Memory

logger = logging.getLogger(__name__)

SUMMARY_PREVIEW_CHARS = 600
CHUNK_SIZE    = 1500
CHUNK_OVERLAP = 150


@dataclass
class InspectionResult:
    file_path:   str
    summary:     str
    category:    str
    sub_type:    str
    entity:      str
    chunk_count: int
    embedded:    bool
    error:       Optional[str] = None


class Inspector:
    """
    The sovereign document reader for FileFlow Cognition.

    Usage:
        inspector = Inspector(bridge=bridge, memory=memory)
        result = inspector.inspect(file_path, text, category, sub_type, entity)
    """

    def __init__(self, bridge: Bridge, memory: Memory):
        self.bridge  = bridge
        self.memory  = memory
        self._prompt_template: Optional[str] = None
        self._load_prompt()

    # ── Public API ─────────────────────────────────────────────────────────────

    def inspect(
        self,
        file_path: Path,
        text:      str,
        category:  str = "Unknown",
        sub_type:  str = "Unknown",
        entity:    str = "",
    ) -> InspectionResult:
        """
        Reads a document, generates a summary, and stores it in Memory.
        Safe to call when AI is offline — falls back gracefully.
        """
        # Step 1: Summary
        summary = self._summarise(file_path, text)

        # Step 2: Chunk
        chunks = self._chunk(text) if text else [file_path.name]

        # Step 3: Embed + store
        # Use the public is_available property — not the private _available attribute
        embedded = False
        if self.bridge.is_healthy() and self.memory.is_available:
            embed_text = f"{summary}\n\n{chunks[0]}" if chunks else summary
            embedded = self.memory.remember(
                file_path=file_path,
                text=embed_text,
                category=category,
                sub_type=sub_type,
                entity=entity,
                summary=summary,
            )

        logger.debug(
            f"[Inspector] {file_path.name} → {summary[:60]}... "
            f"chunks={len(chunks)} embedded={embedded}"
        )

        return InspectionResult(
            file_path=str(file_path),
            summary=summary,
            category=category,
            sub_type=sub_type,
            entity=entity,
            chunk_count=len(chunks),
            embedded=embedded,
        )

    def inspect_batch(
        self,
        files: List[dict],
        progress_callback=None,
    ) -> List[InspectionResult]:
        """Inspects a batch of files. Each dict: {file_path, text, category, sub_type, entity}"""
        results = []
        total   = len(files)

        for i, f in enumerate(files):
            if progress_callback:
                progress_callback(i + 1, total, Path(f["file_path"]).name)
            try:
                result = self.inspect(
                    file_path=Path(f["file_path"]),
                    text=f.get("text", ""),
                    category=f.get("category", "Unknown"),
                    sub_type=f.get("sub_type", "Unknown"),
                    entity=f.get("entity", ""),
                )
                results.append(result)
            except Exception as e:
                logger.warning(f"[Inspector] Failed: {f.get('file_path')}: {e}")
                results.append(InspectionResult(
                    file_path=f.get("file_path", ""),
                    summary="Inspection failed.",
                    category="Unknown",
                    sub_type="Unknown",
                    entity="",
                    chunk_count=0,
                    embedded=False,
                    error=str(e),
                ))

        return results

    # ── Summarisation ──────────────────────────────────────────────────────────

    def _summarise(self, file_path: Path, text: str) -> str:
        if not self.bridge.is_healthy():
            return self._filename_summary(file_path)

        content_preview = text[:SUMMARY_PREVIEW_CHARS] if text else ""
        if not content_preview:
            return self._filename_summary(file_path)

        prompt = (
            f"{self._prompt_template}\n\n"
            f"---\n"
            f"filename: {file_path.name}\n"
            f"content_preview:\n{content_preview}\n"
            f"---\n"
            f"Write your one-sentence summary:"
        )

        raw = self.bridge.generate(prompt)
        if not raw or len(raw.strip()) < 5:
            return self._filename_summary(file_path)

        summary = raw.strip().strip('"').strip("'").split("\n")[0].strip()
        if len(summary) > 300:
            summary = summary[:297] + "..."
        return summary

    @staticmethod
    def _filename_summary(file_path: Path) -> str:
        name = file_path.stem.replace("_", " ").replace("-", " ").title()
        ext  = file_path.suffix.upper().lstrip(".")
        return f"{name} ({ext} file)."

    # ── Chunking ───────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
        if not text:
            return []
        chunks, start = [], 0
        while start < len(text):
            chunk = text[start : start + size]
            if chunk.strip():
                chunks.append(chunk)
            start += size - overlap
        return chunks or [text]

    # ── Prompt loading ─────────────────────────────────────────────────────────

    def _load_prompt(self):
        # BUGFIX: was CWD-relative — see judge.py for the same issue.
        prompt_path = Path(__file__).resolve().parent.parent.parent / "config" / "prompts" / "summarize.md"
        try:
            self._prompt_template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("[Inspector] summarize.md not found — using inline fallback.")
            self._prompt_template = (
                "Write one sentence describing this document. "
                "Be specific. Include names, dates, amounts if present."
            )