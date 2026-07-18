"""
transaction_ledger.py — The Transactional Ledger (Module 5)
FileFlow X (V10)

Enables "Infinite Undo" and self-healing.
Every physical file move (Commit phase) is wrapped in a Transaction.
Records MD5 hashes before and after to ensure absolute data integrity.
"""

import hashlib
import json
import logging
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

class TransactionLedger:
    def __init__(self, ledger_file: Path = Path("data/audit_ledger.json")):
        self.ledger_file = ledger_file
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_file.exists():
            self._write_ledger({})

    def _read_ledger(self) -> dict:
        try:
            with open(self.ledger_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_ledger(self, data: dict):
        with open(self.ledger_file, 'w') as f:
            json.dump(data, f, indent=4)

    def _compute_md5(self, file_path: Path) -> str:
        """Computes the MD5 hash of a file for absolute verification."""
        if not file_path.exists():
            return ""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"[Ledger] Error computing MD5 for {file_path}: {e}")
            return ""

    def start_transaction(self) -> str:
        session_id = str(uuid.uuid4())
        ledger = self._read_ledger()
        ledger[session_id] = {
            "timestamp": datetime.now().isoformat(),
            "status": "in_progress",
            "operations": []
        }
        self._write_ledger(ledger)
        logger.info(f"[Ledger] Started Transaction Session: {session_id}")
        return session_id

    def record_move(self, session_id: str, source: Path, destination: Path) -> bool:
        """
        Records the intent to move a file, calculates its original hash.
        This is called PRE-move.
        """
        source_hash = self._compute_md5(source)
        if not source_hash:
            logger.error(f"[Ledger] Source missing or unreadable: {source}")
            return False

        ledger = self._read_ledger()
        if session_id not in ledger:
            return False

        operation = {
            "op_id": str(uuid.uuid4()),
            "action": "move",
            "source_path": str(source.absolute()),
            "source_md5": source_hash,
            "destination_path": str(destination.absolute()),
            "dest_md5": None, # Filled post-move
            "status": "pending"
        }
        
        ledger[session_id]["operations"].append(operation)
        self._write_ledger(ledger)
        return True

    def commit_move(self, session_id: str, op_index: int, destination: Path) -> bool:
        """
        Called POST-move to verify the destination hash matches the source hash.
        If they match, the operation is verified.
        """
        dest_hash = self._compute_md5(destination)
        
        ledger = self._read_ledger()
        try:
            op = ledger[session_id]["operations"][op_index]
            if dest_hash == op["source_md5"]:
                op["dest_md5"] = dest_hash
                op["status"] = "verified"
                self._write_ledger(ledger)
                return True
            else:
                op["status"] = "hash_mismatch"
                self._write_ledger(ledger)
                logger.error(f"[Ledger] ALARM: Hash mismatch on move: {op['source_path']} -> {destination}")
                return False
        except (KeyError, IndexError):
            return False

    def close_transaction(self, session_id: str):
        ledger = self._read_ledger()
        if session_id in ledger:
            ledger[session_id]["status"] = "completed"
            self._write_ledger(ledger)
            logger.info(f"[Ledger] Closed Transaction Session: {session_id}")

    def rollback(self, session_id: str) -> bool:
        """
        Reverses all operations in a session to restore the original state.
        Never deletes a file without ensuring the original exists.
        """
        ledger = self._read_ledger()
        if session_id not in ledger:
            logger.error(f"[Ledger] Cannot rollback unknown session: {session_id}")
            return False

        session = ledger[session_id]
        if session["status"] == "rolled_back":
            return True

        logger.warning(f"[Ledger] INITIATING ROLLBACK FOR SESSION: {session_id}")
        
        all_success = True
        # Iterate backwards to undo in reverse order
        for op in reversed(session["operations"]):
            if op["status"] in ["verified", "pending", "hash_mismatch"]:
                try:
                    src = Path(op["source_path"])
                    dst = Path(op["destination_path"])
                    
                    if dst.exists():
                        # If destination exists and source is missing, move it back
                        if not src.exists():
                            src.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(dst), str(src))
                            logger.info(f"[Ledger] Rolled back: {dst.name} -> {src.parent}")
                        # If both exist, the source was never deleted (like a copy). Just remove the new copy.
                        else:
                            dst.unlink()
                            logger.info(f"[Ledger] Removed unverified copy: {dst.name}")
                            
                    op["status"] = "reverted"
                except Exception as e:
                    logger.error(f"[Ledger] Failed to revert {op['op_id']}: {e}")
                    op["status"] = "revert_failed"
                    all_success = False
        
        session["status"] = "rolled_back" if all_success else "partially_rolled_back"
        self._write_ledger(ledger)
        return all_success
