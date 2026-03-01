import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

class ProfileManager:
    PROFILES_FILE = Path.home() / '.fileflow_profiles.json'
    
    @staticmethod
    def load_profiles() -> Dict[str, Dict[str, Any]]:
        if ProfileManager.PROFILES_FILE.exists():
            try:
                with open(ProfileManager.PROFILES_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    @staticmethod
    def save_profiles(profiles: Dict) -> None:
        with open(ProfileManager.PROFILES_FILE, 'w') as f:
            json.dump(profiles, f, indent=2)
            
    @staticmethod
    def create_profile(name: str, folders: List[str]) -> Dict[str, Any]:
        return {
            "folders": folders,
            "created": datetime.now().isoformat()
        }
