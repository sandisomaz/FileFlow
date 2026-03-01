"""
refinery.py — Context Propagation Engine
FileFlow Cognition V9

Ensures folder consistency: if a folder has one strong identity (e.g. JUDGES_SECRETARY)
and some weak/unclassified siblings, it propagates the strong identity to all of them.
"""

from typing import Dict, List, Optional
from collections import Counter
from app.muscle.types import StagedFile


class Refinery:
    """
    Context Propagation Engine — decoupled from StagingManager.
    Implements 'Phase 16' logic to ensure folder consistency.

    Usage:
        refinery = Refinery()
        staged_files = refinery.refine(staged_files)

    Optional AI ghost resolution:
        refinery = Refinery()
        refinery.bridge = bridge  # Set after construction if available
        staged_files = refinery.refine(staged_files)
    """

    def __init__(self, weak_entities: List[str] = None):
        self.weak_entities = weak_entities or [
            "INTERNSHIP_DEMO_SOURCE",
            "Unclassified_Recovery",
            "Unknown",
            "_Quarantine",
        ]
        self.bridge = None  # Optionally set externally for AI ghost resolution

    def refine(
        self, staged_files: Dict[str, List[StagedFile]]
    ) -> Dict[str, List[StagedFile]]:
        """
        Groups files by their parent folder.
        If a folder has a 'strong' entity, propagates it to 'weak' siblings.
        """
        # Flatten all files
        by_folder: Dict[str, List[StagedFile]] = {}
        all_files = [f for file_list in staged_files.values() for f in file_list]

        for f in all_files:
            parent = str(f.path.parent)
            by_folder.setdefault(parent, []).append(f)

        for folder, files in by_folder.items():
            # Count strong entity votes in this folder
            votes: Counter = Counter()
            for f in files:
                ent = f.metadata.get("entity")
                if ent and ent not in self.weak_entities:
                    votes[ent] += 1

            if not votes:
                # Ghost folder — try AI resolution if bridge is available
                # NOTE: self.bridge may be None; _resolve_ghost_folder handles that safely
                winning_entity = self._resolve_ghost_folder(
                    [f.path.name for f in files]
                )
                if winning_entity:
                    self._apply_propagation(
                        files, winning_entity, staged_files, "AI_Ghost_Resolution"
                    )
                continue

            winning_entity = votes.most_common(1)[0][0]
            self._apply_propagation(files, winning_entity, staged_files)

        return staged_files

    def _apply_propagation(
        self,
        files: List[StagedFile],
        winning_entity: str,
        staged_files: Dict[str, List[StagedFile]],
        method: str = "Context_Propagated",
    ) -> None:
        """Applies the winning entity to all weak siblings in the list."""
        for f in files:
            current_ent = f.metadata.get("entity")
            if current_ent in self.weak_entities or method == "AI_Ghost_Resolution":
                # Remove from old bucket
                if current_ent in staged_files and f in staged_files[current_ent]:
                    staged_files[current_ent].remove(f)

                # Update metadata
                f.metadata["entity"] = winning_entity
                f.metadata["sub_type"] = f.metadata.get("sub_type", method)
                f.metadata["original_entity"] = current_ent

                # Add to new bucket
                staged_files.setdefault(winning_entity, []).append(f)

    def _resolve_ghost_folder(self, filenames: List[str]) -> Optional[str]:
        """
        Asks the SLM to infer an entity name from a list of filenames.
        Returns None safely if bridge is unavailable or returns nothing useful.
        """
        # Guard: bridge must be set and healthy
        if not self.bridge or not self.bridge.is_healthy():
            return None

        if not filenames:
            return None

        prompt = (
            "Given these filenames found in a folder, what is the most likely "
            "'Entity' name (e.g. Company, Person, or Project) that they belong to?\n\n"
            "Files:\n - " + "\n - ".join(filenames[:15]) + "\n\n"
            "Rules:\n"
            "1. Respond with ONLY the Uppercase Entity Name (e.g. BURGER_HUYSER).\n"
            "2. Use underscores for spaces.\n"
            "3. If you cannot tell, respond 'Unknown'.\n"
            "4. Do not include 'INC' or 'ATTORNEYS' — just the core firm name."
        )

        try:
            raw = self.bridge.generate(prompt)
            if raw and "UNKNOWN" not in raw.upper().strip():
                return raw.strip().upper().replace(" ", "_")
        except Exception:
            pass

        return None