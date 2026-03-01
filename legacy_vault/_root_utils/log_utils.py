#utils/log_utils.py

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Define the log file path as a constant
LOG_PATH = Path("move_log.jsonl")

def log_move(
    src: str,
    dst: str,
    category: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None
) -> None:
    """Appends a single move operation log entry to the JSONL file."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": src,
        "destination": dst,
        "category": category,
        "success": success,
        "error": error,
    }
    try:
        # 'a' mode creates the file if it doesn't exist and appends to it
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except IOError as e:
        print(f"Error: Could not write to log file {LOG_PATH}: {e}")

def read_log_entries() -> List[Dict[str, Any]]:
    """Reads all entries from the JSONL log file."""
    if not LOG_PATH.exists():
        return []
    
    entries = []
    with LOG_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                # Silently skip corrupted lines
                continue
    return entries

def remove_last_log_entry() -> bool:
    """Removes the last line from the log file (used by the undo function)."""
    entries = read_log_entries()
    if not entries:
        return False
    
    # Keep all entries except the last one
    entries_to_keep = entries[:-1]
    
    with LOG_PATH.open("w", encoding="utf-8") as fh:
        for entry in entries_to_keep:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True

def get_last_log_entry() -> Optional[Dict[str, Any]]:
    """Retrieves the most recent log entry from the file."""
    entries = read_log_entries()
    return entries[-1] if entries else None