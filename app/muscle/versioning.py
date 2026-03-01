"""
FileFlow Versioning Engine V8
Generates chronologically accurate, semantically rich filenames.
"""

import re
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from app.memory.abbreviations import abbreviate_entity


class Versioning:
    """
    Filename generator with strict chronological accuracy.
    Format: {Entity}_{SubType}_{FileModDate}_v{Index}{Ext}
    """
    
    @staticmethod
    def generate_name(
        entity: str,
        original_path: Path,
        index: int,
        metadata: Dict[str, Any] = None,
        is_duplicate: bool = False,
        duplicate_hash: str = ""
    ) -> str:
        if metadata is None:
            metadata = {}
        
        ext = original_path.suffix
        sub_type = metadata.get('sub_type', 'Document')
        
        # Step 1: Abbreviate entity name
        safe_entity = abbreviate_entity(entity.replace(" ", "_"))
        
        # Step 2: Extract REAL file date
        date_str = Versioning._extract_file_date(original_path)
        
        # Step 3: Construct base name
        base_name = f"{safe_entity}_{sub_type}_{date_str}_v{index}"
        
        # Step 4: Enforce length limit
        MAX_FILENAME = 200
        if len(base_name) > MAX_FILENAME:
            overflow = len(base_name) - MAX_FILENAME
            safe_entity = safe_entity[:max(10, len(safe_entity) - overflow)]
            base_name = f"{safe_entity}_{sub_type}_{date_str}_v{index}"
        
        # Step 5: Handle duplicates
        if is_duplicate:
            short_hash = duplicate_hash[:8] if duplicate_hash else "UNKNOWN"
            return f"{base_name}_DUP_{short_hash}{ext}"
        
        return f"{base_name}{ext}"
    
    @staticmethod
    def _extract_file_date(file_path: Path) -> str:
        try:
            mtime = file_path.stat().st_mtime
            date_str = datetime.fromtimestamp(mtime).strftime("%Y%m%d")
            return date_str
        except (OSError, FileNotFoundError):
            pass
        
        filename_date = re.search(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', file_path.name)
        if filename_date:
            return filename_date.group(0)
            
        alt_date = re.search(r'(20\d{2})[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])', file_path.name)
        if alt_date:
            return alt_date.group(0).replace('-', '').replace('_', '')
            
        return "UNKNOWN_DATE"
    
    @staticmethod
    def parse_filename(filename: str) -> Dict[str, Any]:
        pattern = r'^(.+?)_([A-Za-z]+)_(\d{8})_v(\d+)(?:_DUP_([a-f0-9]{8}))?(\.\w+)$'
        match = re.match(pattern, filename)
        if not match:
            return {'error': 'Invalid filename format'}
        return {
            'entity': match.group(1),
            'subtype': match.group(2),
            'date': match.group(3),
            'version': int(match.group(4)),
            'duplicate_hash': match.group(5),
            'ext': match.group(6),
            'is_duplicate': match.group(5) is not None
        }
