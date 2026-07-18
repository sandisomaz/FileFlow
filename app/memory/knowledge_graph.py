"""
knowledge_graph.py — The Fact Bank
FileFlow X (V10)

This module implements the "Relational Cognitive Index". Instead of just storing files
in folders, we store them as Nodes in a Graph, linked by Shared Facts (Edges).

When the Sniffer or Judge detects a "Fact" (e.g., CaseRef=123, Email=john@smith.com),
that fact becomes a central node. All files containing that fact are linked to it.
This enables cross-contextual relationships and O(1) matching for future files.
"""

import sqlite3
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Set, Optional

logger = logging.getLogger(__name__)

@dataclass
class GraphNode:
    """Represents a File or a Fact in the Graph."""
    node_id: str          # File hash or Fact value
    node_type: str        # 'FILE', 'FACT', 'AUTHOR', 'CASE'
    label: str            # Display name
    properties: Dict = field(default_factory=dict)

@dataclass
class GraphEdge:
    """Represents a relationship between Nodes."""
    source_id: str
    target_id: str
    relation: str         # 'CONTAINS', 'VERSION_OF', 'REFERENCES'
    confidence: float     # 0.0 - 1.0

class KnowledgeGraph:
    """
    The Local Fact Bank powered by SQLite for persistence and speed.
    (In a full production V10, this could bridge to LanceDB or Grakn).
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the Graph schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            # Nodes Table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    properties TEXT
                )
            ''')
            # Edges Table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT,
                    target_id TEXT,
                    relation TEXT,
                    confidence REAL,
                    PRIMARY KEY (source_id, target_id, relation),
                    FOREIGN KEY(source_id) REFERENCES nodes(id),
                    FOREIGN KEY(target_id) REFERENCES nodes(id)
                )
            ''')

    def add_file_node(self, file_hash: str, filename: str, metadata: dict = None) -> str:
        """Adds a document to the graph."""
        props = json.dumps(metadata) if metadata else "{}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO nodes (id, type, label, properties) VALUES (?, ?, ?, ?)',
                (file_hash, 'FILE', filename, props)
            )
        return file_hash

    def add_fact_node(self, fact_type: str, fact_value: str) -> str:
        """Adds a global fact (e.g., 'SA_ID_870101...', 'CASE_123')."""
        node_id = f"{fact_type}_{fact_value}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT OR IGNORE INTO nodes (id, type, label, properties) VALUES (?, ?, ?, ?)',
                (node_id, 'FACT', fact_value, json.dumps({'fact_type': fact_type}))
            )
        return node_id

    def link_nodes(self, source_id: str, target_id: str, relation: str, confidence: float = 1.0):
        """Creates an edge between a File and a Fact."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO edges (source_id, target_id, relation, confidence) VALUES (?, ?, ?, ?)',
                (source_id, target_id, relation, confidence)
            )

    def ingest_sniff_result(self, file_hash: str, filename: str, extract: dict):
        """
        Takes a result from the Sniffer and directly broadcasts it into the graph.
        """
        # 1. Add the file
        self.add_file_node(file_hash, filename, extract)
        
        # 2. Add and link every extracted fact
        for fact_key, fact_value in extract.get('facts', {}).items():
            fact_id = self.add_fact_node(fact_key, fact_value)
            self.link_nodes(source_id=file_hash, target_id=fact_id, relation="CONTAINS")
            logger.info(f"[Graph] Linked {filename} -> Fact({fact_key}:{fact_value})")

    def get_related_files(self, fact_type: str, fact_value: str) -> List[dict]:
        """
        Find all files that share a specific fact (e.g., get all files with CaseID=123).
        This replaces searching by folder structure.
        """
        fact_id = f"{fact_type}_{fact_value}"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT n.* FROM nodes n
                JOIN edges e ON n.id = e.source_id
                WHERE e.target_id = ? AND n.type = 'FILE'
            ''', (fact_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_file_clusters(self) -> Dict[str, List[str]]:
        """
        Returns dynamic clusters of files based on shared facts.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT e.target_id AS fact_id, n.label AS filename
                FROM edges e
                JOIN nodes n ON e.source_id = n.id
                WHERE e.relation = 'CONTAINS'
            ''')
            
            clusters = {}
            for row in cursor:
                fact, filename = row
                if fact not in clusters:
                    clusters[fact] = []
                clusters[fact].append(filename)
                
        # Filter purely to interesting clusters (>1 file)
        return {k: v for k, v in clusters.items() if len(v) > 1}

    def search_nodes(self, query: str) -> List[dict]:
        """
        Keyword search across all nodes (files and facts).
        Used for precision lookup before falling back to full semantic search.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM nodes 
                WHERE label LIKE ? OR id LIKE ?
                LIMIT 10
            ''', (f"%{query}%", f"%{query}%"))
            return [dict(row) for row in cursor.fetchall()]

    def get_files_by_fact_keyword(self, keyword: str) -> List[dict]:
        """
        Finds all files linked to facts that match the keyword (e.g., 'Registrar').
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT DISTINCT n_file.* FROM nodes n_file
                JOIN edges e ON n_file.id = e.source_id
                JOIN nodes n_fact ON e.target_id = n_fact.id
                WHERE n_fact.type = 'FACT' 
                AND (n_fact.label LIKE ? OR n_fact.id LIKE ?)
                AND n_file.type = 'FILE'
            ''', (f"%{keyword}%", f"%{keyword}%"))
            return [dict(row) for row in cursor.fetchall()]

    def get_entity_count(self) -> int:
        """Returns the number of unique FACTS (Entities) in the graph."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'FACT'")
            return cursor.fetchone()[0]


class FactBroadcaster:
    """
    Allows Worker A to save a discovered Fact (e.g., Case ID) so Worker B 
    can immediately identify related files without using the LLM.
    """
    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph

    def broadcast_fact(self, file_hash: str, filename: str, fact_type: str, fact_value: str, relation: str = "CONTAINS", confidence: float = 1.0):
        """Broadcasts a newly discovered fact to the graph immediately."""
        self.graph.add_file_node(file_hash, filename)
        fact_id = self.graph.add_fact_node(fact_type, fact_value)
        self.graph.link_nodes(source_id=file_hash, target_id=fact_id, relation=relation, confidence=confidence)
        logger.info(f"[FactBroadcaster] 📢 Broadcasted {fact_type}: {fact_value} from {filename}")

    def query_fact(self, fact_type: str, fact_value: str) -> List[dict]:
        """Worker B checks if a fact is already known in the system."""
        return self.graph.get_related_files(fact_type, fact_value)
