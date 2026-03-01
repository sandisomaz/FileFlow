"""
Unified Configuration System for FileFlow V8
MERGED: config.json + settings.yaml + config.py hardcoded values
SINGLE SOURCE OF TRUTH
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Set
from dataclasses import dataclass, field


@dataclass
class SystemConfig:
    version: str = "9.2.0"
    output_folder_prefix: str = "_FileFlow_Final_Clean"
    forensic_manifest_name: str = "Forensic_Manifest.json"


@dataclass
class PathsConfig:
    default_output: str = "C:/FileFlow_Archive"
    reports_folder: str = "reports"


@dataclass
class ScanningConfig:
    max_depth: int = 10
    target_extensions: Set[str] = field(default_factory=lambda: {'.pdf', '.docx', '.doc'})
    ignored_dirs: Set[str] = field(default_factory=set)


@dataclass
class ClassificationConfig:
    keywords_negative: List[str] = field(default_factory=list)
    known_applicants: List[Dict[str, Any]] = field(default_factory=list)
    law_firms: List[str] = field(default_factory=list)
    
    # Unified category rules from config.json
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
    ghost_file_threshold: int = 1024  # Files smaller than this (bytes) are "ghost files"


@dataclass
class AIConfig:
    enabled: bool = True
    ollama_url: str = "http://localhost:11434"
    slm_model: str = "qwen3:4b"
    embed_model: str = "qwen3-embedding:4b"
    summarise_model: str = "qwen2.5:3b"
    vision_model: str = "qwen3-vl:4b"
    triage_confidence_threshold: float = 0.7
    semantic_dedup_threshold: float = 0.95
    vector_store_path: str = "data/vectors.lance"


class ConfigLoader:
    """
    Unified configuration loader for FileFlow V8.
    Loads from settings.yaml (primary) and config.json (categories).
    """
    
    def __init__(self, yaml_path: str = "config/settings.yaml", json_path: str = "config/config.json"):
        self.yaml_path = Path(yaml_path)
        self.json_path = Path(json_path)
        self._load_config()
    
    def _load_config(self):
        """Load configuration from both YAML and JSON sources."""
        yaml_data = {}
        json_data = {}
        
        # Load YAML (primary settings)
        if self.yaml_path.exists():
            try:
                with open(self.yaml_path, 'r') as f:
                    yaml_data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"⚠️ Error loading YAML config: {e}")
        
        # Load JSON (categories)
        if self.json_path.exists():
            try:
                with open(self.json_path, 'r') as f:
                    json_data = json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading JSON config: {e}")
        
        # Initialize components
        self.system = SystemConfig(**yaml_data.get('system', {}))
        self.paths = PathsConfig(**yaml_data.get('paths', {}))
        
        # Scanning config
        scan_data = yaml_data.get('scanning', {})
        self.scanning = ScanningConfig(
            max_depth=scan_data.get('max_depth', 10),
            target_extensions=set(scan_data.get('target_extensions', ['.pdf', '.docx', '.doc'])),
            ignored_dirs=set(scan_data.get('ignored_dirs', []))
        )
        
        # Classification config (merge YAML + JSON)
        classification_yaml = yaml_data.get('classification', {})
        classification_json = json_data.get('categories', {})
        
        self.classification = ClassificationConfig(
            keywords_negative=classification_yaml.get('keywords_negative', []),
            known_applicants=classification_yaml.get('known_applicants', []),
            law_firms=classification_yaml.get('law_firms', []),
            categories=classification_json  # Categories from JSON
        )
        
        # Other configs
        self.versioning = VersioningConfig(**yaml_data.get('versioning', {}))
        self.deduplication = DeduplicationConfig(**yaml_data.get('deduplication', {}))
        
        exec_data = yaml_data.get('execution', {})
        self.execution = ExecutionConfig(**exec_data)

        ai_data = yaml_data.get('ai', {})
        self.ai = AIConfig(**ai_data)
        
        # Cache raw data for .get() support
        self._raw_data = yaml_data
        
        # Merge ignore rules from JSON
        self._ignore_rules = json_data.get('ignore', {
            'filenames': ['.ds_store', 'thumbs.db', 'desktop.ini'],
            'extensions': ['.tmp', '.lnk', '.log', '.bak'],
            'patterns': [r'~\$', r'^\.']
        })
    
    def get_ignore_rules(self) -> Dict[str, List[str]]:
        """Returns unified ignore rules."""
        return self._ignore_rules
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Generic settings getter supporting nested keys (e.g., 'ai.slm_model').
        """
        # First check backwards compatibility mapping
        mapping = {
            'scan_depth': self.scanning.max_depth,
            'dry_run_default': self.execution.dry_run_default,
            'pdf_timeout': self.execution.timeout_pdf_extraction,
            'ghost_threshold': self.execution.ghost_file_threshold
        }
        if key in mapping:
            return mapping[key]

        # Use raw data for deep lookup
        parts = key.split('.')
        current = self._raw_data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current
    
    def get_category_config(self, category: str) -> Dict[str, Any]:
        """Get configuration for a specific category."""
        return self.classification.categories.get(category, {})
    
    def export_merged_config(self, output_path: Path):
        """
        Exports the current configuration as a single unified YAML file.
        Useful for creating a new master config.
        """
        merged = {
            'system': {
                'version': self.system.version,
                'output_folder_prefix': self.system.output_folder_prefix,
                'forensic_manifest_name': self.system.forensic_manifest_name
            },
            'paths': {
                'default_output': self.paths.default_output,
                'reports_folder': self.paths.reports_folder
            },
            'scanning': {
                'max_depth': self.scanning.max_depth,
                'target_extensions': list(self.scanning.target_extensions),
                'ignored_dirs': list(self.scanning.ignored_dirs)
            },
            'classification': {
                'keywords_negative': self.classification.keywords_negative,
                'known_applicants': self.classification.known_applicants,
                'law_firms': self.classification.law_firms,
                'categories': self.classification.categories
            },
            'versioning': {
                'format': self.versioning.format,
                'date_format': self.versioning.date_format,
                'duplicate_suffix': self.versioning.duplicate_suffix,
                'max_filename_length': self.versioning.max_filename_length
            },
            'deduplication': {
                'method': self.deduplication.method,
                'normalize_text': self.deduplication.normalize_text
            },
            'execution': {
                'dry_run_default': self.execution.dry_run_default,
                'verify_copies': self.execution.verify_copies,
                'atomic_operations': self.execution.atomic_operations,
                'log_level': self.execution.log_level,
                'timeout_pdf_extraction': self.execution.timeout_pdf_extraction,
                'ghost_file_threshold': self.execution.ghost_file_threshold
            },
            'ignore_rules': self._ignore_rules
        }
        
        try:
            with open(output_path, 'w') as f:
                yaml.dump(merged, f, default_flow_style=False, sort_keys=False)
            print(f"✅ Merged config exported to: {output_path}")
        except Exception as e:
            print(f"❌ Failed to export config: {e}")


# Backwards compatibility - hardcoded fallbacks
class Config:
    """Legacy config class for backwards compatibility."""
    
    IGNORED_SYSTEM_DIRS: Set[str] = {
        '.venv', 'venv', 'env', '__pycache__', '.git', 'node_modules', 
        '.vscode', 'site-packages', 'Lib', 'Scripts', 'assets', 'images', 'css', 'js',
        'reports', '_Organized_Output', 'System Volume Information'
    }

    TARGET_EXTENSIONS: Set[str] = {'.pdf', '.docx', '.doc'}

    KEYWORDS_NEGATIVE: List[str] = [
        "statement", "invoice", "receipt", "lease", "agreement", 
        "contract", "payment", "study guide", "textbook", "exam", 
        "tutorial", "assignment", "transcript", "ticket", "cheque",
        "curriculum_plan", "id_copy", "matric", "template", "flyer",
        "udemy", "course resource"
    ]

    FOLDER_JOB_MAP: Dict[str, str] = {
        "ADMINISTRATION_CLERK": "Administration_Clerk",
        "ADMIN_CLERK": "Administration_Clerk",
        "REGIONAL_COURT": "Regional_Court_Prosecutor",
        "DISTRICT_COURT": "District_Court_Prosecutor",
        "PROSECUTOR": "Public_Prosecutor",
        "SECRETARY": "Secretary",
        "JUDGE": "Judges_Secretary",
        "LEGAL_ADMIN": "Legal_Admin_Officer",
        "STATE_LAW": "State_Law_Advisor",
        "CANDIDATE": "Candidate_Attorney",
        "ATTORNEY": "Candidate_Attorney",
        "INTERNSHIP": "Legal_Internship",
        "REGISTRAR": "Registrar",
        "CLERK": "Clerk"
    }

    LAW_FIRMS: List[str] = [
        "ENS", "WEBBER", "BOWMANS", "CLIFFE", "DEKKER", "HOFMEYR", 
        "WERKSMANS", "NORTON", "ROSE", "FASKEN", "HOGAN", "LOVELLS",
        "MACROBERT", "ADAMS", "SPOOR", "FISHER", "STRAUSS", "DALY",
        "ATTORNEYS", "INC", "LAW"
    ]
