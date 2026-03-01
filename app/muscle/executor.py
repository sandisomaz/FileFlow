import hashlib
import shutil
import os
import math
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from rich import print as rprint


class ArchiveEngine:
    """
    Implements the 'Archive before act' safety rule.
    Ensures a backup copy of a file exists in a safe location
    before any operations are performed.
    """
    def __init__(self, archive_root: Path):
        self.archive_root = archive_root
        self.archive_root.mkdir(parents=True, exist_ok=True)

    def archive(self, src: Path) -> bool:
        """Creates a timestamped backup in the archive folder."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Relative path to keep structure if needed, or flat? 
            # Let's go with a flat structure with original path info encoded
            safe_name = f"{timestamp}_{src.name}"
            dst = self.archive_root / safe_name
            
            shutil.copy2(src, dst)
            rprint(f"[ArchiveEngine] Backup created: {dst.name}")
            return True
        except Exception as e:
            rprint(f"[ArchiveEngine] FAILED to archive {src}: {e}")
            return False


class AtomicExecutor:
    def __init__(self, dry_run: bool = True, bridge=None, archive_root: Path = None):
        """
        Args:
            dry_run: If True, only prints what would happen (never touches files)
            bridge:  Optional Bridge for semantic deduplication (V9 Cognition)
            archive_root: Optional path for the ArchiveEngine
        """
        self.dry_run = dry_run
        self.bridge = bridge  # V9: used for semantic dedup
        self.archive_engine = ArchiveEngine(archive_root) if archive_root else None

        # V9: In-memory embedding cache for semantic dedup
        # Maps file_path_str → embedding vector
        self._embedding_cache: Dict[str, List[float]] = {}

    def safe_copy(self, src: Path, dst: Path) -> bool:
        """
        Copies file, verifies integrity, then returns True.
        Example Usage:
            if safe_copy(src, dst):
            # SAFETY LOCK: Source deletion is PERMANENTLY DISABLED
            # src.unlink()
            rprint(f"[SAFETY] Archived copy created. Source preserved: {src}")
        """
        if self.dry_run:
            rprint(f"[DRY RUN] Copy {src} -> {dst}")
            return True

        try:
            # SAFETY LOCK: ARCHIVE BEFORE ACT
            if self.archive_engine and not self.dry_run:
                if not self.archive_engine.archive(src):
                    rprint(f"[SAFETY] Aborting copy: Archive failed for {src}")
                    return False

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            # Verify copy
            if self._verify_copy(src, dst):
                return True
            else:
                rprint(f"Verification failed for {dst}")
                if dst.exists():
                    dst.unlink()  # Rollback bad copy
                return False
        except Exception as e:
            rprint(f"Error copying {src}: {e}")
            return False

    def safe_delete(self, path: Path) -> bool:
        if self.dry_run:
            rprint(f"[DRY RUN] Delete {path}")
            return True

        try:
            path.unlink()
            return True
        except Exception as e:
            rprint(f"Error deleting {path}: {e}")
            return False

    # ------------------------------------------------------------------
    # V9 Cognition: Semantic Deduplication
    # ------------------------------------------------------------------

    def is_semantic_duplicate(
        self,
        text_a: str,
        text_b: str,
        threshold: float = 0.95,
    ) -> bool:
        """
        Determines if two documents are semantically identical using embeddings.

        Two documents are considered semantic duplicates if their embedding
        cosine similarity exceeds the threshold (default: 0.95).

        Falls back to exact MD5 hash comparison if bridge is offline.

        Args:
            text_a:    Extracted text from file A
            text_b:    Extracted text from file B
            threshold: Cosine similarity threshold (0.0–1.0)

        Returns:
            True if the documents are semantic duplicates
        """
        # Fast path: exact text match
        if text_a and text_b and text_a.strip() == text_b.strip():
            return True

        # Fast path: MD5 hash match (catches identical binary content)
        if text_a and text_b:
            hash_a = hashlib.md5(text_a.encode("utf-8", errors="replace")).hexdigest()
            hash_b = hashlib.md5(text_b.encode("utf-8", errors="replace")).hexdigest()
            if hash_a == hash_b:
                return True

        # Slow path: semantic similarity via embeddings
        if self.bridge and self.bridge.is_healthy():
            embed_a = self.bridge.embed(text_a[:3000]) if text_a else None
            embed_b = self.bridge.embed(text_b[:3000]) if text_b else None

            if embed_a and embed_b:
                similarity = self._cosine_similarity(embed_a, embed_b)
                return similarity >= threshold

        return False

    def find_semantic_duplicates(
        self,
        file_texts: Dict[str, str],
        threshold: float = 0.95,
    ) -> List[tuple]:
        """
        Finds all semantic duplicate pairs in a collection of files.

        Args:
            file_texts: Dict mapping file_path_str → extracted_text
            threshold:  Cosine similarity threshold

        Returns:
            List of (path_a, path_b, similarity_score) tuples
        """
        paths = list(file_texts.keys())
        duplicates = []

        # Embed all files first (batch for efficiency)
        embeddings: Dict[str, Optional[List[float]]] = {}
        if self.bridge and self.bridge.is_healthy():
            for path, text in file_texts.items():
                if text:
                    embeddings[path] = self.bridge.embed(text[:3000])
                else:
                    embeddings[path] = None

        # Compare all pairs (O(n²) — acceptable for typical archive sizes)
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                path_a, path_b = paths[i], paths[j]
                text_a, text_b = file_texts[path_a], file_texts[path_b]

                # Quick MD5 check first
                if text_a and text_b:
                    h_a = hashlib.md5(text_a.encode("utf-8", errors="replace")).hexdigest()
                    h_b = hashlib.md5(text_b.encode("utf-8", errors="replace")).hexdigest()
                    if h_a == h_b:
                        duplicates.append((path_a, path_b, 1.0))
                        continue

                # Semantic check
                emb_a = embeddings.get(path_a)
                emb_b = embeddings.get(path_b)
                if emb_a and emb_b:
                    sim = self._cosine_similarity(emb_a, emb_b)
                    if sim >= threshold:
                        duplicates.append((path_a, path_b, sim))

        return duplicates

    # ------------------------------------------------------------------
    # Integrity verification (V8 preserved)
    # ------------------------------------------------------------------

    def _verify_copy(self, src: Path, dst: Path) -> bool:
        """
        Check if file size and hash match.
        """
        if src.stat().st_size != dst.stat().st_size:
            return False

        return self._calculate_md5(src) == self._calculate_md5(dst)

    def _calculate_md5(self, file_path: Path, chunk_size=8192) -> str:
        md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    md5.update(chunk)
            return md5.hexdigest()
        except OSError:
            return ""

    # ------------------------------------------------------------------
    # Math
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """
        Computes cosine similarity between two vectors.
        Returns a value between -1.0 and 1.0 (1.0 = identical direction).
        """
        if len(vec_a) != len(vec_b):
            # Truncate to shorter length
            min_len = min(len(vec_a), len(vec_b))
            vec_a = vec_a[:min_len]
            vec_b = vec_b[:min_len]

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))

        if mag_a == 0 or mag_b == 0:
            return 0.0

        return dot / (mag_a * mag_b)

