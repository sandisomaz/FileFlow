"""
unpacker.py — The Folder Flattener
FileFlow Cognition V9

Detects and resolves deeply nested folder structures by surfacing files
to a sensible depth. Handles the common "Downloads chaos" pattern:

    Downloads/
      2024/
        January/
          Applications/
            Job1/
              CV.pdf          ← 4 levels deep
              Z83.pdf

After unpacking:
    Staging/
      CV.pdf
      Z83.pdf

The Unpacker is non-destructive: it only proposes moves, never executes
them directly. The AtomicExecutor handles the actual file operations.

Rules:
- Only flattens if depth > max_depth (default: 2)
- Preserves filename uniqueness (adds parent folder prefix if collision)
- Skips system folders (.git, __pycache__, node_modules, etc.)
- Dry-run safe: reports what it would do without touching anything
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# Folders that should never be touched
SYSTEM_FOLDERS: Set[str] = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules",
    ".venv", "venv", "env", ".env", ".idea", ".vscode",
    "Thumbs.db", "$RECYCLE.BIN", "System Volume Information",
}

DEFAULT_MAX_DEPTH = 2


@dataclass
class FlattenProposal:
    """A proposed move to flatten a deeply nested file."""
    source: Path            # Current location (deep)
    destination: Path       # Proposed location (flat)
    depth: int              # How many levels deep the source was
    collision_resolved: bool  # Was a name collision resolved?
    reason: str             # Human-readable explanation


@dataclass
class UnpackReport:
    """Summary of what the Unpacker found and proposes."""
    scanned_dirs: int
    deep_files: int             # Files found below max_depth
    proposals: List[FlattenProposal]
    skipped_system: int
    already_flat: int           # Files already at acceptable depth


class Unpacker:
    """
    The sovereign folder flattener for FileFlow Cognition.

    Finds files buried in deep folder hierarchies and proposes
    moving them to a flat staging area for processing.

    Usage:
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source_path, staging_path)
        for proposal in report.proposals:
            executor.safe_copy(proposal.source, proposal.destination)
    """

    def __init__(self, max_depth: int = DEFAULT_MAX_DEPTH):
        """
        Args:
            max_depth: Files deeper than this level will be proposed for flattening.
                       Depth 0 = root, depth 1 = one subfolder, etc.
        """
        self.max_depth = max_depth

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, source: Path, staging: Path) -> UnpackReport:
        """
        Scans source for deeply nested files and proposes flattening moves.

        Args:
            source:  The root folder to scan
            staging: Where flattened files should be moved to

        Returns:
            UnpackReport with all proposals
        """
        proposals: List[FlattenProposal] = []
        scanned_dirs = 0
        skipped_system = 0
        already_flat = 0

        for item in self._walk(source):
            if item.is_dir():
                scanned_dirs += 1
                continue

            if not item.is_file():
                continue

            # Calculate depth relative to source root
            try:
                rel = item.relative_to(source)
            except ValueError:
                continue

            depth = len(rel.parts) - 1  # -1 because the file itself is a part

            if depth <= self.max_depth:
                already_flat += 1
                continue

            # This file is too deep — propose flattening it
            destination = self._resolve_destination(item, staging, proposals)
            collision_resolved = destination.name != item.name

            proposals.append(FlattenProposal(
                source=item,
                destination=destination,
                depth=depth,
                collision_resolved=collision_resolved,
                reason=f"Depth {depth} exceeds max {self.max_depth}. "
                       f"Parent chain: {' → '.join(rel.parts[:-1])}",
            ))

        logger.debug(
            f"[Unpacker] Scanned {source.name}: "
            f"{len(proposals)} to flatten, {already_flat} already flat"
        )

        return UnpackReport(
            scanned_dirs=scanned_dirs,
            deep_files=len(proposals),
            proposals=proposals,
            skipped_system=skipped_system,
            already_flat=already_flat,
        )

    def summarise(self, report: UnpackReport) -> str:
        """Returns a human-readable summary of the unpack report."""
        if not report.proposals:
            return (
                f"✅ No deep nesting found. "
                f"All {report.already_flat} files are within {self.max_depth} levels."
            )

        lines = [
            f"📦 Unpacker Report",
            f"  Deep files to flatten: {report.deep_files}",
            f"  Already flat:          {report.already_flat}",
            f"  Name collisions fixed: {sum(1 for p in report.proposals if p.collision_resolved)}",
            f"",
            f"  Proposals (first 10):",
        ]
        for p in report.proposals[:10]:
            arrow = "→"
            lines.append(f"    [{p.depth}] {p.source.name} {arrow} {p.destination.name}")
            if p.collision_resolved:
                lines.append(f"         ⚠ Name collision resolved")

        if len(report.proposals) > 10:
            lines.append(f"    ... and {len(report.proposals) - 10} more")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk(self, root: Path):
        """
        Recursively yields all items under root, skipping system folders.
        """
        try:
            for item in root.iterdir():
                if item.name in SYSTEM_FOLDERS or item.name.startswith("."):
                    continue
                yield item
                if item.is_dir():
                    yield from self._walk(item)
        except PermissionError:
            logger.debug(f"[Unpacker] Permission denied: {root}")
        except OSError as e:
            logger.debug(f"[Unpacker] OS error walking {root}: {e}")

    def _resolve_destination(
        self,
        source: Path,
        staging: Path,
        existing_proposals: List[FlattenProposal],
    ) -> Path:
        """
        Determines the destination path for a file being flattened.

        If the filename already exists in staging (or in another proposal),
        prefixes with the immediate parent folder name to disambiguate.

        Example:
            CV.pdf (from Applications/) → Applications_CV.pdf
        """
        # Collect names already claimed in staging
        claimed_names: Set[str] = set()
        for p in existing_proposals:
            claimed_names.add(p.destination.name)

        # Also check what's already physically in staging
        if staging.exists():
            for existing in staging.iterdir():
                if existing.is_file():
                    claimed_names.add(existing.name)

        candidate = staging / source.name

        if source.name not in claimed_names:
            return candidate

        # Collision — prefix with parent folder name
        parent_prefix = source.parent.name
        new_name = f"{parent_prefix}_{source.name}"
        candidate = staging / new_name

        # If still colliding, add a counter
        counter = 2
        base_name = new_name
        stem = Path(base_name).stem
        suffix = Path(base_name).suffix
        while new_name in claimed_names:
            new_name = f"{stem}_{counter}{suffix}"
            candidate = staging / new_name
            counter += 1

        return candidate
