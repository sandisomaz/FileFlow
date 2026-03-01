# utils/categorizer.py
import json
import re
from pathlib import Path
from typing import Any, Dict, List

# Define a type alias for file metadata for clarity
FileInfo = Dict[str, Any]

class Categorizer:
    def __init__(self, config_path: str = 'config.json') -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.categories = self.config.get('categories', {})
        self.settings = self.config.get('settings', {})
        self._normalize_rules()

    def _load_config(self) -> Dict[str, Any]:
        """Load and parse the JSON configuration file."""
        try:
            with self.config_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Config not found: {self.config_path}. Using defaults.")
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing config: {e}. Using defaults.")
        
        return {
            "categories": {"Other_Files": {}},
            "settings": {"organize_by_date": True, "date_format": "%Y-%m"}
        }

    def _normalize_rules(self) -> None:
        """Pre-compile regex patterns and lowercase keywords for efficiency."""
        for category, rules in self.categories.items():
            # Lowercase simple keywords
            rules['keywords'] = [k.lower() for k in rules.get('keywords', [])]
            
            # Compile regex patterns for efficiency
            regex_keywords = rules.get('regex_keywords', [])
            rules['compiled_regex'] = [re.compile(p, re.IGNORECASE) for p in regex_keywords]

    def categorize_file(self, file_data: FileInfo) -> str:
        """
        Categorize a file based on a scoring and priority system.
        Supports keywords, regex, extensions, and priority weighting.
        """
        name = file_data.get('name', '').lower()
        ext = file_data.get('extension', '').lower()

        best_category = "Other_Files"
        highest_score = -1
        highest_priority = -1

        for category, rules in self.categories.items():
            score = 0
            
            # 1. Check standard keywords (high score)
            for keyword in rules.get('keywords', []):
                if keyword in name:
                    score += 10
            
            # 2. Check regex patterns (very high score)
            for pattern in rules.get('compiled_regex', []):
                if pattern.search(name): # Use re.search for substring matching.
                    score += 20
            
            # 3. Check file extensions (medium score)
            if ext and ext in rules.get('extensions', []):
                score += 5

            if score > 0:
                priority = rules.get('priority', 0)
                # Prioritize by category priority first, then by match score
                if priority > highest_priority:
                    highest_priority = priority
                    highest_score = score
                    best_category = category
                elif priority == highest_priority and score > highest_score:
                    highest_score = score
                    best_category = category
                    
        return best_category