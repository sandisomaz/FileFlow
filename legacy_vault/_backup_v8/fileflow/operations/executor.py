import hashlib
import shutil
import os
from pathlib import Path
from typing import Optional
from rich import print as rprint

class AtomicExecutor:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

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
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            
            # Verify copy
            if self._verify_copy(src, dst):
                return True
            else:
                rprint(f"Verification failed for {dst}")
                if dst.exists():
                    dst.unlink() # Rollback bad copy
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

    def _verify_copy(self, src: Path, dst: Path) -> bool:
        """
        Check if file size and hash match.
        """
        if src.stat().st_size != dst.stat().st_size:
            return False
            
        # Optional: Full hash check (expensive for big files, maybe skip for now?)
        # For Enterprise reliability, we should do it.
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
