"""
sniffer.py — Level 1 Triage
FileFlow X (V10)

The Sniffer acts as the "Fast Path" in the Tiered Triage Pool.
Its job is to analyze extracted text or filenames incredibly fast (<100ms) 
using regex patterns and heuristics. If it's 90% confident, it returns a 
classification and extracts "Facts" (IDs, names, case numbers) to broadcast 
to the Knowledge Graph. Only if it fails does the file go to the Judge (Level 2).
"""

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class SniffResult:
    """The result from the Level 1 Sniffer."""
    confidence: float
    category: str
    sub_type: str
    facts: Dict[str, str] = field(default_factory=dict) # e.g. {"CaseID": "12345", "PersonName": "John Doe"}
    source: str = "Sniffer (Level 1)"

class Sniffer:
    """
    Ultra-fast heuristic analyzer to preserve hardware resources.
    Matches predefined patterns for common document types to bypass SLM inference.
    """

    def __init__(self):
        # Professional/Legal
        self.invoice_regex = re.compile(r"\b(INVOICE|TAX INVOICE|BILL TO)\b", re.IGNORECASE)
        self.legal_ref_regex = re.compile(r"\bREF:\s*([A-Z0-9-]{5,})\b", re.IGNORECASE)
        self.id_number_regex = re.compile(r"\b(?P<id_number>\d{13})\b") # Generic 13-digit ID number pattern
        self.case_number_regex = re.compile(r"\b(\d{1,6}/\d{2,4})\b") # Case/Docket Number format (e.g. 123/2023)
        
        # Academia / CV
        self.cv_regex = re.compile(r"\b(CURRICULUM VITAE|RESUME|WORK EXPERIENCE|EDUCATION)\b", re.IGNORECASE)
        self.z83_regex = re.compile(r"\bZ83(?: FORM| APPLICATION)?\b", re.IGNORECASE)
        self.transcript_regex = re.compile(r"\b(ACADEMIC TRANSCRIPT|ACADEMIC RECORD|DEGREE CERTIFICATE)\b", re.IGNORECASE)

    def sniff(self, file_path: Path, extracted_text: str = "") -> SniffResult:
        """
        Takes a file and its text, returns a SniffResult if a strong match is found.
        """
        content = extracted_text if extracted_text else ""
        text_to_analyze = file_path.name + " " + content
        
        facts = {}
        
        # 1. Fact Extraction (These are extracted even if confidence isn't 1.0)
        # 1a. ID Number
        id_match = self.id_number_regex.search(text_to_analyze)
        if id_match:
            id_val = id_match.group("id_number")
            facts["ID_Number"] = id_val
            facts["SA_ID"] = id_val

        # 1b. Case Number Extraction
        case_match = self.case_number_regex.search(text_to_analyze)
        if case_match:
            facts["CaseNumber"] = case_match.group(1)
            
        # 1b. Legal Reference Number
        ref_match = self.legal_ref_regex.search(text_to_analyze)
        if ref_match:
            facts["CaseReference"] = ref_match.group(1).upper()

        # 2. Classification
        if self.z83_regex.search(text_to_analyze):
            facts["DocumentType"] = "Z83 Application"
            return SniffResult(confidence=0.95, category="Professional", sub_type="Z83 Application", facts=facts)

        if self.cv_regex.search(text_to_analyze) and len(content) > 10:
            facts["DocumentType"] = "CV / Resume"
            return SniffResult(confidence=0.90, category="Professional", sub_type="CV / Resume", facts=facts)

        if self.transcript_regex.search(text_to_analyze):
            facts["DocumentType"] = "Academic Record"
            return SniffResult(confidence=0.95, category="Education", sub_type="Academic Record", facts=facts)

        if self.invoice_regex.search(text_to_analyze):
            facts["DocumentType"] = "Invoice"
            return SniffResult(confidence=0.85, category="Life_Admin", sub_type="Invoice", facts=facts)
            
        # If we found a case reference but no specific document type, 
        # it's still highly likely a professional/legal document
        if "CaseReference" in facts or "CaseNumber" in facts:
            return SniffResult(confidence=0.80, category="Professional", sub_type="Legal Document", facts=facts)

        # Fallback - Low confidence, send to Judge
        return SniffResult(confidence=0.1, category="Unknown", sub_type="Document", facts=facts)

    def is_confident(self, result: SniffResult, threshold: float = 0.8) -> bool:
        """Helper to determine if we should bypass the Judge."""
        return result.confidence >= threshold
