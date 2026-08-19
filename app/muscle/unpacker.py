"""
unpacker.py — The Recursive Merge Engine
FileFlow Cognition V9

This is the module that solves the original FileFlow problem:
hundreds of copies of the same job application scattered across
deeply nested folders, created by an automated application system
running tests over months.

The Unpacker:
1. HUNTS across an entire folder tree (no matter how deep)
2. Groups every file by its resolved entity/identity
3. Versions them chronologically (same job applied 5x at 1pm = v1..v5)
4. Detects true duplicates (same content, different folder)
5. Proposes a flat, clean staging area
6. Collapses the empty nests behind it

Design principles:
- Non-destructive: only proposes moves, never acts without approval
- Transparent: every decision has a reason
- Resilient: corrupt files, permission errors, deep paths all handled
- Integrates with Judge for AI-powered entity resolution

Usage:
    unpacker = Unpacker(config, extractor, judge=judge)
    report = unpacker.analyse(source_path, staging_path)
    print(unpacker.summarise(report))

    # After user approval:
    results = unpacker.execute(report, dry_run=False)
"""

import hashlib
import logging
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FileSighting:
    """One discovered instance of a file anywhere in the tree."""
    path: Path
    entity: str                 # Resolved entity name (e.g. "JOHN_SMITH_ATTORNEYS")
    sub_type: str               # CV, CoverLetter, Z83, etc.
    content_hash: str           # MD5 of content (for true duplicate detection)
    file_mtime: float           # Modification timestamp
    depth: int                  # How deep in the tree this was found
    confidence: float           # How confident we are in the entity assignment
    reason: str                 # Why this entity was assigned
    size: int = 0


@dataclass
class MergeProposal:
    """A proposed move for a single file."""
    source: Path
    destination: Path
    entity: str
    version_label: str          # e.g. "v1", "v2_DUP_a3f2b1c4"
    is_duplicate: bool
    duplicate_of: Optional[Path]
    reason: str
    confidence: float


@dataclass
class UnpackReport:
    """Full analysis report from the Unpacker."""
    source_root: Path
    staging_root: Path
    
    # What was found
    total_files_scanned: int = 0
    total_dirs_scanned: int = 0
    max_depth_found: int = 0
    
    # Entity groups
    entity_groups: Dict[str, List[FileSighting]] = field(default_factory=dict)
    
    # Proposals
    proposals: List[MergeProposal] = field(default_factory=list)
    
    # Unresolved (couldn't identify)
    unresolved: List[Path] = field(default_factory=list)
    unresolved_reasons: Dict[str, str] = field(default_factory=dict)
    
    # Stats
    duplicate_count: int = 0
    empty_dirs: List[Path] = field(default_factory=list)

    @property
    def entity_count(self) -> int:
        return len(self.entity_groups)

    @property
    def proposal_count(self) -> int:
        return len(self.proposals)


@dataclass  
class ExecutionResult:
    """Result of executing an UnpackReport."""
    moved: int = 0
    skipped: int = 0
    failed: int = 0
    empty_dirs_removed: int = 0
    errors: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Extensions the Unpacker cares about
# ─────────────────────────────────────────────────────────────────────────────

TARGET_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".rtf",
    ".xlsx", ".xls", ".csv",
    ".jpg", ".jpeg", ".png",
    ".zip", ".rar",
}

IGNORED_DIRS = {
    ".venv", "venv", "env", "__pycache__", ".git", "node_modules",
    ".vscode", "site-packages", "Lib", "Scripts",
    "FileFlow_Archive", "_Flattened", "_Quarantine",
    "BACKUP_V8_OLD", "_legacy_prototypes",
}


# ─────────────────────────────────────────────────────────────────────────────
# The Unpacker
# ─────────────────────────────────────────────────────────────────────────────

class Unpacker:
    """
    The recursive merge engine for FileFlow.

    Hunts an entire folder tree, groups scattered copies of the same
    document by identity, and proposes a clean flat staging area.

    This directly solves the "automated job application system created
    hundreds of nested copies" problem.
    """

    def __init__(
        self,
        extractor=None,
        judge=None,
        max_depth: int = 20,
        min_file_size: int = 512,       # bytes — ignore ghost files
        similarity_threshold: float = 0.95,
    ):
        """
        Args:
            extractor:   UnifiedExtractor for entity resolution
            judge:       Optional Judge for AI-powered classification
            max_depth:   How deep to recurse (default 20, handles any real nesting)
            min_file_size: Files smaller than this are treated as empty/ghost
            similarity_threshold: Content hash match threshold for dedup
        """
        self.extractor = extractor
        self.judge = judge
        self.max_depth = max_depth
        self.min_file_size = min_file_size
        self.similarity_threshold = similarity_threshold

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def analyse(self, source: Path, staging_root: Path, progress_callback=None) -> UnpackReport:
        """
        Full tree analysis. Non-destructive — only reads, never writes.

        Steps:
        1. Walk the entire tree, collecting FileSightings
        2. Group sightings by entity
        3. Within each group, sort chronologically and detect duplicates
        4. Build MergeProposals for each file

        Args:
            source:       Root folder to analyse (can be the entire Desktop)
            staging_root: Where the merged output will go

        Returns:
            UnpackReport with full analysis and proposals
        """
        report = UnpackReport(source_root=source, staging_root=staging_root)

        logger.info(f"[Unpacker] Analysing: {source}")

        # Phase 1: Walk the tree
        sightings = self._walk_tree(source, report, progress_callback)
        logger.info(f"[Unpacker] Found {len(sightings)} files across {report.total_dirs_scanned} dirs")

        # Phase 2: Group by entity
        by_entity: Dict[str, List[FileSighting]] = defaultdict(list)
        for s in sightings:
            if s.entity:
                by_entity[s.entity].append(s)
            else:
                report.unresolved.append(s.path)

        report.entity_groups = dict(by_entity)

        # Phase 3: For each entity group, build proposals
        for entity, group in by_entity.items():
            proposals = self._build_proposals(entity, group, staging_root)
            report.proposals.extend(proposals)
            report.duplicate_count += sum(1 for p in proposals if p.is_duplicate)

        # Phase 4: Find empty dirs (candidates for cleanup)
        report.empty_dirs = self._find_empty_dirs(source)

        logger.info(
            f"[Unpacker] Analysis complete: {report.entity_count} entities, "
            f"{report.proposal_count} proposals, {report.duplicate_count} duplicates"
        )
        return report

    def execute(self, report: UnpackReport, dry_run: bool = True) -> ExecutionResult:
        """
        Executes the proposals from an UnpackReport.

        In dry_run mode: logs what would happen, touches nothing.
        In execute mode: copies files to staging, then removes empty dirs.

        Note: Uses COPY not MOVE. Original files stay until you explicitly
        clean up with the Janitor. This is the safe default.

        Args:
            report:   The UnpackReport from analyse()
            dry_run:  If True, simulate only

        Returns:
            ExecutionResult with counts and any errors
        """
        result = ExecutionResult()

        for proposal in report.proposals:
            if dry_run:
                logger.info(
                    f"[DRY RUN] {proposal.source.name} → "
                    f"{proposal.entity}/{proposal.version_label}"
                )
                result.moved += 1
                continue

            try:
                # Ensure destination directory exists
                proposal.destination.parent.mkdir(parents=True, exist_ok=True)

                # Copy with metadata preservation
                shutil.copy2(str(proposal.source), str(proposal.destination))

                # Verify the copy
                if self._verify_copy(proposal.source, proposal.destination):
                    result.moved += 1
                    logger.debug(f"[Unpacker] Moved: {proposal.source.name} → {proposal.destination}")
                else:
                    result.failed += 1
                    result.errors.append(f"Verification failed: {proposal.source.name}")
                    # Remove failed copy
                    try:
                        proposal.destination.unlink()
                    except Exception:
                        pass

            except PermissionError as e:
                result.failed += 1
                result.errors.append(f"Permission denied: {proposal.source.name}")
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{proposal.source.name}: {e}")

        # Clean up empty dirs (only after all copies succeed)
        if not dry_run and result.failed == 0:
            for empty_dir in report.empty_dirs:
                try:
                    if empty_dir.exists() and not any(empty_dir.iterdir()):
                        empty_dir.rmdir()
                        result.empty_dirs_removed += 1
                except Exception:
                    pass

        return result

    def summarise(self, report: UnpackReport) -> str:
        """
        Human-readable summary of an UnpackReport for terminal output.

        Example:
            ════════════════════════════════════════
            UNPACKER ANALYSIS — C:/Users/<you>/Desktop/courses
            ════════════════════════════════════════
            Scanned:    847 files across 203 directories (max depth: 9)
            Entities:   14 unique document groups found
            Proposals:  847 moves proposed
            Duplicates: 312 (36%) — will be versioned as DUP
            Unresolved: 23 files couldn't be classified

            TOP ENTITIES:
              JOHN_SMITH_ATTORNEYS       127 files  (43 duplicates)
              JUDGES_SECRETARY            89 files  (31 duplicates)
              ...
        """
        lines = [
            "",
            "=" * 60,
            f"UNPACKER ANALYSIS - {report.source_root.name}",
            "=" * 60,
            f"Scanned:    {report.total_files_scanned} files across "
            f"{report.total_dirs_scanned} directories "
            f"(max depth: {report.max_depth_found})",
            f"Entities:   {report.entity_count} unique document groups found",
            f"Proposals:  {report.proposal_count} moves proposed",
            f"Duplicates: {report.duplicate_count} "
            f"({int(report.duplicate_count / max(report.proposal_count, 1) * 100)}%) "
            f"- will be versioned as DUP",
            f"Unresolved: {len(report.unresolved)} files couldn't be classified",
        ]

        if report.entity_groups:
            lines.append("")
            lines.append("TOP ENTITIES:")
            sorted_entities = sorted(
                report.entity_groups.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )
            for entity, group in sorted_entities[:10]:
                dupe_count = sum(
                    1 for p in report.proposals
                    if p.entity == entity and p.is_duplicate
                )
                lines.append(
                    f"  {entity:<40} {len(group):>4} files"
                    + (f"  ({dupe_count} duplicates)" if dupe_count else "")
                )

        if report.unresolved:
            lines.append("")
            lines.append(f"UNRESOLVED (first 5):")
            for path in report.unresolved[:5]:
                reason = report.unresolved_reasons.get(str(path), "No entity detected")
                lines.append(f"  {path.name[:50]:<50}  {reason}")

        if report.empty_dirs:
            lines.append("")
            lines.append(f"EMPTY DIRS TO CLEAN: {len(report.empty_dirs)}")

        lines.append("=" * 60)
        lines.append("")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Tree Walking
    # ─────────────────────────────────────────────────────────────────────

    def _walk_tree(self, root: Path, report: UnpackReport, progress_callback=None) -> List[FileSighting]:
        """
        Recursively walks the tree using a stack (no recursion limit issues).
        Returns all FileSightings found.
        """
        sightings = []
        visited = set()

        # Stack items: (path, depth)
        stack = [(root, 0)]

        while stack:
            current_dir, depth = stack.pop()

            # Resolve symlinks and detect loops
            try:
                real = current_dir.resolve()
                if real in visited:
                    continue
                visited.add(real)
            except Exception:
                continue

            if depth > self.max_depth:
                continue

            report.total_dirs_scanned += 1
            report.max_depth_found = max(report.max_depth_found, depth)

            try:
                entries = list(current_dir.iterdir())
            except PermissionError:
                continue
            except Exception:
                continue

            for entry in entries:
                try:
                    if entry.is_dir():
                        # Skip system/ignored directories
                        if entry.name.lower() in IGNORED_DIRS:
                            continue
                        if entry.name.startswith('.'):
                            continue
                        stack.append((entry, depth + 1))

                    elif entry.is_file():
                        # HEARTBEAT: Tell the UI which file we are looking at
                        if progress_callback:
                            progress_callback(entry.name)

                        if entry.suffix.lower() not in TARGET_EXTENSIONS:
                            continue

                        # Ghost file check
                        try:
                            size = entry.stat().st_size
                        except OSError:
                            size = 0

                        if size < self.min_file_size:
                            report.unresolved.append(entry)
                            report.unresolved_reasons[str(entry)] = f"Too small ({size} bytes)"
                            report.total_files_scanned += 1
                            continue

                        # Resolve entity for this file
                        sighting = self._resolve_file(entry, depth, size)
                        report.total_files_scanned += 1

                        if sighting.entity:
                            sightings.append(sighting)
                        else:
                            report.unresolved.append(entry)
                            report.unresolved_reasons[str(entry)] = sighting.reason

                except PermissionError:
                    continue
                except Exception as e:
                    logger.debug(f"[Unpacker] Error processing {entry}: {e}")
                    continue

        return sightings

    # ─────────────────────────────────────────────────────────────────────
    # Entity Resolution
    # ─────────────────────────────────────────────────────────────────────

    def _resolve_file(self, path: Path, depth: int, size: int) -> FileSighting:
        """
        Determines the entity for a single file.

        Resolution order:
        1. Extractor (V8 rules — fast, handles job applications well)
        2. Judge (AI — for ambiguous files)
        3. Folder context (parent folder name as fallback)
        4. Filename heuristics
        """
        entity = ""
        sub_type = "Document"
        confidence = 0.0
        reason = "No entity detected"
        content_hash = ""

        # Content hash (for dedup)
        content_hash = self._hash_file(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = datetime.now().timestamp()

        # BUGFIX: `text` was previously referenced below without ever being
        # assigned, which raised NameError on every call and was silently
        # swallowed by the broad except blocks — every file was falling
        # through to "unresolved" no matter what it actually contained.
        text = self._extract_text(path)

        # Step 1: V8 Extractor
        if self.extractor:
            try:
                meta = self.extractor.extract_metadata(text, file_path=path)
                sub_type = self.extractor.classify_sub_type(path, text)
                if meta.get("entity"):
                    entity = meta["entity"]
                    confidence = 0.75
                    reason = f"V8 rule match (text extraction)"
            except Exception as e:
                logger.debug(f"[Unpacker] Extractor failed for {path.name}: {e}")

        # Step 2: AI Judge for low-confidence or no-entity files
        if not entity or confidence < 0.5:
            if self.judge:
                try:
                    ruling = self.judge.rule(
                        file_path=path,
                        extracted_text=text,
                        folder_hint=path.parent.name,
                    )
                    if ruling.entity and ruling.confidence > confidence:
                        entity = ruling.entity
                        sub_type = ruling.sub_type or sub_type
                        confidence = ruling.confidence
                        reason = f"AI Judge ({ruling.path} path): {ruling.reasoning[:80]}"
                except Exception as e:
                    logger.debug(f"[Unpacker] Judge failed for {path.name}: {e}")

        # Step 3: Folder context fallback
        if not entity:
            folder_entity = self._entity_from_folder(path)
            if folder_entity:
                entity = folder_entity
                confidence = 0.4
                reason = f"Folder context: {path.parent.name}"

        # Step 4: Filename heuristics
        if not entity:
            fname_entity = self._entity_from_filename(path)
            if fname_entity:
                entity = fname_entity
                confidence = 0.35
                reason = f"Filename heuristic"

        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0

        return FileSighting(
            path=path,
            entity=entity,
            sub_type=sub_type,
            content_hash=content_hash,
            file_mtime=mtime,
            depth=depth,
            confidence=confidence,
            reason=reason,
            size=size,
        )

    def _entity_from_folder(self, path: Path) -> str:
        """Infers entity from the parent folder name."""
        parent = path.parent.name.upper()
        # Skip generic folder names
        generic = {
            "DOWNLOADS", "DESKTOP", "DOCUMENTS", "COURSES",
            "APPLICATIONS", "JOBS", "FILES", "MISC", "OTHER",
            "NEW FOLDER", "TEMP", "TMP", "1", "2", "3",
        }
        if parent in generic:
            # Try grandparent
            grandparent = path.parent.parent.name.upper()
            if grandparent not in generic and len(grandparent) > 3:
                return self._sanitise_entity(grandparent)
            return ""
        if len(parent) > 3:
            return self._sanitise_entity(parent)
        return ""

    def _entity_from_filename(self, path: Path) -> str:
        """
        Last-resort entity extraction from the filename itself.
        Handles patterns like:
        - CV_Applicant_for_Acme_Corp.pdf
        - Application_Office_Manager_2024.pdf
        - ACME_CoverLetter.pdf
        """
        stem = path.stem.upper()

        # Pattern: ..._FOR_<FIRM>
        match = re.search(r'FOR[_\s]+([A-Z][A-Z0-9_\s&]{3,40}?)(?:[_\s]ATTORNEY|[_\s]INC|\.|\d|$)', stem)
        if match:
            return self._sanitise_entity(match.group(1))

        # Known position keywords
        positions = [
            "JUDGES_SECRETARY", "CANDIDATE_ATTORNEY", "STATE_LAW_ADVISOR",
            "LEGAL_ADMIN", "ADMIN_CLERK", "PROSECUTOR", "REGISTRAR",
        ]
        for pos in positions:
            if pos.replace("_", "") in stem.replace("_", "").replace(" ", ""):
                return pos

        # Known law firm keywords
        firms = [
            "WERKSMANS", "BOWMANS", "NORTON", "FASKEN", "HOGAN",
            "ENS", "CLIFFE", "DEKKER", "WEBBER",
        ]
        for firm in firms:
            if firm in stem:
                return firm + "_ATTORNEYS"

        return ""

    # ─────────────────────────────────────────────────────────────────────
    # Proposal Building
    # ─────────────────────────────────────────────────────────────────────

    def _build_proposals(
        self,
        entity: str,
        group: List[FileSighting],
        staging_root: Path,
    ) -> List[MergeProposal]:
        """
        For one entity group:
        1. Sort chronologically by file modification time
        2. Detect true duplicates by content hash
        3. Generate versioned filenames
        4. Build MergeProposal for each file
        """
        proposals = []

        # Sort chronologically — oldest first
        group_sorted = sorted(group, key=lambda s: s.file_mtime)

        # Track content hashes to detect duplicates
        seen_hashes: Dict[str, Path] = {}

        # Track versions per (entity, sub_type, date) for numbering
        version_counters: Dict[str, int] = defaultdict(int)

        entity_dir = staging_root / entity

        for sighting in group_sorted:
            is_dupe = False
            dupe_of = None

            # Duplicate detection by content hash
            if sighting.content_hash and sighting.content_hash != "FAILED":
                if sighting.content_hash in seen_hashes:
                    is_dupe = True
                    dupe_of = seen_hashes[sighting.content_hash]
                else:
                    seen_hashes[sighting.content_hash] = sighting.path

            # Build version key: entity + subtype + date
            date_str = datetime.fromtimestamp(sighting.file_mtime).strftime("%Y%m%d")
            version_key = f"{sighting.sub_type}_{date_str}"
            version_counters[version_key] += 1
            version_num = version_counters[version_key]

            # Build filename
            ext = sighting.path.suffix.lower()
            safe_entity = self._sanitise_entity(entity)[:40]
            safe_subtype = re.sub(r"[^\w]", "_", sighting.sub_type)[:20]

            if is_dupe:
                short_hash = sighting.content_hash[:8] if sighting.content_hash else "UNKN"
                version_label = f"v{version_num}_DUP_{short_hash}"
            else:
                version_label = f"v{version_num}"

            new_filename = f"{safe_entity}_{safe_subtype}_{date_str}_{version_label}{ext}"
            destination = entity_dir / new_filename

            proposals.append(MergeProposal(
                source=sighting.path,
                destination=destination,
                entity=entity,
                version_label=version_label,
                is_duplicate=is_dupe,
                duplicate_of=dupe_of,
                reason=sighting.reason,
                confidence=sighting.confidence,
            ))

        return proposals

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _extract_text(self, path: Path) -> str:
        """
        Fast text extraction for entity resolution.
        Only reads the first page / first 500 chars — speed matters here
        since we might process thousands of files.
        """
        try:
            if path.suffix.lower() == ".pdf":
                # Try pdfplumber first (more reliable)
                try:
                    import pdfplumber
                    with pdfplumber.open(path) as pdf:
                        if pdf.pages:
                            text = pdf.pages[0].extract_text() or ""
                            return text[:2000]
                except Exception:
                    pass

                # Fallback to pypdf
                try:
                    import pypdf
                    with open(path, "rb") as f:
                        if f.read(4) != b"%PDF":
                            return ""
                        f.seek(0)
                        reader = pypdf.PdfReader(f)
                        if reader.pages:
                            return (reader.pages[0].extract_text() or "")[:2000]
                except Exception:
                    pass

            elif path.suffix.lower() in {".txt", ".csv", ".rtf"}:
                return path.read_text(encoding="utf-8", errors="replace")[:2000]

            elif path.suffix.lower() in {".docx", ".doc"}:
                try:
                    import docx
                    doc = docx.Document(str(path))
                    return " ".join(p.text for p in doc.paragraphs[:10])[:2000]
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"[Unpacker] Text extraction failed for {path.name}: {e}")

        return ""

    @staticmethod
    def _hash_file(path: Path) -> str:
        """MD5 hash of raw file bytes for true duplicate detection."""
        try:
            md5 = hashlib.md5()
            with open(path, "rb") as f:
                while chunk := f.read(65536):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception:
            return "FAILED"

    @staticmethod
    def _verify_copy(source: Path, destination: Path) -> bool:
        """Verifies a copy succeeded by comparing file sizes."""
        try:
            return source.stat().st_size == destination.stat().st_size
        except Exception:
            return False

    @staticmethod
    def _sanitise_entity(name: str) -> str:
        """Makes entity name safe for use as a folder/filename component."""
        clean = re.sub(r"[^\w\s-]", "", name)
        clean = re.sub(r"[\s\-]+", "_", clean)
        clean = re.sub(r"_+", "_", clean)
        clean = clean.strip("_").upper()
        return clean[:50]

    @staticmethod
    def _find_empty_dirs(root: Path) -> List[Path]:
        """
        Finds all empty directories under root.
        Returns them deepest-first so we can remove them safely
        without trying to remove a parent before its children.
        """
        empty = []
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            # Skip system dirs
            path = Path(dirpath)
            if path.name.lower() in IGNORED_DIRS:
                continue
            if not filenames and not dirnames:
                if path != root:
                    empty.append(path)
        return empty