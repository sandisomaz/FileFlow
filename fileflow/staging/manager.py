import hashlib
import multiprocessing
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional
from collections import Counter

@dataclass
class StagedFile:
    path: Path
    hash_digest: str
    metadata: dict
    is_duplicate: bool
    size: int = 0
    duplicate_of: Optional[Path] = None

def forensic_worker(path_str):
    """Deep isolation worker with Soft Repair logic."""
    # Windows Fix: Import inside worker to avoid bootstrapping issues
    import pypdf
    
    # helper for safe read
    def try_read(stream):
        try:
            reader = pypdf.PdfReader(stream)
            if len(reader.pages) > 0:
                text = reader.pages[0].extract_text()
                return text if text else ""
            return ""
        except Exception:
            return None

    try:
        # 1. Standard Read
        with open(path_str, 'rb') as f:
            # Header Check
            if f.read(4) != b'%PDF': return None 
            f.seek(0)
            res = try_read(f)
            if res is not None: return res

        # 2. Soft Repair (EOF Fix)
        # Many recovered files are just missing the %%EOF marker
        with open(path_str, 'rb') as f:
            content = f.read()
            if b'%%EOF' not in content[-100:]:
                # Try to emulate a fixed file in memory
                from io import BytesIO
                fixed_stream = BytesIO(content + b'\n%%EOF')
                res = try_read(fixed_stream)
                if res is not None: return res
                
        return None
    except:
        return None

class StagingManager:
    def __init__(self, extractor):
        self.extractor = extractor
        self.staged_files: Dict[str, List[StagedFile]] = {}
        self.all_hashes: Dict[str, List[Path]] = {}

    def stage_file(self, file_path: Path):
        # RECOVERY FIX: Ignore folders that are just numbers (1, 2, 3...)
        parent_name = file_path.parent.name
        if parent_name.isdigit():
            parent_name = "Unclassified_Recovery"

        extracted_text = ""
        meta = {"needs_quarantine": False}
        file_size = 0
        try:
             file_size = file_path.stat().st_size
        except OSError:
             pass

        if file_path.suffix.lower() == '.pdf':
            extracted_text = self._safe_extract(file_path)
            # NOTE: If extracted_text is None, it means PDF read failed.
            # We CONTINUE to extractor.extract_metadata because it now has a fallback scraper!
            if extracted_text is None:
                extracted_text = "" # Pass empty string, but pass file_path below
        
        # Unified Analysis
        # Pass file_path so extractor can try Dirty Scrape if text is empty
        sub_type = self.extractor.classify_sub_type(file_path, extracted_text)
        content_meta = self.extractor.extract_metadata(extracted_text, file_path=file_path)
        
        # If it's still empty and marked as corrupted/unrecoverable
        if not content_meta and not extracted_text:
             self._quarantine(file_path, "Corrupted_and_Unscrapeable", size=file_size)
             return

        
        # Hashing for deduplication (crucial for recovered files)
        f_hash = hashlib.md5(extracted_text.encode() if extracted_text else file_path.name.encode()).hexdigest()
        
        entity = content_meta.get('entity', parent_name)
        
        is_dup = False
        duplicate_of = None
        if f_hash in self.all_hashes:
            is_dup = True
            duplicate_of = self.all_hashes[f_hash][0]
            self.all_hashes[f_hash].append(file_path)
        else:
            self.all_hashes[f_hash] = [file_path]
        
        final_meta = {**content_meta, "sub_type": sub_type, "entity": entity}
        
        staged = StagedFile(
            path=file_path, 
            hash_digest=f_hash, 
            metadata=final_meta, 
            is_duplicate=is_dup,
            size=file_size,
            duplicate_of=duplicate_of
        )
        self.staged_files.setdefault(entity, []).append(staged)

    def _safe_extract(self, path: Path, timeout=2):
        # Windows Multiprocessing Guard
        # We rely on the fact that 'forensic_worker' is top-level importable.
        try:
            with multiprocessing.Pool(1) as pool:
                res = pool.apply_async(forensic_worker, (str(path),))
                try: 
                    return res.get(timeout=timeout)
                except multiprocessing.TimeoutError:
                    return None
                except Exception:
                   return None
        except Exception:
             # Fallback: Try straight read in main process if pool fails (risky but worth it for recovery)
             # return forensic_worker(str(path)) <--- TOO RISKY regarding crashes
             return None

    def _quarantine(self, path: Path, reason: str, size: int = 0):
        staged = StagedFile(
            path=path, 
            hash_digest="CORRUPT", 
            metadata={"entity": "_Quarantine", "sub_type": "Corrupted_File", "needs_quarantine": True, "quarantine_reason": reason}, 
            is_duplicate=False,
            size=size
        )
        self.staged_files.setdefault("_Quarantine", []).append(staged)

    # =================================================================================================
    # PHASE 16: CONTEXT PROPAGATION
    # =================================================================================================
    def resolve_folder_context(self):
        """
        Grouping files by their PARENT FOLDER.
        If a folder contains a 'Strong Entity' (e.g. CANDIDATE_ATTORNEY),
        propagate it to all 'Weak Entity' siblings (e.g. INTERNSHIP_DEMO_SOURCE).
        """
        # 1. Group by Parent Folder
        by_folder: Dict[str, List[StagedFile]] = {}
        all_files = [f for file_list in self.staged_files.values() for f in file_list]
        
        for f in all_files:
            parent = str(f.path.parent)
            by_folder.setdefault(parent, []).append(f)

        # 2. Analyze each folder
        for folder, files in by_folder.items():
            # Find the "Winner" entity for this folder
            votes = Counter()
            for f in files:
                ent = f.metadata.get('entity')
                # Ignore weak entities
                if ent and ent not in ["INTERNSHIP_DEMO_SOURCE", "Unclassified_Recovery", "Unknown", "_Quarantine"]:
                    votes[ent] += 1
            
            if not votes:
                continue # No strong entity found in this folder

            winning_entity = votes.most_common(1)[0][0]
            
            # 3. Propagate to Weak Siblings
            for f in files:
                current_ent = f.metadata.get('entity')
                if current_ent in ["INTERNSHIP_DEMO_SOURCE", "Unclassified_Recovery", "Unknown"]:
                    # MOVE the file internally
                    # Remove from old list
                    if current_ent in self.staged_files and f in self.staged_files[current_ent]:
                        self.staged_files[current_ent].remove(f)
                    
                    # Update Metadata
                    f.metadata['entity'] = winning_entity
                    f.metadata['sub_type'] = f.metadata.get('sub_type', 'Context_Propagated')
                    f.metadata['original_entity'] = current_ent # Traceability
                    
                    # Add to new list
                    self.staged_files.setdefault(winning_entity, []).append(f)

    # =================================================================================================
    # MERGED UTILITY METHODS (Required for main.py)
    # =================================================================================================

    def get_staged_count(self) -> int:
        return sum(len(files) for files in self.staged_files.values())
    
    def get_preview(self) -> Dict[str, List[Dict]]:
        # self._resolve_folder_contexts() # Disabled for forensic mode as we trust content more
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
        
        manifest['_statistics'] = {
            'total_files': self.get_staged_count(),
            'duplicates': sum(1 for files in self.staged_files.values() for f in files if f.is_duplicate)
        }
        
        try:
            with open(output_path, 'w') as f:
                json.dump(manifest, f, indent=4)
        except Exception as e:
            print(f"❌ Failed to write manifest: {e}")
