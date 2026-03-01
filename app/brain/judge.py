"""
judge.py — The Decision Engine
FileFlow Cognition V9

The Judge examines every file and issues a ruling on where it belongs.

Decision flow:
  1. FAST PATH: V8 rule engine (UnifiedExtractor) — instant, no AI needed
  2. SLOW PATH: SLM ruling via bridge.py — for ambiguous files the rules can't handle

The Judge never destroys files. It only issues verdicts.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .bridge import Bridge

logger = logging.getLogger(__name__)

# Confidence threshold: below this, escalate to the SLM
FAST_PATH_THRESHOLD = 0.7

# Map V8 entity names → V9 archive taxonomy categories
_ENTITY_TO_CATEGORY = {
    "JUDGES_SECRETARY": "Professional",
    "CANDIDATE_ATTORNEY": "Professional",
    "LEGAL_BOARD_EXAMS": "Education",
    "RECOVERED_": "Professional",   # prefix match
    "_Quarantine": "Waste",
    "Ghost_Files": "Waste",
    "Educational_Materials": "Education",
}

# Valid categories the SLM may return
VALID_CATEGORIES = {"Professional", "Education", "Development", "Life_Admin", "Waste", "Unknown"}


@dataclass
class Ruling:
    """The Judge's verdict on a single file."""
    category: str           # Archive taxonomy category
    confidence: float       # 0.0 – 1.0
    reasoning: str          # Human-readable explanation
    path: str               # Fast or Slow
    entity: str             # V8 entity name (preserved for folder naming)
    sub_type: str           # V8 sub_type (preserved)


class Judge:
    """
    The sovereign decision engine for FileFlow Cognition.

    Usage:
        judge = Judge(bridge=Bridge(), extractor=UnifiedExtractor())
        ruling = judge.rule(file_path, extracted_text)
    """

    def __init__(self, bridge: Bridge, extractor):
        self.bridge = bridge
        self.extractor = extractor
        self._prompt_template: Optional[str] = None
        self._load_prompt()

    def _load_prompt(self):
        # Load the ruling prompt template from config/prompts/ruling.md.
        prompt_path = Path("config/prompts/ruling.md")
        try:
            self._prompt_template = prompt_path.read_text(encoding="utf-8")
            logger.debug(f"[Judge] Loaded ruling prompt from {prompt_path}")
        except FileNotFoundError:
            logger.warning(f"[Judge] ruling.md not found at {prompt_path}. Using inline fallback.")
            self._prompt_template = self._fallback_prompt()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rule(
        self,
        file_path: Path,
        extracted_text: str = "",
        folder_hint: str = "",
    ) -> Ruling:
        """
        Issue a ruling on a single file.

        Args:
            file_path:      Path to the file being judged
            extracted_text: Text content already extracted by the staging manager
            folder_hint:    Parent folder name (provides context)

        Returns:
            A Ruling dataclass with category, confidence, reasoning, and V8 metadata
        """
        # --- FAST PATH: V8 Rule Engine ---
        v8_meta = self.extractor.extract_metadata(extracted_text, file_path=file_path)
        v8_sub_type = self.extractor.classify_sub_type(file_path, extracted_text)
        v8_entity = v8_meta.get("entity", "")
        v8_confidence = self._score_v8_confidence(v8_entity, extracted_text)

        if v8_confidence >= FAST_PATH_THRESHOLD:
            category = self._entity_to_category(v8_entity)
            logger.debug(
                f"[Judge] FAST PATH → {file_path.name} → {category} "
                f"(entity={v8_entity}, conf={v8_confidence:.2f})"
            )
            return Ruling(
                category=category,
                confidence=v8_confidence,
                reasoning=f"V8 rule match: entity='{v8_entity}'",
                path="fast",
                entity=v8_entity or file_path.stem.upper(),
                sub_type=v8_sub_type,
            )

        # --- SLOW PATH: SLM Judge ---
        if self.bridge.is_healthy():
            slm_ruling = self._ask_slm(file_path, extracted_text, folder_hint)
            if slm_ruling:
                # Preserve V8 entity if we have one, otherwise derive from category
                entity = v8_entity or self._category_to_default_entity(slm_ruling["category"])
                logger.debug(
                    f"[Judge] SLOW PATH → {file_path.name} → {slm_ruling['category']} "
                    f"(conf={slm_ruling['confidence']:.2f})"
                )
                return Ruling(
                    category=slm_ruling["category"],
                    confidence=slm_ruling["confidence"],
                    reasoning=slm_ruling["reasoning"],
                    path="slow",
                    entity=entity,
                    sub_type=v8_sub_type,
                )

        # --- FALLBACK: V8 behaviour (Ollama offline or SLM failed) ---
        fallback_entity = v8_entity or folder_hint.upper() or "Unclassified"
        logger.debug(f"[Judge] FALLBACK → {file_path.name} → entity={fallback_entity}")
        return Ruling(
            category=self._entity_to_category(fallback_entity),
            confidence=max(v8_confidence, 0.3),
            reasoning="V8 fallback (Ollama unavailable or SLM parse failed)",
            path="fallback",
            entity=fallback_entity,
            sub_type=v8_sub_type,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_v8_confidence(self, entity: str, text: str) -> float:
        """
        Assigns a confidence score to a V8 rule-engine result.

        High confidence = strong pattern match (REF number, Z83, known firm).
        Low confidence = generic fallback entity.
        """
        if not entity:
            return 0.0

        # Strong signals
        if entity in ("JUDGES_SECRETARY", "CANDIDATE_ATTORNEY", "LEGAL_BOARD_EXAMS"):
            return 0.95
        if entity.startswith("RECOVERED_") and len(entity) > 10:
            return 0.85
        if entity == "_Quarantine":
            return 1.0
        if entity == "Ghost_Files":
            return 1.0

        # Partial signals
        if entity.startswith("POTENTIAL_"):
            return 0.55
        if entity == "Unclassified_Recovery":
            return 0.2
        if entity in ("Unknown", "Unclassified"):
            return 0.1

        # Named entity (firm name, position) — moderate confidence
        if re.match(r"^[A-Z][A-Z0-9_]{3,}$", entity):
            return 0.75

        return 0.4

    def _entity_to_category(self, entity: str) -> str:
        """Maps a V8 entity name to a V9 archive taxonomy category."""
        if not entity:
            return "Unknown"

        for key, cat in _ENTITY_TO_CATEGORY.items():
            if entity == key or entity.startswith(key):
                return cat

        # Heuristic fallbacks
        upper = entity.upper()
        if any(x in upper for x in ["JUDGE", "ATTORNEY", "LEGAL", "COURT", "LAW", "FIRM"]):
            return "Professional"
        if any(x in upper for x in ["EXAM", "STUDY", "COURSE", "CERT", "TRANSCRIPT"]):
            return "Education"
        if any(x in upper for x in ["CODE", "DEV", "PROJECT", "SCRIPT", "LOG"]):
            return "Development"
        if any(x in upper for x in ["BANK", "LEASE", "INVOICE", "RECEIPT", "MEDICAL"]):
            return "Life_Admin"
        if entity in ("_Quarantine", "Ghost_Files"):
            return "Waste"

        return "Unknown"

    def _category_to_default_entity(self, category: str) -> str:
        """Returns a sensible default entity name for a given category."""
        defaults = {
            "Professional": "Professional_Archive",
            "Education": "Educational_Materials",
            "Development": "Dev_Workshop",
            "Life_Admin": "Life_Admin",
            "Waste": "_Quarantine",
            "Unknown": "Unclassified",
        }
        return defaults.get(category, "Unclassified")

    def _ask_slm(
        self,
        file_path: Path,
        text: str,
        folder_hint: str,
    ) -> Optional[dict]:
        """
        Sends the file to the SLM for a ruling.
        Returns a dict with {category, confidence, reasoning} or None on failure.
        """
        content_preview = text[:800] if text else "(no text extracted)"
        prompt = (
            f"{self._prompt_template}\n\n"
            f"---\n"
            f"filename: {file_path.name}\n"
            f"folder_hint: {folder_hint or file_path.parent.name}\n"
            f"content_preview:\n{content_preview}\n"
            f"---\n"
            f"Issue your ruling now (JSON only):"
        )

        raw = self.bridge.generate(prompt)
        if not raw:
            return None

        return self._parse_slm_response(raw)

    def _parse_slm_response(self, raw: str) -> Optional[dict]:
        """
        Extracts and validates JSON from the SLM response.
        Handles:
        1. Clean JSON responses
        2. JSON wrapped in markdown code fences
        3. Prose responses (qwen3 fallback) — scans for category keywords
        """
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

        # Try to find JSON object in the response
        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                category = data.get("category", "Unknown")
                if category not in VALID_CATEGORIES:
                    category = self._extract_category_from_prose(cleaned)
                confidence = float(data.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))
                reasoning = str(data.get("reasoning", "No reasoning provided"))
                return {"category": category, "confidence": confidence, "reasoning": reasoning}
            except json.JSONDecodeError:
                pass

        # Prose fallback: scan the raw text for any valid category name
        prose_category = self._extract_category_from_prose(cleaned)
        if prose_category != "Unknown":
            logger.debug(f"[Judge] Prose fallback extracted category: {prose_category}")
            return {
                "category": prose_category,
                "confidence": 0.6,   # Lower confidence since it came from prose
                "reasoning": f"Extracted from prose response: {raw[:120]}",
            }

        logger.warning(f"[Judge] SLM response contained no parseable category: {raw[:200]}")
        return None

    @staticmethod
    def _extract_category_from_prose(text: str) -> str:
        """
        Scans prose text for any valid category name.
        Used as fallback when models don't output JSON.
        """
        # Direct category name match (case-insensitive)
        for cat in ("Professional", "Life_Admin", "Education", "Development", "Waste"):
            if re.search(rf"\b{cat}\b", text, re.IGNORECASE):
                return cat
        # Synonym mapping for common prose patterns
        synonyms = {
            "Professional": ["job application", "cv", "cover letter", "legal", "court", "attorney", "Z83"],
            "Life_Admin":   ["bank statement", "lease", "invoice", "receipt", "personal", "financial"],
            "Education":    ["study guide", "textbook", "exam", "course", "certificate", "transcript"],
            "Development":  ["code", "script", "programming", "software", "project"],
            "Waste":        ["duplicate", "empty", "corrupted", "junk", "temporary"],
        }
        text_lower = text.lower()
        for cat, keywords in synonyms.items():
            if any(kw in text_lower for kw in keywords):
                return cat
        return "Unknown"

    @staticmethod
    def _fallback_prompt() -> str:
        return (
            "You are a file classification assistant. "
            "Classify the document into one of: Professional, Education, Development, Life_Admin, Waste, Unknown. "
            "Respond with JSON: {\"category\": \"...\", \"confidence\": 0.0, \"reasoning\": \"...\"}"
        )
