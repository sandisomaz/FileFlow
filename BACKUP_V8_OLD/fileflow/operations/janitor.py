"""
Janitor V8 - Cleanup and Rollback Operations
"""

import os
import json
import shutil
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional


class PruneExecutor:
    """
    Handles cleanup and rollback operations.
    """
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        
    def get_prune_candidates(self, root_path: Path) -> List[Path]:
        candidates = []
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
            if not dirnames and not filenames:
                candidates.append(Path(dirpath))
        return candidates

    def execute_prune(self, root_path: Path) -> int:
        candidates = self.get_prune_candidates(root_path)
        count = 0
        for folder in candidates:
            if folder == root_path: continue
            try:
                # SAFETY LOCK: Pruning is PERMANENTLY DISABLED
                # if not self.dry_run:
                #     folder.rmdir()
                print(f"[SAFETY] Would prune: {folder}")
                count += 1
            except Exception:
                pass
        return count

    def purge_from_manifest(self, manifest_path: Path) -> Dict[str, any]:
        report = {'deleted': 0, 'failed': 0, 'space_reclaimed_bytes': 0, 'errors': []}
        if not manifest_path.exists():
            report['errors'].append(f"Manifest not found: {manifest_path}")
            return report
            
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
        except Exception as e:
            report['errors'].append(f"Failed to load manifest: {e}")
            return report
            
        for entity, files in manifest.items():
            for f_entry in files:
                source_path = Path(f_entry['original_path'])
                if source_path.exists():
                    try:
                        size = source_path.stat().st_size
                        # SAFETY LOCK: Source deletion is PERMANENTLY DISABLED
                        # if not self.dry_run:
                        #     source_path.unlink()
                        print(f"[SAFETY] Would delete: {source_path}")
                        report['deleted'] += 1
                        report['space_reclaimed_bytes'] += size
                    except Exception as e:
                        report['failed'] += 1
                        report['errors'].append(f"Failed to delete {source_path}: {e}")
        return report

    def rollback_run(self, manifest_path: Path) -> Dict[str, any]:
        """
        Batch rollback - undo entire FileFlow run.
        Optimized to avoid O(N^2) MD5 scanning.
        """
        report = {'restored': 0, 'failed': 0, 'errors': [], 'manifest_path': str(manifest_path)}
        if not manifest_path.exists():
            report['errors'].append(f"Manifest not found: {manifest_path}")
            return report
        
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
        except Exception as e:
            report['errors'].append(f"Failed to load manifest: {e}")
            return report
            
        base_folder = manifest_path.parent
        
        # Optimization: Pre-index all files in the organized folder by MD5
        hash_map = {}
        print("Indexing organized files for fast rollback...")
        for file in base_folder.rglob("*"):
            if file.is_file() and not file.name.endswith('.json'):
                f_hash = self._calculate_md5(file)
                if f_hash:
                    hash_map[f_hash] = file

        for entity, files in manifest.items():
            for file_entry in files:
                original_path = Path(file_entry['original_path'])
                target_hash = file_entry['md5']
                organized_file = hash_map.get(target_hash)
                
                if not organized_file:
                    report['failed'] += 1
                    continue
                    
                if self.dry_run:
                    report['restored'] += 1
                else:
                    try:
                        original_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(organized_file), str(original_path))
                        # Remove from map after moving to prevent re-use
                        del hash_map[target_hash]
                        report['restored'] += 1
                    except Exception as e:
                        report['failed'] += 1
                        report['errors'].append(f"{original_path.name}: {e}")
                        
        return report

    def _calculate_md5(self, path: Path) -> Optional[str]:
        try:
            md5 = hashlib.md5()
            with open(path, 'rb') as f:
                while chunk := f.read(8192):
                    md5.update(chunk)
            return md5.hexdigest()
        except:
            return None
    
    def _find_file_by_hash(self, folder: Path, target_hash: str) -> Optional[Path]:
        if not folder.exists(): return None
        for file in folder.iterdir():
            if file.is_file():
                try:
                    md5 = hashlib.md5()
                    with open(file, 'rb') as f:
                        while chunk := f.read(8192):
                            md5.update(chunk)
                    if md5.hexdigest() == target_hash:
                        return file
                except:
                    continue
        return None
