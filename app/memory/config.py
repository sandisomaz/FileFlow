"""
Unified Configuration System for FileFlow V8/V9/V10
Single source of truth — loads from config/settings.yaml + config/config.json
"""

import os
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Set
from dataclasses import dataclass, field, fields

logger = logging.getLogger(__name__)


# ── Safe dataclass builder ─────────────────────────────────────────────────────
def _safe_build(cls, data: dict):
    """
    Builds a dataclass from a dict, silently ignoring unknown keys.
    Prevents crashes when settings.yaml has extra/future fields.
    """
    valid = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in valid})


# ── Config dataclasses ─────────────────────────────────────────────────────────

@dataclass
class SystemConfig:
    version: str = "10.0.0"
    output_folder_prefix: str = "FileFlow_Archive"
    forensic_manifest_name: str = "Forensic_Manifest.json"


@dataclass
class PathsConfig:
    default_output: str = ""   # Resolved at load time
    reports_folder: str = "reports"


@dataclass
class ScanningConfig:
    max_depth: int = 10
    target_extensions: Set[str] = field(default_factory=lambda: {".pdf", ".docx", ".doc"})
    ignored_dirs: Set[str] = field(default_factory=set)


@dataclass
class ClassificationConfig:
    keywords_negative: List[str] = field(default_factory=list)
    known_applicants: List[Dict[str, Any]] = field(default_factory=list)
    law_firms: List[str] = field(default_factory=list)
    categories: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class VersioningConfig:
    format: str = "{entity}_{subtype}_{date}_v{index}{ext}"
    date_format: str = "%Y%m%d"
    duplicate_suffix: str = "DUP"
    max_filename_length: int = 200


@dataclass
class DeduplicationConfig:
    method: str = "content_hash"
    normalize_text: bool = True


@dataclass
class ExecutionConfig:
    dry_run_default: bool = True
    verify_copies: bool = True
    atomic_operations: bool = True
    log_level: str = "INFO"
    timeout_pdf_extraction: int = 3
    ghost_file_threshold: int = 1024


@dataclass
class AIConfig:
    enabled: bool = True
    ollama_url: str = "http://localhost:11434"
    slm_model: str = "ministral-3:3b"        # Must match settings.yaml
    embed_model: str = "qwen3-embedding:4b"  # Must match settings.yaml
    summarise_model: str = "qwen2.5:3b"
    vision_model: str = "qwen3-vl:4b"
    triage_confidence_threshold: float = 0.7
    semantic_dedup_threshold: float = 0.95
    vector_store_path: str = "data/vectors.lance"


# ── Main loader ────────────────────────────────────────────────────────────────

class ConfigLoader:
    """
    Unified configuration loader for FileFlow.
    Loads from settings.yaml (primary) and config.json (categories).
    Unknown YAML keys are silently ignored — safe to add new fields.
    """

    def __init__(
        self,
        yaml_path: str = "config/settings.yaml",
        json_path: str = "config/config.json",
    ):
        self.yaml_path = Path(yaml_path)
        self.json_path = Path(json_path)
        self._load_config()

    def _load_config(self):
        yaml_data: dict = {}
        json_data: dict = {}

        if self.yaml_path.exists():
            try:
                with open(self.yaml_path, "r") as f:
                    yaml_data = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Error loading settings.yaml: {e} — using defaults")

        if self.json_path.exists():
            try:
                with open(self.json_path, "r") as f:
                    json_data = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading config.json: {e}")

        # ── System ─────────────────────────────────────────────────────────────
        self.system = _safe_build(SystemConfig, yaml_data.get("system", {}))

        # ── Paths (with tilde expansion) ───────────────────────────────────────
        paths_raw = yaml_data.get("paths", {})
        if "default_output" in paths_raw:
            # Expand ~/Desktop etc. so the path actually works on every OS
            paths_raw["default_output"] = os.path.expanduser(paths_raw["default_output"])
        if not paths_raw.get("default_output"):
            # Sensible cross-platform default: user's Desktop
            paths_raw["default_output"] = str(Path.home() / "Desktop" / "FileFlow_Archive")
        self.paths = _safe_build(PathsConfig, paths_raw)

        # ── Scanning ───────────────────────────────────────────────────────────
        scan_raw = yaml_data.get("scanning", {})
        self.scanning = ScanningConfig(
            max_depth=scan_raw.get("max_depth", 10),
            target_extensions=set(scan_raw.get("target_extensions", [".pdf", ".docx", ".doc"])),
            ignored_dirs=set(scan_raw.get("ignored_dirs", [])),
        )

        # ── Classification ─────────────────────────────────────────────────────
        cls_yaml = yaml_data.get("classification", {})
        cls_json = json_data.get("categories", {})
        self.classification = ClassificationConfig(
            keywords_negative=cls_yaml.get("keywords_negative", []),
            known_applicants=cls_yaml.get("known_applicants", []),
            law_firms=cls_yaml.get("law_firms", []),
            categories=cls_json,
        )

        # ── Other configs (safe build — unknown keys ignored) ──────────────────
        self.versioning    = _safe_build(VersioningConfig,    yaml_data.get("versioning", {}))
        self.deduplication = _safe_build(DeduplicationConfig, yaml_data.get("deduplication", {}))
        self.execution     = _safe_build(ExecutionConfig,     yaml_data.get("execution", {}))
        self.ai            = _safe_build(AIConfig,            yaml_data.get("ai", {}))

        # ── Raw data cache (for .get() deep lookups) ───────────────────────────
        self._raw_data = yaml_data

        # ── Ignore rules (from JSON, with safe fallback) ───────────────────────
        self._ignore_rules = json_data.get("ignore", {
            "filenames": [".ds_store", "thumbs.db", "desktop.ini"],
            "extensions": [".tmp", ".lnk", ".log", ".bak"],
            "patterns":   [r"~\$", r"^\."],
        })

    # ── Public helpers ─────────────────────────────────────────────────────────

    def get_ignore_rules(self) -> Dict[str, List[str]]:
        return self._ignore_rules

    def get(self, key: str, default: Any = None) -> Any:
        """Supports dot-notation lookup: config.get('ai.slm_model')"""
        mapping = {
            "scan_depth":        self.scanning.max_depth,
            "dry_run_default":   self.execution.dry_run_default,
            "pdf_timeout":       self.execution.timeout_pdf_extraction,
            "ghost_threshold":   self.execution.ghost_file_threshold,
        }
        if key in mapping:
            return mapping[key]

        parts = key.split(".")
        current = self._raw_data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def get_category_config(self, category: str) -> Dict[str, Any]:
        return self.classification.categories.get(category, {})


# ── Legacy compatibility shim ──────────────────────────────────────────────────

class Config:
    """Legacy class kept for backward compatibility. Use ConfigLoader instead."""

    IGNORED_SYSTEM_DIRS: Set[str] = {
        ".venv", "venv", "env", "__pycache__", ".git", "node_modules",
        ".vscode", "site-packages", "Lib", "Scripts", "assets", "images",
        "css", "js", "reports", "_Organized_Output", "System Volume Information",
    }

    TARGET_EXTENSIONS: Set[str] = {".pdf", ".docx", ".doc"}

    KEYWORDS_NEGATIVE: List[str] = [
        "statement", "invoice", "receipt", "lease", "agreement",
        "contract", "payment", "study guide", "textbook", "exam",
        "tutorial", "assignment", "transcript", "ticket", "cheque",
        "curriculum_plan", "id_copy", "matric", "template", "flyer",
        "udemy", "course resource",
    ]

    LAW_FIRMS: List[str] = [
        "ENS", "WEBBER", "BOWMANS", "CLIFFE", "DEKKER", "HOFMEYR",
        "WERKSMANS", "NORTON", "ROSE", "FASKEN", "HOGAN", "LOVELLS",
        "MACROBERT", "ADAMS", "SPOOR", "FISHER", "STRAUSS", "DALY",
        "ATTORNEYS", "INC", "LAW",
    ]