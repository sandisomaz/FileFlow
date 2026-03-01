import os
from pathlib import Path
from typing import List, Dict, Generator, Set
from .config import ConfigLoader

class DeepScanner:
    """
    V8 Deep Scanner
    Recursively discovers files while respecting ignore rules and depth limits.
    """
    def __init__(self, config: ConfigLoader, ignore_paths: List[Path] = None):
        self.config = config
        self.ignore_rules = config.get_ignore_rules()
        self.allowed_extensions = config.scanning.target_extensions
        self.max_depth = config.scanning.max_depth
        self.ignore_paths = [p.resolve() for p in (ignore_paths or [])]
        
        # Build set of ignored directory names from config
        self.ignored_dir_names = config.scanning.ignored_dirs

    def scan(self, root_path: str) -> Generator[Path, None, None]:
        """
        Recursively yields file paths that match allowed extensions.
        """
        root = Path(root_path)
        if not root.exists():
            return

        # Stack-based iteration to control depth
        stack = [(root, 0)]
        visited_dirs = set()

        while stack:
            current_dir, depth = stack.pop()
            
            if depth > self.max_depth:
                continue
                
            try:
                real_path = current_dir.resolve()
                if real_path in visited_dirs:
                    continue
                visited_dirs.add(real_path)
            except Exception:
                continue

            try:
                for item in current_dir.iterdir():
                    try:
                        if item.is_dir():
                            if self._should_ignore(item, root):
                                continue
                            stack.append((item, depth + 1))
                        
                        elif item.is_file():
                            if self._should_ignore(item, root):
                                continue
                            
                            if item.suffix.lower() in self.allowed_extensions:
                                yield item
                    except PermissionError:
                        continue
            except PermissionError:
                 continue

    def _should_ignore(self, path: Path, root: Path = None) -> bool:
        """
        V8 Ignore Logic:
        1. Explicitly ignored directory names from settings.yaml
        2. Configured ignore rules (filenames/extensions/patterns)
        3. Protection against scanning specific ignore paths (like current output)
        """
        name = path.name.lower()
        path_str = str(path)
        resolved_path = path.resolve()

        # 1. Protection against infinite loops (Ignore specific paths)
        if self.ignore_paths:
            for ip in self.ignore_paths:
                if ip == resolved_path or ip in resolved_path.parents:
                    # BUT ALLOW if it is the root being scanned (for Vacuum operations)
                    if root and resolved_path == root.resolve():
                        continue
                    return True

        # 2. Check explicitly ignored directory names
        if path.is_dir() and name in self.ignored_dir_names:
            return True

        # 3. Check legacy ignore rules (for patterns and specific filenames)
        if name in self.ignore_rules.get("filenames", []):
            return True
        if path.suffix.lower() in self.ignore_rules.get("extensions", []):
            return True
            
        # Check patterns
        for pattern in self.ignore_rules.get("patterns", []):
            if pattern == "~$" and name.startswith("~$"):
                return True
            if pattern == r"^\." and name.startswith("."):
                return True
                
        return False
