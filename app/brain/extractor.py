import re
from typing import Dict, Optional, List
from pathlib import Path
import pypdf

class UnifiedExtractor:
    """
    Generalized & Adaptive Document Metadata & Text Extractor.
    Extracts text, references, roles, entities, and document sub-types
    across diverse document layouts and formats without hardcoded personal heuristics.
    """
    def __init__(self):
        # Universal reference, position, and identifier patterns
        self.patterns = {
            'reference': [
                r'(?:Reference|Ref|REF|Case|Account|Invoice|Policy|Claim)(?:\s*(?:Number|No|Num|Code|Id|#))?\s*[:#\-]\s*([A-Z0-9/_-]{4,30})',
                r'(?:Reference\s*number|Ref|REF)\s*[:#\-]?\s*([A-Z0-9/]{4,20})',
                r'([A-Z]{2,4}/\d+/\d+/\d+)'  # Circular / hierarchical refs (e.g. HR/4/4/7/56)
            ],
            'position': [
                r'(?:Position|Post|Title|Role|Designation)\s*[:\s]+([A-Za-z0-9\s&/-]{4,60})',
                r'(JUDGE\'S SECRETARY|STATE LAW ADVISOR|LEGAL ADMIN OFFICER|CANDIDATE ATTORNEY|ADMINISTRATIVE CLERK)'
            ],
            'id_number': [r'\b(\d{13})\b']  # Generic 13-digit identification numbers
        }

    def _read_pdf_text(self, path: Path, max_pages: int = 10, max_chars: int = 20000) -> str:
        """
        Forensic multi-page PDF read:
        Safely extracts text across up to `max_pages` without hanging on oversized files.
        """
        try:
            with open(path, 'rb') as f:
                # Fast header check: If not %PDF, exit immediately
                if f.read(4) != b'%PDF':
                    return ""
            
            with open(path, 'rb') as file:
                reader = pypdf.PdfReader(file)
                num_pages = len(reader.pages)
                if num_pages == 0:
                    return ""
                
                text_parts = []
                total_chars = 0
                for page in reader.pages[:max_pages]:
                    page_text = page.extract_text() or ""
                    if page_text:
                        text_parts.append(page_text)
                        total_chars += len(page_text)
                        if total_chars >= max_chars:
                            break
                return "\n".join(text_parts)[:max_chars]
        except Exception:
            return ""

    def extract_text(self, path: Path) -> str:
        """
        Public entry point for text extraction.
        Detects file type and routes to the appropriate internal reader.
        """
        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                return self._read_pdf_text(path)
            elif suffix in {".txt", ".csv", ".rtf", ".md"}:
                return path.read_text(encoding="utf-8", errors="replace")
            return self._dirty_scrape(path)
        except Exception:
            return ""

    def extract_metadata(self, text: str = "", file_path: Optional[Path] = None) -> Dict[str, str]:
        """
        Extracts metadata from text and filename dynamically.
        If text is empty and file_path is provided, attempts dirty byte scraping.
        """
        meta = {}
        
        # --- 1. FILENAME-BASED PATTERNS ---
        if file_path:
            fname = file_path.name.upper()

            # Board / Academic Exams & Papers
            if any(k in fname for k in ["PART", "PAPER", "MEMO", "ANSWERS", "ESTATE"]):
                meta['entity'] = "LEGAL_BOARD_EXAMS"
                if "MEMO" in fname:
                    meta['sub_type'] = "Exam_Memo"
                elif "ANSWERS" in fname:
                    meta['sub_type'] = "Exam_Answers"
                else:
                    meta['sub_type'] = "Board_Exam_Paper"
                return self._finalize(meta)

            # Target Entity / Organization from filename: e.g. "...FOR_<Org>..." or "...AT_<Org>..."
            org_match = re.search(r'(?:FOR|AT)_(.*?)(?:_ATTORNEYS|_INC|_AND_ASSOCIATES|\.PDF|_\d|\d|$)', fname)
            if org_match:
                extracted_org = org_match.group(1).strip('_')
                if len(extracted_org) >= 3 and not extracted_org.isdigit():
                    meta['entity'] = extracted_org
                    meta['sub_type'] = "Application_Packet"
                    return self._finalize(meta)

        # Fallback: Dirty Scrape if no text and file path exists
        if not text and file_path:
            text = self._dirty_scrape(file_path)
            if text:
                meta['sub_type'] = "Scraped_From_Corrupt_File"

        if not text:
            return self._finalize(meta)

        # --- 2. CONTENT REFERENCE NUMBER ---
        for p in self.patterns['reference']:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                ref = match.group(1).strip().replace('/', '_').replace('\\', '_')
                meta['entity'] = f"RECOVERED_{ref}"
                return self._finalize(meta)
        
        # --- 3. CONTENT POSITION / TITLE ---
        for p in self.patterns['position']:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                pos = match.group(1).strip().upper().replace(' ', '_')
                meta['entity'] = f"RECOVERED_{pos}"
                return self._finalize(meta)

        # --- 4. FILENAME KEYWORD RESCUE ---
        if file_path and ('entity' not in meta):
            fname = file_path.name.upper()
            job_keywords = [
                'JUDGE', 'ADMIN', 'CLERK', 'PROSECUTOR', 'ATTORNEY', 'ADVISOR',
                'REGISTRAR', 'PRACTITIONER', 'ENGINEER', 'ANALYST', 'MANAGER',
                'CONSULTANT', 'DIRECTOR', 'SECRETARY', 'OFFICER'
            ]
            for job_key in job_keywords:
                if job_key in fname:
                    match = re.search(r'FOR_(.*?)(?:\.PDF|\d|$)', fname)
                    if match:
                        role = match.group(1).strip('_')
                        meta['entity'] = role
                        meta['sub_type'] = "Filename_Rescued"
                        return self._finalize(meta)
                    else:
                        meta['entity'] = f"POTENTIAL_{job_key}"
                        meta['sub_type'] = "Filename_Rescued"
                        return self._finalize(meta)

        return self._finalize(meta)

    def _finalize(self, meta: Dict[str, str]) -> Dict[str, str]:
        if 'entity' in meta:
            meta['entity'] = self._normalize_entity(meta['entity'])
        return meta

    def _normalize_entity(self, entity: str) -> str:
        """Collapses and sanitizes entity names into canonical, safe folder names."""
        if not entity:
            return entity
        
        norm = entity.upper()
        norm = re.sub(r"[^A-Z0-9_]", "_", norm) 
        norm = re.sub(r"_+", "_", norm)
        norm = norm.strip('_')

        # Canonical group mappings
        if any(x in norm for x in ['JUDGE', 'SECRETARY', 'JUSTICE']):
            return "JUDGES_SECRETARY"
        
        if any(x in norm for x in ['POTENTIAL_ATTORNEY', 'CANDIDATE_PRACTITIONER', 'CANDIDATE_ATTORNEY']):
            return "CANDIDATE_ATTORNEY"
            
        return norm

    def _dirty_scrape(self, path: Path) -> str:
        """Extracts printable ASCII sequences from corrupted or raw binary files."""
        try:
            with open(path, 'rb') as f:
                data = f.read(250000)
                tokens = re.findall(rb'[A-Za-z0-9/\s-]{4,}', data)
                return " ".join([m.decode('ascii', errors='ignore') for m in tokens])
        except Exception:
            return ""

    def classify_sub_type(self, path: Path, text: str) -> str:
        t_low = text.lower() if text else ""
        n_low = path.name.lower()
        if "z83" in t_low or "application for employment" in t_low:
            return "Z83"
        if "curriculum vitae" in t_low or "resume" in t_low or "cv" in n_low:
            return "CV"
        if "cover letter" in t_low or "cover" in n_low:
            return "CoverLetter"
        if "scraped_from_corrupt_file" in t_low:
            return "Recovered_Fragment"
        return "Supporting_Doc"

    def extract_from_filename(self, filename: str) -> Dict[str, str]:
        """Legacy stub for filename extraction compatibility."""
        return {}