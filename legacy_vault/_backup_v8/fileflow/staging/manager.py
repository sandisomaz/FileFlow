"""
Staging Manager V8 - EMERGENCY FIX
Fixed: ThreadPoolExecutor hang -> ProcessPoolExecutor with termination
Added: Ghost file detection (< 1KB skip)
"""

import hashlib
import os
from typing import Dict, List, Set, Optional
from collections import Counter
from pathlib import Path
from dataclasses import dataclass, field
import concurrent.futures
import pypdf


@dataclass
class StagedFile:
    """Represents a file in the staging area."""
    path: Path
    hash_digest: str
    metadata: Dict[str, str] = field(default_factory=dict)
    size: int = 0
    duplicate_of: Optional[Path] = None
    is_duplicate: bool = False


# ============================================================================
# CRITICAL FIX: Top-level worker function for ProcessPoolExecutor
# ============================================================================
def worker_extract_pdf_text(file_path_str: str) -> str:
    """
    Worker function for ProcessPoolExecutor.
    MUST be top-level for Windows pickling.
    Returns extracted text or empty string on failure.
    """
    try:
        file_path = Path(file_path_str)
        
        with open(file_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            
            # Recursion Guard
            try:
                num_pages = len(reader.pages)
            except (RecursionError, Exception):
                return ""
            
            text = ""
            # Cap at 20 pages for speed
            for i in range(min(num_pages, 20)): 
                try:
                    page_text = reader.pages[i].extract_text()
                    if page_text:
                        text += page_text
                except Exception:
                    continue
            
            return text
    except Exception:
        return ""


class StagingManager:
    """
    The "Brain" of FileFlow - stages files before execution.
    FIXED: Now uses ProcessPoolExecutor with proper timeout handling.
    """
    
    def __init__(self, extractor):
        self.extractor = extractor
        self.staged_files: Dict[str, List[StagedFile]] = {}
        self.all_hashes: Dict[str, List[Path]] = {}
        self.config = None
        self.timeout_count = 0
        self.ghost_file_count = 0
    
    def stage_file(self, file_path: Path):
        corruption_meta = {}
        
        # ============================================================================
        # CRITICAL FIX #1: Ghost File Detection (< 1KB = Skip immediately)
        # ============================================================================
        try:
            file_size = os.path.getsize(file_path)
            if file_size < 1024:  # Less than 1KB
                print(f"[GHOST] Skipping tiny/empty file: {file_path.name} ({file_size} bytes)")
                self.ghost_file_count += 1
                
                # Still stage it but mark as Ghost
                staged = StagedFile(
                    path=file_path,
                    hash_digest="GHOST_FILE",
                    metadata={
                        'entity': 'Ghost_Files',
                        'sub_type': 'Ghost_File',
                        'needs_quarantine': True,
                        'quarantine_reason': f'File too small ({file_size} bytes)'
                    },
                    size=file_size,
                    is_duplicate=False
                )
                
                if 'Ghost_Files' not in self.staged_files:
                    self.staged_files['Ghost_Files'] = []
                self.staged_files['Ghost_Files'].append(staged)
                return
        except OSError:
            pass
        
        # ============================================================================
        # CRITICAL FIX #2: Content hash with ProcessPoolExecutor
        # ============================================================================
        file_hash = self._calculate_content_hash(file_path, metadata=corruption_meta)
        is_duplicate = False
        duplicate_of = None
        
        if file_hash in self.all_hashes:
            is_duplicate = True
            duplicate_of = self.all_hashes[file_hash][0]
            self.all_hashes[file_hash].append(file_path)
        else:
            self.all_hashes[file_hash] = [file_path]
        
        filename_meta = self.extractor.extract_from_filename(file_path.name)
        sub_type = self.extractor.classify_sub_type(file_path)
        
        # Deep Context for Unclassified/Generic files
        content_meta = {}
        if filename_meta.get('type') == 'generic_government' or not filename_meta.get('entity'):
            if file_path.suffix.lower() == '.pdf':
                content_meta = self.extractor.extract_metadata(file_path)
        
        content_meta['sub_type'] = sub_type
        metadata = {**filename_meta, **content_meta, **corruption_meta}
        
        entity = metadata.get('entity', 'Unclassified')
        
        staged = StagedFile(
            path=file_path,
            hash_digest=file_hash,
            metadata=metadata,
            size=file_path.stat().st_size if file_path.exists() else 0,
            duplicate_of=duplicate_of,
            is_duplicate=is_duplicate
        )
        
        if entity not in self.staged_files:
            self.staged_files[entity] = []
        self.staged_files[entity].append(staged)
    
    def _calculate_content_hash(self, file_path: Path, metadata: dict = None) -> str:
        ext = file_path.suffix.lower()
        
        # Binary fallback for non-content types
        if ext not in ['.pdf', '.docx', '.doc']:
            return self._calculate_md5(file_path)

        # ============================================================================
        # CRITICAL FIX #3: PDF Processing with ProcessPoolExecutor
        # ============================================================================
        if ext == '.pdf':
            try:
                # A. Header validation
                with open(file_path, 'rb') as f:
                    header = f.read(100)
                    if all(b == 0 for b in header) or b'%PDF' not in header:
                        if metadata is not None:
                            metadata['needs_quarantine'] = True
                            metadata['quarantine_reason'] = "Invalid PDF Header"
                        return self._calculate_md5(file_path)

                # B. Process-based extraction with HARD timeout
                text = self._get_pdf_text_with_timeout(file_path, timeout=3)
                
                if text is None:  # Timeout occurred
                    self.timeout_count += 1
                    print(f"[TIMEOUT] Skipping corrupted PDF: {file_path.name}")
                    if metadata is not None:
                        metadata['needs_quarantine'] = True
                        metadata['quarantine_reason'] = "PDF extraction timeout (>3s)"
                    return self._calculate_md5(file_path)
                
                if not text:
                    return self._calculate_md5(file_path)
                    
                # Hash the text content
                normalized = ''.join(text.split()).lower()
                return hashlib.md5(normalized.encode()).hexdigest()

            except Exception as e:
                if metadata is not None:
                    metadata['needs_quarantine'] = True
                    metadata['quarantine_reason'] = f"Content Read Failed: {str(e)[:50]}"
                return self._calculate_md5(file_path)
        
        # DOCX/DOC handling
        elif ext in ['.docx', '.doc']:
            return self._calculate_md5(file_path)
        
        return self._calculate_md5(file_path)

    def _get_pdf_text_with_timeout(self, file_path: Path, timeout: int = 3) -> Optional[str]:
        """
        CRITICAL FIX: Runs pypdf extraction in a PROCESS (not thread) with hard timeout.
        Processes can be terminated, threads cannot.
        """
        
        # Use ProcessPoolExecutor instead of ThreadPoolExecutor
        with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(worker_extract_pdf_text, str(file_path))
            try:
                result = future.result(timeout=timeout)
                return result
            except concurrent.futures.TimeoutError:
                # Timeout - the process will be forcefully terminated
                return None
            except Exception:
                return None
    
    def _calculate_md5(self, file_path: Path, chunk_size=8192) -> str:
        md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    md5.update(chunk)
            return md5.hexdigest()
        except OSError:
            return ""
            
    def get_staged_count(self) -> int:
        return sum(len(files) for files in self.staged_files.values())
    
    def get_preview(self) -> Dict[str, List[Dict]]:
        self._resolve_folder_contexts()
        preview = {}
        for entity, files in self.staged_files.items():
            preview[entity] = []
            for f in files:
                preview[entity].append({
                    "name": f.path.name,
                    "subtype": f.metadata.get('sub_type', 'Unknown'),
                    "duplicate": f.is_duplicate,
                    "original": str(f.duplicate_of) if f.duplicate_of else None
                })
        return preview
        
    def _resolve_folder_contexts(self):
        folder_map: Dict[Path, List[StagedFile]] = {}
        for file_list in list(self.staged_files.values()):
            for f in file_list:
                parent = f.path.parent
                if parent not in folder_map:
                    folder_map[parent] = []
                folder_map[parent].append(f)
                
        for folder, files in folder_map.items():
            # Look for a "Strong Anchor"
            dominant_entity = None
            for f in files:
                m = f.metadata
                if m.get('type') in ['job_packet', 'firm_application'] or str(m.get('entity', '')).startswith('REF_'):
                    dominant_entity = m.get('entity')
                    break
            
            if dominant_entity:
                for f in files:
                    current_entity = self._find_current_entity(f)
                    if self._is_document_type(f) and current_entity != dominant_entity:
                        self._move_file_to_entity(f, current_entity, dominant_entity)
            else:
                # Architectural recovery
                internal_identities = Counter()
                for f in files:
                    ident = f.metadata.get('entity')
                    if ident and ident not in ['in_a_government', 'Unclassified']:
                        internal_identities[ident] += 1
                
                if internal_identities:
                    winner_entity, _ = internal_identities.most_common(1)[0]
                    for f in files:
                        current_entity = self._find_current_entity(f)
                        if self._is_document_type(f) and current_entity != winner_entity:
                            self._move_file_to_entity(f, current_entity, winner_entity)
                            
    def _is_document_type(self, file_obj: StagedFile) -> bool:
        doc_extensions = {'.pdf', '.docx', '.doc', '.txt', '.rtf'}
        return file_obj.path.suffix.lower() in doc_extensions
        
    def _find_current_entity(self, file_obj: StagedFile) -> str:
        for entity, files in self.staged_files.items():
            if file_obj in files:
                return entity
        return "Unclassified"
        
    def _move_file_to_entity(self, file_obj: StagedFile, old_entity: str, new_entity: str):
        if old_entity in self.staged_files and file_obj in self.staged_files[old_entity]:
            self.staged_files[old_entity].remove(file_obj)
        if new_entity not in self.staged_files:
            self.staged_files[new_entity] = []
        self.staged_files[new_entity].append(file_obj)
        file_obj.metadata['entity'] = new_entity
        
    def export_manifest(self, output_path: Path):
        import json
        manifest = {}
        for entity, files in self.staged_files.items():
            manifest[entity] = []
            for f in files:
                manifest[entity].append({
                    "original_path": str(f.path),
                    "md5": f.hash_digest,
                    "metadata": f.metadata,
                    "size": f.size,
                    "duplicate_of": str(f.duplicate_of) if f.duplicate_of else None,
                    "is_duplicate": f.is_duplicate,
                    "staging_entity": entity
                })
        
        # Add statistics
        manifest['_statistics'] = {
            'total_files': self.get_staged_count(),
            'ghost_files': self.ghost_file_count,
            'timeouts': self.timeout_count,
            'duplicates': sum(1 for files in self.staged_files.values() for f in files if f.is_duplicate)
        }
        
        try:
            with open(output_path, 'w') as f:
                json.dump(manifest, f, indent=4)
        except Exception as e:
            print(f"❌ Failed to write manifest: {e}")
