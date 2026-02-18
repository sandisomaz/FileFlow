"""
Persistent logging for FileFlow V8.
Captures terminal output and internal events to disk.
"""

import os
import sys
import io
import datetime
from pathlib import Path
from rich.console import Console


class SessionLogger:
    """
    Context manager that mirrors console output to a file.
    Ensures UTF-8 encoding for production safety.
    """
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_file_path = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.file_handle = None

    def __enter__(self):
        # Ensure logs directory exists
        if not self.log_dir.exists():
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = self.log_dir / f"session_{timestamp}.log"

        # Open file in UTF-8 mode
        try:
            self.file_handle = open(self.log_file_path, "w", encoding="utf-8", buffering=1)
            
            # Wrap standard streams to write to both original and file
            sys.stdout = DualStream(self.original_stdout, self.file_handle)
            sys.stderr = DualStream(self.original_stderr, self.file_handle)
            
            # Print log header
            print(f"--- SESSION LOG STARTED: {datetime.datetime.now()} ---")
            print(f"--- LOG FILE: {self.log_file_path.absolute()} ---")
            print("-" * 50)
            
        except Exception as e:
            # Fallback if file logging fails
            sys.stdout.write(f"\n⚠️ WARNING: Could not initialize session logger: {e}\n")
            
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original streams
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        if self.file_handle:
            print("-" * 50)
            print(f"--- SESSION LOG CLOSED: {datetime.datetime.now()} ---")
            self.file_handle.close()


class DualStream:
    """
    Writes output to two streams simultaneously.
    """
    def __init__(self, stream1, stream2):
        self.stream1 = stream1
        self.stream2 = stream2

    def write(self, data):
        self.stream1.write(data)
        if self.stream2:
            try:
                self.stream2.write(data)
            except UnicodeEncodeError:
                # Fallback for streams that don't support UTF-8 (though we opened the file with it)
                self.stream2.write(data.encode('ascii', 'replace').decode('ascii'))

    def flush(self):
        self.stream1.flush()
        if self.stream2:
            self.stream2.flush()

    # Mimic buffer attribute if requested (needed by some Rich/IO wrappers)
    @property
    def buffer(self):
        return getattr(self.stream1, 'buffer', None)
        
    def isatty(self):
        """Pass through isatty validation to the primary stream."""
        return getattr(self.stream1, 'isatty', lambda: False)()

    def fileno(self):
        """Pass through fileno to the primary stream."""
        return getattr(self.stream1, 'fileno', lambda: -1)()


class MigrationLogger:
    """
    CSV Audit Logger for tracking every file operation.
    """
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.log_dir / "migration_audit.csv"
        
        # Initialize with header if new
        if not self.csv_path.exists():
            with open(self.csv_path, "w", encoding="utf-8") as f:
                f.write("Timestamp,Original_Path,New_Entity,SubType,MD5,Status,Notes\n")
    
    def log(self, original: Path, entity: str, subtype: str, md5: str, status: str, notes: str = ""):
        timestamp = datetime.datetime.now().isoformat()
        # Escape commas in notes/paths
        clean_notes = notes.replace(",", ";").replace("\n", " ")
        clean_path = str(original).replace(",", ";")
        
        row = f"{timestamp},{clean_path},{entity},{subtype},{md5},{status},{clean_notes}\n"
        
        try:
            with open(self.csv_path, "a", encoding="utf-8") as f:
                f.write(row)
        except Exception:
            pass # Never crash logging


import logging
from rich.logging import RichHandler

def setup_forensic_logging(log_dir: str = "logs"):
    """
    Configures the Dual-Channel Logging System:
    1. Console: High-level INFO only (clean).
    2. File: Deep DEBUG logs (system_forensics.log).
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # 1. System Forensics File Handler (Captures EVERYTHING)
    file_handler = logging.FileHandler(Path(log_dir) / "system_forensics.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    file_handler.setFormatter(file_fmt)
    root_logger.addHandler(file_handler)
    
    # 2. Rich Console Handler (Clean UI)
    console_handler = RichHandler(rich_tracebacks=True, markup=True)
    console_handler.setLevel(logging.INFO)
    
    # Filter pypdf noise from console (allow ERRORs only)
    class PypdfConsoleFilter(logging.Filter):
        def filter(self, record):
            if record.name.startswith("pypdf"):
                return record.levelno >= logging.ERROR
            return True
            
    console_handler.addFilter(PypdfConsoleFilter())
    root_logger.addHandler(console_handler)
    
    # 3. Third-party Noise Control
    # pypdf is noisy at DEBUG, silence it slightly in console
    logging.getLogger("pypdf").setLevel(logging.DEBUG) 

