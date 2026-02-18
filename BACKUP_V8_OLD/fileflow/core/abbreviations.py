"""
Entity name abbreviations to avoid Windows MAX_PATH issues.
Maps long job position names to shorter equivalents.
"""

from typing import Dict

ENTITY_ABBREVIATIONS: Dict[str, str] = {
    # Government Positions (Long Names)
    "Uif_Client_Service_Officer": "UIF_CSO",
    "Transversal_Contracting_Support_Officer": "Trans_CSO",
    "Inspection_And_Enforcement_Services": "Inspect_Enforce",
    "Immovable_Asset_Register": "Asset_Reg",
    "Public_Employment_Services": "Pub_Employ",
    "Intern_Labour_Relations": "Intern_Labour",
    "Business_Regulation": "Bus_Reg",
    "Administrative_Officer": "Admin_Officer",
    
    # Office Positions
    "Human_Resource_Clerk": "HR_Clerk",
    "Administration_Clerk": "Admin_Clerk",
    "Chief_Registry_Clerk": "Chief_Reg",
    "Msc_Administration_Clerk": "MSc_Admin",
    "Registrars_Clerk": "Reg_Clerk",
    "Registry_Clerk": "Reg_Clerk",
    "Records_Clerk": "Reg_Clerk",
    
    # Legal Positions
    "Judges_Secretary": "Judge_Sec",
    "State_Law_Advisor": "State_Law",
    "Legal_Admin_Officer": "Legal_Admin",
    "Candidate_Attorney": "Cand_Atty",
    
    # Other
    "Estate_Controller": "Estate_Ctrl",
    "Data_Capturer": "Data_Cap",
    "Team_Leader": "Team_Lead",
}

def abbreviate_entity(entity_name: str, max_length: int = 50) -> str:
    """
    Shorten entity names to avoid MAX_PATH issues.
    """
    # Check if we have a predefined abbreviation
    if entity_name in ENTITY_ABBREVIATIONS:
        return ENTITY_ABBREVIATIONS[entity_name]
    
    # If name is too long and no abbreviation exists, truncate
    if len(entity_name) > max_length:
        return entity_name[:max_length].rstrip('_')
    
    return entity_name


def get_full_name(abbreviated: str) -> str:
    """
    Reverse lookup: Get full name from abbreviation.
    """
    reverse_map = {v: k for k, v in ENTITY_ABBREVIATIONS.items()}
    return reverse_map.get(abbreviated, abbreviated)
