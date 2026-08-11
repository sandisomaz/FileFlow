"""
shadow_mapper.py — The Shadow Mapper (Module 4)
FileFlow X (V10)

Creates zero-byte, risk-free previews of organized file structures using Hard-links.
The original files remain completely untouched until the user explicitly commits a consolidation.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class ShadowMapper:
    """
    Creates virtual directory structures using hard links.
    """

    def __init__(self, preview_root: Path):
        self.preview_root = Path(preview_root)

    def create_preview(self, plan: Dict[str, str]) -> Path:
        """
        Takes an execution plan mapping {source_file_path: target_relative_path}
        and creates a hard-linked preview structure.
        
        Args:
            plan: Dict mapping absolute source paths to relative destination paths.
                  e.g., {"C:/Users/<you>/Downloads/cv.pdf": "Resumes/cv.pdf"}
                  
        Returns:
            The Path to the preview root directory.
        """
        # Ensure root exists and is clean-ish
        self.preview_root.mkdir(parents=True, exist_ok=True)
        
        preview_dir = self.preview_root / "FileFlow_Preview"
        
        # If a previous preview exists, we could clean it up, but for safety in V10,
        # we append a unique ID or just clear the directory safely.
        # For this prototype, we'll try to use a fresh preview folder.
        import uuid
        run_id = str(uuid.uuid4())[:8]
        preview_run_dir = preview_dir / f"Preview_{run_id}"
        preview_run_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        error_count = 0
        
        logger.info(f"[ShadowMapper] Generating shadow preview at {preview_run_dir}")
        
        for source_str, target_rel in plan.items():
            source_path = Path(source_str)
            if not source_path.exists() or not source_path.is_file():
                logger.warning(f"[ShadowMapper] Source file missing: {source_path}")
                error_count += 1
                continue
                
            target_path = preview_run_dir / target_rel
            
            # Create parent directories for the target
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                # The Wow Factor: Zero-byte instant copy via hard links
                # If they are on different drives, this will throw an OSError (Cross-device link).
                # We catch that and fallback to a symlink or standard copy if absolutely necessary,
                # but for a local desktop organizing task, hard links are the gold standard.
                os.link(source_path, target_path)
                success_count += 1
            except OSError as e:
                # Fallback to symlink if hard link fails (e.g., cross-device)
                try:
                    os.symlink(source_path, target_path)
                    logger.debug(f"[ShadowMapper] Fallback to symlink for {target_path}")
                    success_count += 1
                except OSError as sym_e:
                    if getattr(sym_e, 'winerror', None) == 1314:
                        error_msg = (
                            "[ShadowMapper] Permission denied to create symlink. "
                            "On Windows, you must enable 'Developer Mode' in Settings "
                            "or run FileFlow as Administrator to use the Shadow Mapper fallback."
                        )
                        logger.error(error_msg)
                    else:
                        logger.error(f"[ShadowMapper] Link failed for {source_path}: {e} -> {sym_e}")
                    error_count += 1
                except Exception as sym_e:
                    logger.error(f"[ShadowMapper] Link failed for {source_path}: {e} -> {sym_e}")
                    error_count += 1
                    
        logger.info(f"[ShadowMapper] Preview generated. Success: {success_count}, Errors: {error_count}")
        return preview_run_dir

    def cleanup_preview(self, preview_run_dir: Path):
        """
        Removes the preview directory. Since these are hard links or symlinks,
        the underlying data is safe. Only the links are deleted.
        """
        if not preview_run_dir.exists():
            return
            
        import shutil
        try:
            shutil.rmtree(preview_run_dir)
            logger.info(f"[ShadowMapper] Cleaned up preview at {preview_run_dir}")
        except Exception as e:
            logger.error(f"[ShadowMapper] Cleanup failed: {e}")