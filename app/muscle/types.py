from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class StagedFile:
    path: Path
    hash_digest: str
    metadata: dict
    is_duplicate: bool
    size: int = 0
    duplicate_of: Optional[Path] = None
