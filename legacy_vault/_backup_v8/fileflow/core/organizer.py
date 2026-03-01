import shutil
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

class MoveLogger:
    LOG_FILE = Path.home() / '.fileflow_moves.jsonl'
    
    @staticmethod
    def log_move(src: str, dst: str, position: str, applicant: str) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": src,
            "destination": dst,
            "position": position,
            "applicant": applicant
        }
        try:
            with open(MoveLogger.LOG_FILE, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            pass
    
    @staticmethod
    def undo_last_move() -> Tuple[bool, str]:
        if not MoveLogger.LOG_FILE.exists():
            return False, "No log file found."
        
        lines = []
        with open(MoveLogger.LOG_FILE, 'r') as f:
            lines = f.readlines()
            
        if not lines:
            return False, "Log file is empty."
            
        last_line = lines[-1]
        try:
            move = json.loads(last_line)
            dst = Path(move['destination'])
            src = Path(move['source'])
            
            if not dst.exists():
                return False, f"Destination file missing: {dst}"
                
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            
            # Remove last line
            with open(MoveLogger.LOG_FILE, 'w') as f:
                f.writelines(lines[:-1])
                
            return True, f"Restored {src.name}"
        except Exception as e:
            return False, str(e)

class Organizer:
    @staticmethod
    def generate_new_filename(
        applicant: str,
        position: str,
        date_obj: datetime,
        existing_count: int = 0
    ) -> str:
        date_str = date_obj.strftime("%Y%m%d")
        version = existing_count + 1
        return f"{applicant}_{position}_{date_str}_v{version}.pdf"

    @staticmethod
    def organize_file(
        file_info: Dict[str, Any], 
        dest_base: Path, 
        dry_run: bool = False
    ) -> Tuple[bool, str]:
        """
        Moves a single file to the organized destination.
        Returns (success, message/new_path).
        """
        meta = file_info['metadata']
        if not meta:
            return False, "No metadata extracted"

        applicant = meta.get('applicant', 'Unknown')
        position = meta.get('position', 'General')
        date_obj = file_info['date']
        
        # Clean strings
        position = position.replace(' ', '_').replace('/', '-')
        applicant = applicant.replace(' ', '_')

        dest_folder = dest_base / position
        
        if not dry_run:
            dest_folder.mkdir(parents=True, exist_ok=True)

        # Versioning
        date_str = date_obj.strftime("%Y%m%d")
        pattern = f"{applicant}_{position}_{date_str}_v*.pdf"
        
        # Check existing in destination (real check)
        existing = list(dest_folder.glob(pattern)) if dest_folder.exists() else []
        version = len(existing)
        
        new_name = Organizer.generate_new_filename(applicant, position, date_obj, version)
        dest_path = dest_folder / new_name
        
        if dry_run:
            return True, str(dest_path)
            
        try:
            shutil.copy2(file_info['path'], dest_path) # Copy first
            MoveLogger.log_move(file_info['path'], str(dest_path), position, applicant)
            return True, str(dest_path)
        except Exception as e:
            return False, str(e)
