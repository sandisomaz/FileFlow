# Save this as: utils/file_utils.py
import os
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

FileInfo = Dict[str, Any]

def is_ignored(file_path: Path, ignore_rules: Dict[str, Any]) -> bool:
    """Check if a file should be ignored based on rules in the config."""
    name_lower = file_path.name.lower()
    if name_lower in ignore_rules.get('filenames', []):
        return True
    
    if file_path.suffix.lower() in ignore_rules.get('extensions', []):
        return True
    
    for pattern in ignore_rules.get('patterns', []):
        if re.search(pattern, file_path.name, re.IGNORECASE):
            return True
            
    return False

class FileUtils:
    @staticmethod
    def scan_folder(folder_path: str, ignore_rules: Optional[Dict] = None, recursive: bool = True) -> List[FileInfo]:
        """Scans a folder and returns metadata, skipping ignored files."""
        files_data: List[FileInfo] = []
        folder = Path(folder_path)
        rules = ignore_rules or {}
        
        if not folder.is_dir():
            print(f"❌ Error: Folder not found at {folder_path}")
            return files_data

        scan_iterator = folder.rglob('*') if recursive else folder.iterdir()

        for item in scan_iterator:
            if item.is_file() and not is_ignored(item, rules):
                info = FileUtils.get_file_info(item)
                if info:
                    files_data.append(info)
        
        return files_data
    
    @staticmethod
    def get_file_info(file_path: Path) -> Optional[FileInfo]:
        """Extracts metadata from a single file path."""
        try:
            stat = file_path.stat()
            return {
                'path': str(file_path.resolve()),
                'name': file_path.name,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'created': datetime.fromtimestamp(stat.st_ctime),
                'extension': file_path.suffix.lower()
            }
        except (FileNotFoundError, PermissionError) as e:
            print(f"⚠️  Could not read info for {file_path.name}: {e}")
            return None
    
    @staticmethod
    def safe_move(src: str, dst: str) -> None:
        """Moves a file robustly, with a fallback for cross-device moves."""
        src_p = Path(src)
        dst_p = Path(dst)
        
        try:
            shutil.move(str(src_p), str(dst_p))
        except (OSError, shutil.Error):
            try:
                shutil.copy2(str(src_p), str(dst_p))
                src_p.unlink()
            except Exception as e:
                raise e

    @staticmethod
    def get_unique_filename(file_path: str) -> str:
        """Generates a unique filename like 'file_1.txt' if 'file.txt' exists."""
        path = Path(file_path)
        if not path.exists():
            return str(path)
        
        counter = 1
        while True:
            new_name = f"{path.stem}_{counter}{path.suffix}"
            new_path = path.parent / new_name
            if not new_path.exists():
                return str(new_path)
            counter += 1
            
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Formats file size into a human-readable string (KB, MB, GB)."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        size_kb = size_bytes / 1024
        if size_kb < 1024:
            return f"{size_kb:.1f} KB"
        size_mb = size_kb / 1024
        if size_mb < 1024:
            return f"{size_mb:.1f} MB"
        size_gb = size_mb / 1024
        return f"{size_gb:.1f} GB"