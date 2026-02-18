"""
librarian.py — The Smart Naming & Versioning Engine
FileFlow Cognition V9

The Librarian gives every file a meaningful, consistent name.

V8 behaviour (preserved):
- Version numbering: CV_v1.pdf, CV_v2.pdf
- Collision detection: never overwrites

V9 additions:
- AI-powered rename suggestions based on document content
- Consistent naming conventions across the archive
- Rename preview before execution

Naming convention:
    {Entity}_{SubType}_{Date}_{Version}.{ext}

Examples:
    JUDGES_SECRETARY_Z83_2024-03_v1.pdf
    WERKSMANS_CoverLetter_2024-03_v1.pdf
    FNB_BankStatement_2025-01_v1.pdf
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RenameProposal:
    """A proposed rename for a single file."""
    source: Path
    proposed_name: str
    proposed_path: Path
    method: str             # "ai", "rule", "version_bump"
    confidence: float
    reason: str


class Librarian:
    """
    The sovereign naming engine for FileFlow Cognition.

    Generates consistent, meaningful filenames for archived documents.

    Usage:
        librarian = Librarian(bridge=bridge)
        proposal = librarian.propose_name(file_path, metadata, destination_dir)
        executor.safe_copy(proposal.source, proposal.proposed_path)
    """

    def __init__(self, bridge=None):
        """
        Args:
            bridge: Optional Bridge for AI-powered rename suggestions.
                    Falls back to rule-based naming if None or offline.
        """
        self.bridge = bridge

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def propose_name(
        self,
        file_path: Path,
        metadata: dict,
        destination_dir: Path,
    ) -> RenameProposal:
        """
        Proposes a clean, consistent name for a file.

        Priority:
        1. AI suggestion (if bridge is available and content is rich)
        2. Rule-based name from metadata (entity + sub_type + date)
        3. Version bump of existing name (V8 fallback)

        Args:
            file_path:       Source file path
            metadata:        Dict with entity, sub_type, ai_category, etc.
            destination_dir: Where the file will live (for collision checking)

        Returns:
            RenameProposal with the proposed name and path
        """
        entity = metadata.get("entity", "").strip()
        sub_type = metadata.get("sub_type", "").strip()
        ai_category = metadata.get("ai_category", "")
        ext = file_path.suffix.lower()

        # --- Method 1: AI suggestion ---
        if self.bridge and self.bridge.is_healthy() and entity and sub_type:
            ai_name = self._ask_ai_for_name(file_path, metadata)
            if ai_name:
                safe_name = self._sanitise(ai_name) + ext
                final_path = self._resolve_collision(destination_dir, safe_name)
                return RenameProposal(
                    source=file_path,
                    proposed_name=final_path.name,
                    proposed_path=final_path,
                    method="ai",
                    confidence=0.85,
                    reason=f"AI-generated name from content analysis",
                )

        # --- Method 2: Rule-based from metadata ---
        if entity and sub_type:
            rule_name = self._rule_name(entity, sub_type, ext)
            final_path = self._resolve_collision(destination_dir, rule_name)
            return RenameProposal(
                source=file_path,
                proposed_name=final_path.name,
                proposed_path=final_path,
                method="rule",
                confidence=0.75,
                reason=f"Rule-based: entity='{entity}', sub_type='{sub_type}'",
            )

        # --- Method 3: Version bump (V8 fallback) ---
        versioned_name = self._version_bump(file_path.name, destination_dir)
        final_path = destination_dir / versioned_name
        return RenameProposal(
            source=file_path,
            proposed_name=versioned_name,
            proposed_path=final_path,
            method="version_bump",
            confidence=0.5,
            reason="Version bump: insufficient metadata for smart naming",
        )

    def propose_batch(
        self,
        files: list,
        destination_dir: Path,
    ) -> list:
        """
        Proposes names for a batch of files.

        Args:
            files: List of dicts with keys: file_path (Path), metadata (dict)
            destination_dir: Target directory

        Returns:
            List of RenameProposal
        """
        proposals = []
        for f in files:
            proposal = self.propose_name(
                file_path=f["file_path"],
                metadata=f.get("metadata", {}),
                destination_dir=destination_dir,
            )
            proposals.append(proposal)
        return proposals

    # ------------------------------------------------------------------
    # Naming strategies
    # ------------------------------------------------------------------

    def _rule_name(self, entity: str, sub_type: str, ext: str) -> str:
        """
        Generates a clean name from entity + sub_type.

        Format: {Entity}_{SubType}{ext}
        Example: JUDGES_SECRETARY_Z83.pdf
        """
        clean_entity = self._sanitise(entity)
        clean_sub = self._sanitise(sub_type)
        return f"{clean_entity}_{clean_sub}{ext}"

    def _ask_ai_for_name(self, file_path: Path, metadata: dict) -> Optional[str]:
        """
        Asks the SLM to suggest a clean filename based on document metadata.
        Returns just the stem (no extension), or None on failure.
        """
        entity = metadata.get("entity", "")
        sub_type = metadata.get("sub_type", "")
        summary = metadata.get("ai_summary", "")
        category = metadata.get("ai_category", "")

        prompt = (
            f"You are a file naming assistant. Generate a clean, professional filename stem "
            f"(no extension, no spaces, use underscores) for this document.\n\n"
            f"Document info:\n"
            f"  Current name: {file_path.name}\n"
            f"  Category: {category}\n"
            f"  Entity: {entity}\n"
            f"  Type: {sub_type}\n"
            f"  Summary: {summary}\n\n"
            f"Rules:\n"
            f"  - Use underscores, not spaces or hyphens\n"
            f"  - Max 60 characters\n"
            f"  - Be specific: include entity name and document type\n"
            f"  - No dates unless clearly present in summary\n\n"
            f"Respond with ONLY the filename stem. Nothing else."
        )

        raw = self.bridge.generate(prompt)
        if not raw:
            return None

        # Clean up: take first line, strip quotes and spaces
        stem = raw.strip().split("\n")[0].strip().strip('"').strip("'")

        # Validate: must look like a filename stem
        if not stem or len(stem) > 80 or " " in stem:
            return None

        return stem

    # ------------------------------------------------------------------
    # Versioning (V8 preserved)
    # ------------------------------------------------------------------

    @staticmethod
    def _version_bump(filename: str, destination_dir: Path) -> str:
        """
        V8 versioning logic: appends _v1, _v2, etc. to avoid collisions.

        CV.pdf → CV_v1.pdf → CV_v2.pdf
        """
        stem = Path(filename).stem
        ext = Path(filename).suffix

        # Strip existing version suffix if present
        base_stem = re.sub(r"_v\d+$", "", stem)

        version = 1
        candidate = f"{base_stem}_v{version}{ext}"
        while (destination_dir / candidate).exists():
            version += 1
            candidate = f"{base_stem}_v{version}{ext}"

        return candidate

    @staticmethod
    def _resolve_collision(directory: Path, filename: str) -> Path:
        """
        Ensures the proposed path doesn't already exist.
        Appends _v1, _v2, etc. if needed.
        """
        candidate = directory / filename
        if not candidate.exists():
            return candidate

        stem = Path(filename).stem
        ext = Path(filename).suffix
        base_stem = re.sub(r"_v\d+$", "", stem)

        version = 2
        while True:
            new_name = f"{base_stem}_v{version}{ext}"
            candidate = directory / new_name
            if not candidate.exists():
                return candidate
            version += 1

    @staticmethod
    def _sanitise(name: str) -> str:
        """
        Makes a string safe for use as a filename component.
        Strips special characters, replaces spaces with underscores.
        """
        # Replace spaces and hyphens with underscores
        clean = re.sub(r"[\s\-]+", "_", name)
        # Remove characters that aren't alphanumeric or underscore
        clean = re.sub(r"[^\w]", "", clean)
        # Collapse multiple underscores
        clean = re.sub(r"_+", "_", clean)
        # Strip leading/trailing underscores
        clean = clean.strip("_")
        # Truncate
        return clean[:50]
