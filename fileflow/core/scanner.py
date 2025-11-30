import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from fileflow.config import Config
from fileflow.core.extractor import UnifiedExtractor

class Scanner:
    @staticmethod
    def is_wanted_file(filename: str) -> bool:
        name_lower = filename.lower()
        for junk in Config.KEYWORDS_NEGATIVE:
            if junk in name_lower: return False
        return True 

    @staticmethod
    def scan_directory(
        root_path: Path, 
        recursive: bool = True,
        callback=None
    ) -> Dict[str, List[Dict]]:
        """
        Scans directory and returns results grouped by relative folder path.
        callback(str): Optional function to report progress (current folder name).
        """
        results = {}
        
        # Walk
        walker = os.walk(root_path, topdown=True) if recursive else [(str(root_path), [], [f.name for f in root_path.iterdir() if f.is_file()])]
        
        for root, dirs, files in walker:
            # Filter dirs in-place
            dirs[:] = [d for d in dirs if d not in Config.IGNORED_SYSTEM_DIRS and not d.startswith('.')]
            
            if callback:
                callback(Path(root).name)

            for filename in files:
                file_path = Path(root) / filename
                
                if file_path.suffix.lower() not in Config.TARGET_EXTENSIONS: continue
                if not Scanner.is_wanted_file(filename): continue

                try:
                    stat = file_path.stat()
                    phys_date = datetime.fromtimestamp(stat.st_mtime)
                    
                    # Extraction
                    meta = UnifiedExtractor.get_metadata(file_path)
                    final_date = meta['final_date'] if meta['final_date'] else phys_date
                    
                    # Grouping Key (Relative Path)
                    try:
                        rel_path = str(Path(root).relative_to(root_path))
                    except ValueError:
                        rel_path = str(Path(root))

                    if rel_path not in results: results[rel_path] = []
                    
                    results[rel_path].append({
                        'path': str(file_path),
                        'name': filename,
                        'date': final_date,
                        'metadata': meta,
                        'size': stat.st_size
                    })
                except Exception as e:
                    # print(f"Error scanning {filename}: {e}")
                    pass
                    
        return results
