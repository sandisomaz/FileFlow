import re
from typing import Dict, Optional, List
from pathlib import Path
import pypdf

class UnifiedExtractor:
    def __init__(self):
        # Patterns tuned for Z83 and SA Public Service Circulars
        self.patterns = {
            'reference': [
                r'(?:Reference number|Ref|REF)\s*[:#\-]?\s*([A-Z0-9/]{4,20})',
                r'([A-Z]{2,4}/\d+/\d+/\d+)' # Matches patterns like HR/4/4/7/56
            ],
            'position': [
                r'(JUDGE\'S SECRETARY|STATE LAW ADVISOR|LEGAL ADMIN OFFICER|CANDIDATE ATTORNEY|ADMINISTRATIVE CLERK)',
                r'(?:Position|Post).*?[:\s]+([A-Za-z\s&]{5,60})'
            ],
            'id_number': [r'(\d{13})'] # Captures the ID number from Section B
        }

    def _read_pdf_text(self, path: Path) -> str:
        """Forensic read: Fast exit on corruption."""
        try:
            with open(path, 'rb') as f:
                # Header check: If not %PDF, Adobe can't open it, neither can we.
                if f.read(4) != b'%PDF': return ""
            
            with open(path, 'rb') as file:
                reader = pypdf.PdfReader(file)
                # Just read page 1 (where the Z83 details and CV summary are)
                return reader.pages[0].extract_text() or ""
        except:
            return ""

    def extract_metadata(self, text: str = "", file_path: Optional[Path] = None) -> Dict[str, str]:
        """
        Extracts metadata from text.
        If text is empty/None and file_path is provided, attempts 'Dirty Scraping' on raw bytes.
        """
        meta = {}
        
        # --- PHASE 23: DEMO TUNING (PRIORITY OVERRIDE) ---
        if file_path:
            fname = file_path.name.upper()

            # 1. Board Exams Logic
            if any(k in fname for k in ["PART", "PAPER", "MEMO", "ANSWERS", "ESTATE"]):
                meta['entity'] = "LEGAL_BOARD_EXAMS"
                if "MEMO" in fname: meta['sub_type'] = "Exam_Memo"
                elif "ANSWERS" in fname: meta['sub_type'] = "Exam_Answers"
                else: meta['sub_type'] = "Board_Exam_Paper"
                return self._finalize(meta)

            # 2. Rex Stone / Firm Extraction Logic
            # Matches: CV_REX_STONE_FOR_BURGER_HUYSER_ATTORNEYS -> BURGER_HUYSER
            # Bypasses "ATTORNEY" normalization by extracting the specific firm name
            if "REX_STONE" in fname:
                # Try to extract the target firm
                match = re.search(r'FOR_(.*?)(?:_ATTORNEYS|_INC|_AND_ASSOCIATES|\.PDF)', fname)
                if match:
                    firm = match.group(1).strip('_')
                    meta['entity'] = firm # Use Firm Name as Folder
                    meta['sub_type'] = "Application_Packet"
                    return meta # DIRECT RETURN to skip normalization!
                else:
                    meta['entity'] = "CANDIDATE_ATTORNEY" # Fallback
                    return self._finalize(meta)

        # Fallback: Dirty Scrape if no text and we have a file path
        if not text and file_path:
            text = self._dirty_scrape(file_path)
            if text:
                meta['sub_type'] = "Scraped_From_Corrupt_File"

        if not text: return self._finalize(meta)

        # Try to find a Reference Number first (This is the best folder name)
        for p in self.patterns['reference']:
            match = re.search(p, text)
            if match:
                ref = match.group(1).strip().replace('/', '_')
                meta['entity'] = f"RECOVERED_{ref}"
                return self._finalize(meta)
        
        # Fallback to Position
        for p in self.patterns['position']:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                pos = match.group(1).strip().upper().replace(' ', '_')
                meta['entity'] = f"RECOVERED_{pos}"
                return self._finalize(meta)

        # --- PHASE 15: FILENAME RESCUE ---
        # If content extracted nothing, look at the filename!
        if file_path and ('entity' not in meta):
            fname = file_path.name.upper()
            # Check for high-value job keywords
            job_keywords = ['JUDGE', 'ADMIN', 'CLERK', 'PROSECUTOR', 'ATTORNEY', 'ADVISOR', 'REGISTRAR', 'PRACTITIONER']
            for job_key in job_keywords:
                if job_key in fname:
                    # Attempt to extract full role: "Application_for_XYZ.pdf" -> "XYZ"
                    # Regex looks for "FOR_" followed by text until dot or digit (Allow underscores!)
                    match = re.search(r'FOR_(.*?)(?:\.PDF|\d)', fname)
                    if match:
                         role = match.group(1).strip('_')
                         meta['entity'] = role
                         meta['sub_type'] = "Filename_Rescued"
                         return self._finalize(meta)
                    # Deep fallback: Just use the keyword if specific extraction fails
                    else:
                         meta['entity'] = f"POTENTIAL_{job_key}"
                         meta['sub_type'] = "Filename_Rescued"
                         return self._finalize(meta)
                         
        # --- PHASE 17: ENTITY NORMALIZATION ---
        return self._finalize(meta)

    def _finalize(self, meta: Dict[str, str]) -> Dict[str, str]:
        if 'entity' in meta:
            meta['entity'] = self._normalize_entity(meta['entity'])
        return meta

    def _normalize_entity(self, entity: str) -> str:
        """
        Collapses fragmented entity names into canonical folders.
        """
        if not entity: return entity
        
        # 1. Sanitize (Remove apostrophes, fix encoding artifacts like â€™)
        # Replace non-alphanumeric chars (except underscore) with underscore
        norm = entity.upper()
        norm = re.sub(r"[^A-Z0-9_]", "_", norm) 
        norm = re.sub(r"_+", "_", norm) # Collapse multiple underscores
        norm = norm.strip('_')

        # 2. Canonical Mapping (The "Folder Collapse")
        # Merging all Judge/Secretary variations
        if any(x in norm for x in ['JUDGE', 'SECRETARY', 'JUSTICE']):
            return "JUDGES_SECRETARY"
        
        # Merging Candidate/Potential Attorney variations
        if any(x in norm for x in ['POTENTIAL_ATTORNEY', 'CANDIDATE_PRACTITIONER', 'CANDIDATE_ATTORNEY']):
            return "CANDIDATE_ATTORNEY"
            
        return norm

    def _dirty_scrape(self, path: Path) -> str:
        """The 'Detective' mode: reads printable strings from corrupt files."""
        try:
            with open(path, 'rb') as f:
                data = f.read(250000) # Read first 250KB where most header info lives
                # Find sequences of text that look like words (4+ printable chars)
                # We filter for likely meaningful text to avoid garbage
                tokens = re.findall(b'[A-Za-z0-9/\s-]{4,}', data)
                return " ".join([m.decode('ascii', errors='ignore') for m in tokens])
        except:
            return ""

    def classify_sub_type(self, path: Path, text: str) -> str:
        t_low = text.lower() if text else ""
        n_low = path.name.lower()
        if "z83" in t_low or "application for employment" in t_low: return "Z83"
        if "curriculum vitae" in t_low or "cv" in n_low: return "CV"
        if "cover letter" in t_low or "cover" in n_low: return "CoverLetter"
        if "scraped_from_corrupt_file" in t_low: return "Recovered_Fragment"
        return "Supporting_Doc"


    def extract_from_filename(self, filename: str) -> Dict[str, str]:
        """
        Legacy/Backup extraction from filename.
        Kept for compatibility with fileflow pipeline.
        """
        return {} 
