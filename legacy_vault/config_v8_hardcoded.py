import json
from pathlib import Path
from typing import Set, List, Dict

class Config:
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

    @classmethod
    def load_from_file(cls, path: Path):
        if path.exists():
            with open(path, 'r') as f:
                data = json.load(f)
                # Update attributes if present in json
                for key, value in data.items():
                    if hasattr(cls, key):
                        setattr(cls, key, value)
