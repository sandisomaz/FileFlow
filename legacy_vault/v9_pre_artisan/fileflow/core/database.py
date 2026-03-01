import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Optional

class DatabaseManager:
    """
    Handles SQLite persistence for tasks and audit logs.
    """
    def __init__(self, db_path: str = "data/fileflow.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            # Tasks table: Stores session/task state
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    status TEXT,
                    progress INTEGER,
                    created_at TEXT,
                    source TEXT,
                    scope TEXT,
                    stats TEXT, -- JSON
                    plan TEXT,  -- JSON
                    scout_report TEXT, -- JSON
                    execution_log TEXT -- JSON
                )
            """)
            
            # Audit table: Stores every file operation
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    timestamp TEXT,
                    original_path TEXT,
                    entity TEXT,
                    subtype TEXT,
                    md5 TEXT,
                    status TEXT,
                    notes TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                )
            """)
            conn.commit()

    # --- Task Operations ---

    def save_task(self, task_id: str, data: Dict):
        """Persists or updates a task in the DB."""
        sql = """
            INSERT INTO tasks (id, name, status, progress, created_at, source, scope, stats, plan, scout_report, execution_log)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                progress=excluded.progress,
                stats=excluded.stats,
                plan=excluded.plan,
                scout_report=excluded.scout_report,
                execution_log=excluded.execution_log
        """
        with self._get_conn() as conn:
            conn.execute(sql, (
                task_id,
                data.get("name"),
                data.get("status"),
                data.get("progress"),
                data.get("created_at"),
                data.get("source"),
                data.get("scope"),
                json.dumps(data.get("stats", {})),
                json.dumps(data.get("plan", [])),
                json.dumps(data.get("scout_report", {})),
                json.dumps(data.get("execution_log", []))
            ))
            conn.commit()

    def get_task(self, task_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                d = dict(row)
                d["stats"] = json.loads(d["stats"] or "{}")
                d["plan"] = json.loads(d["plan"] or "[]")
                d["scout_report"] = json.loads(d["scout_report"] or "{}")
                d["execution_log"] = json.loads(d["execution_log"] or "[]")
                return d
        return None

    def list_tasks(self, limit: int = 50) -> List[Dict]:
        """Returns recent tasks (sessions)."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            tasks = []
            for row in rows:
                d = dict(row)
                d["stats"] = json.loads(d["stats"] or "{}")
                # We skip large blobs like plan/scout_report for list view
                tasks.append(d)
            return tasks

    # --- Audit Operations ---

    def log_operation(self, task_id: str, original: str, entity: str, subtype: str, md5: str, status: str, notes: str = ""):
        sql = """
            INSERT INTO audit_log (task_id, timestamp, original_path, entity, subtype, md5, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._get_conn() as conn:
            conn.execute(sql, (task_id, timestamp, original, entity, subtype, md5, status, notes))
            conn.commit()

    def get_audit_for_task(self, task_id: str) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM audit_log WHERE task_id = ?", (task_id,)).fetchall()
            return [dict(row) for row in rows]
