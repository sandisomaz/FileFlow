"""
inspector.py — The Document Reader
FileFlow Cognition V9

The Inspector reads every document, understands its content, generates a
one-sentence summary, and feeds it into Memory for later retrieval.

It is the bridge between raw files and semantic understanding.

Flow:
    file → read text → chunk → summarise (SLM) → embed → Memory.remember()
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from fileflow.intelligence.bridge import Bridge
from fileflow.intelligence.memory import Memory

logger = logging.getLogger(__name__)

# Max characters sent to the SLM for summarisation
SUMMARY_PREVIEW_CHARS = 600

# Max characters per chunk sent to the embedder
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 150


@dataclass
class InspectionResult:
    """The Inspector's report on a single file."""
    file_path: str
    summary: str            # One-sentence human-readable summary
    category: str           # Archive taxonomy category
    sub_type: str
    entity: str
    chunk_count: int        # How many chunks were embedded
    embedded: bool          # Was it stored in Memory?
    error: Optional[str] = None


class Inspector:
    """
    The sovereign document reader for FileFlow Cognition.

    Reads a file's extracted text, generates a summary, and stores
    the embedding in Memory so Discovery can find it later.

    Usage:
        inspector = Inspector(bridge=bridge, memory=memory)
        result = inspector.inspect(file_path, text, category, sub_type, entity)
    """

    def __init__(self, bridge: Bridge, memory: Memory):
        self.bridge = bridge
        self.memory = memory
        self._prompt_template: Optional[str] = None
        self._load_prompt()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inspect(
        self,
        file_path: Path,
        text: str,
        category: str = "Unknown",
        sub_type: str = "Unknown",
        entity: str = "",
    ) -> InspectionResult:
        """
        Reads a document, generates a summary, and stores it in Memory.

        Args:
            file_path:  Path to the file
            text:       Extracted text content (may be empty)
            category:   Archive taxonomy category (from the Judge)
            sub_type:   V8 sub_type
            entity:     V8 entity name

        Returns:
            InspectionResult with summary and embedding status
        """
        # Step 1: Generate a summary
        summary = self._summarise(file_path, text)

        # Step 2: Chunk the text for embedding
        chunks = self._chunk(text) if text else [file_path.name]

        # Step 3: Embed and store in Memory
        embedded = False
        if self.bridge.is_healthy() and self.memory._available:
            # Use summary + first chunk as the embedding text for best recall
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
            f"[Inspector] {file_path.name} → summary={summary[:60]}... "
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
        """
        Inspects a batch of files.

        Args:
            files: List of dicts with keys: file_path, text, category, sub_type, entity
            progress_callback: Optional callable(current, total, filename) for progress reporting

        Returns:
            List of InspectionResult
        """
        results = []
        total = len(files)

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
                logger.warning(f"[Inspector] Failed to inspect {f.get('file_path')}: {e}")
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

    # ------------------------------------------------------------------
    # Summarisation
    # ------------------------------------------------------------------

    def _summarise(self, file_path: Path, text: str) -> str:
        """
        Asks the SLM to write a one-sentence summary of the document.
        Falls back to a filename-based description if Ollama is offline.
        """
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

        # Clean up: strip quotes, newlines, leading/trailing whitespace
        summary = raw.strip().strip('"').strip("'").split("\n")[0].strip()

        # Sanity check: if the SLM returned something too long, truncate
        if len(summary) > 300:
            summary = summary[:297] + "..."

        return summary

    @staticmethod
    def _filename_summary(file_path: Path) -> str:
        """Generates a basic summary from the filename when AI is unavailable."""
        name = file_path.stem.replace("_", " ").replace("-", " ").title()
        ext = file_path.suffix.upper().lstrip(".")
        return f"{name} ({ext} file)."

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
        """
        Splits text into overlapping chunks for embedding.

        Overlap ensures that sentences spanning chunk boundaries are still
        captured in at least one chunk's embedding.
        """
        if not text:
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = start + size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap  # step back by overlap amount

        return chunks if chunks else [text]

    # ------------------------------------------------------------------
    # Prompt loading
    # ------------------------------------------------------------------

    def _load_prompt(self):
        prompt_path = Path(__file__).parent / "prompts" / "summarize.md"
        try:
            self._prompt_template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("[Inspector] summarize.md not found. Using inline fallback.")
            self._prompt_template = (
                "Write one sentence describing this document. "
                "Be specific. Include names, dates, amounts if present."
            )
