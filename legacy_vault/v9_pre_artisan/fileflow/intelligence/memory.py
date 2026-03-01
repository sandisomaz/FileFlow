"""
memory.py — The Long-Term Vector Store
FileFlow Cognition V9

This is where FileFlow remembers what your files mean.
Every document that passes through the system gets embedded and stored here.
Later, the Discovery module uses this to answer questions like:
  "Find my ID document"
  "Where are all my lease agreements?"

Storage: LanceDB (local, zero-server, pure Python)
Embeddings: qwen3-embedding via Ollama (bridge.py)
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Lazy import — lancedb is optional. System works without it (Phase 1 fallback).
try:
    import lancedb
    import pyarrow as pa
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    logger.warning(
        "[Memory] lancedb not installed. Vector memory disabled. "
        "Run: pip install lancedb pyarrow"
    )


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

SCHEMA_FIELDS = [
    ("file_path", pa.string()),
    ("file_name", pa.string()),
    ("content_hash", pa.string()),
    ("category", pa.string()),
    ("sub_type", pa.string()),
    ("entity", pa.string()),
    ("summary", pa.string()),
    ("embedding", pa.list_(pa.float32(), 2560)),  # qwen3-embedding dim
    ("indexed_at", pa.float64()),                 # unix timestamp
]

TABLE_NAME = "file_memory"


@dataclass
class MemoryRecord:
    file_path: str
    file_name: str
    content_hash: str
    category: str
    sub_type: str
    entity: str
    summary: str
    embedding: List[float]
    indexed_at: float


class Memory:
    """
    The sovereign long-term memory of FileFlow.

    Stores vector embeddings of every processed document so the system
    can answer semantic queries about your file system.

    Usage:
        memory = Memory(db_path="fileflow_data/vectors.lance", bridge=bridge)
        memory.remember(file_path, text, ruling)
        results = memory.recall("find my lease agreement")
    """

    def __init__(self, db_path: str, bridge):
        self.db_path = db_path
        self.bridge = bridge
        self._db = None
        self._table = None
        self._available = LANCEDB_AVAILABLE

        if self._available:
            self._connect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self):
        """Open or create the LanceDB database."""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self.db_path)

            if TABLE_NAME in self._db.table_names():
                self._table = self._db.open_table(TABLE_NAME)
                logger.debug(f"[Memory] Opened existing table '{TABLE_NAME}' at {self.db_path}")
            else:
                schema = pa.schema([(name, dtype) for name, dtype in SCHEMA_FIELDS])
                self._table = self._db.create_table(TABLE_NAME, schema=schema)
                logger.debug(f"[Memory] Created new table '{TABLE_NAME}' at {self.db_path}")

        except Exception as e:
            logger.warning(f"[Memory] Failed to connect to LanceDB: {e}. Memory disabled.")
            self._available = False

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def remember(
        self,
        file_path: Path,
        text: str,
        category: str = "Unknown",
        sub_type: str = "Unknown",
        entity: str = "",
        summary: str = "",
    ) -> bool:
        """
        Embeds a document and stores it in memory.

        Skips files that are already in memory with the same content hash
        (incremental indexing — only re-embeds changed files).

        Returns True if the record was stored, False otherwise.
        """
        if not self._available:
            return False

        content_hash = self._hash(text or file_path.name)

        # Skip if already indexed with same content
        if self._already_indexed(str(file_path), content_hash):
            logger.debug(f"[Memory] Skipping (unchanged): {file_path.name}")
            return False

        # Get embedding from bridge
        embed_text = text[:4000] if text else file_path.name
        embedding = self.bridge.embed(embed_text)

        if not embedding:
            logger.debug(f"[Memory] No embedding for {file_path.name} (bridge offline)")
            return False

        # Pad or truncate embedding to exactly 2560 dims (qwen3-embedding)
        embedding = self._normalise_embedding(embedding, 2560)

        record = {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "content_hash": content_hash,
            "category": category,
            "sub_type": sub_type,
            "entity": entity,
            "summary": summary,
            "embedding": embedding,
            "indexed_at": time.time(),
        }

        try:
            self._table.add([record])
            logger.debug(f"[Memory] Remembered: {file_path.name} → {category}")
            return True
        except Exception as e:
            logger.warning(f"[Memory] Failed to store record: {e}")
            return False

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall(self, query: str, top_k: int = 5) -> List[dict]:
        """
        Semantic search: find the most relevant files for a natural language query.

        Returns a list of dicts with file_path, file_name, category, score, summary.
        """
        if not self._available:
            return []

        embedding = self.bridge.embed(query)
        if not embedding:
            logger.debug("[Memory] recall() skipped — bridge offline")
            return []

        embedding = self._normalise_embedding(embedding, 2560)

        try:
            results = (
                self._table.search(embedding)
                .limit(top_k)
                .to_list()
            )
            return [
                {
                    "file_path": r["file_path"],
                    "file_name": r["file_name"],
                    "category": r["category"],
                    "entity": r["entity"],
                    "summary": r["summary"],
                    "score": r.get("_distance", 0.0),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"[Memory] recall() failed: {e}")
            return []

    def get_stats(self) -> dict:
        """Returns basic stats about what's in memory."""
        if not self._available or self._table is None:
            return {"available": False, "total_records": 0}
        try:
            count = self._table.count_rows()
            return {"available": True, "total_records": count, "db_path": self.db_path}
        except Exception:
            return {"available": True, "total_records": "unknown"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _already_indexed(self, file_path: str, content_hash: str) -> bool:
        """Check if this exact file+hash combo is already in memory."""
        if not self._table:
             return False
        try:
            # Escape single quotes for SQL-like safety
            safe_path = file_path.replace("'", "''")
            results = (
                self._table.search()
                .where(f"file_path = '{safe_path}' AND content_hash = '{content_hash}'")
                .limit(1)
                .to_list()
            )
            return len(results) > 0
        except Exception:
            return False

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _normalise_embedding(embedding: list, target_dim: int) -> list:
        """Pad with zeros or truncate to match the schema dimension."""
        if len(embedding) == target_dim:
            return embedding
        if len(embedding) < target_dim:
            return embedding + [0.0] * (target_dim - len(embedding))
        return embedding[:target_dim]
