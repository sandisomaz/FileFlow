"""
Unified Extractor for FileFlow V8
MERGED: extractor.py + text_extractor.py into single module
ADDED: Better error handling and timeout protection
"""

import re
from typing import Dict, Optional, List
from pathlib import Path
import pypdf
import concurrent.futures


class UnifiedExtractor:
    """
    All-in-one metadata extraction and classification engine.
    Handles both filename-based and content-based extraction.
    """
    
    def __init__(self):
        # Compiled regex patterns for Z83 forms
        self.patterns = {
            'position': [
                r'(?:Position for which you are applying|Position|POSITION).*?[:\s]+([A-Za-z\s&]{5,100}?)[\r\n]',
                r'(JUDGE\'S SECRETARY|STATE LAW ADVISOR|LEGAL ADMIN OFFICER|CANDIDATE ATTORNEY)',
                r'(?:Position|Post).*?:\s*([A-Z\s&]{5,})'
            ],
            'department': [
                r'(?:Department|DEPARTMENT).*?:\s*([A-Z\s&]{5,})'
            ],
            'reference': [
                r'(?:Reference number|Reference|Ref)\s*[:#\-]?\s*([A-Z0-9/]{5,})',
                r'(?:REFERENCE|Post Number).*?:\s*([A-Z0-9/\-]{4,})'
            ],
            'applicant': [
                r'(?:Surname and Full names|SURNAME).*?:\s*([A-Za-z\s]+?)(?:\n|Date of Birth)'
            ]
        }
    
    def _read_pdf_text(self, path: Path, max_pages: int = 3, timeout: int = 5) -> str:
        """
        Safely reads PDF text with timeout protection.
        Returns empty string on failure/timeout.
        """
        try:
            # Quick size check
            if path.stat().st_size < 100:  # < 100 bytes
                return ""
            
            # Use process pool for safety
            with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._pdf_worker, str(path), max_pages)
                try:
                    return future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    return ""
                except Exception:
                    return ""
        except Exception:
            return ""
    
    @staticmethod
    def _pdf_worker(path_str: str, max_pages: int) -> str:
        """Worker function for process pool."""
        try:
            path = Path(path_str)
            with open(path, 'rb') as file:
                reader = pypdf.PdfReader(file)
                text = ""
                
                # Safe page count
                try:
                    num_pages = len(reader.pages)
                except (RecursionError, Exception):
                    return ""
                
                for i in range(min(num_pages, max_pages)):
                    try:
                        extracted = reader.pages[i].extract_text()
                        if extracted:
                            text += extracted
                    except (RecursionError, Exception):
                        continue
                
                return text
        except Exception:
            return ""
    
    def classify_sub_type(self, path: Path, text: str = "") -> str:
        """
        Determine document SubType with multi-layered logic.
        Priority: Filename patterns > Content analysis > Extension fallback
        """
        name_lower = path.name.lower()
        
        # PRIORITY 0: Application Summary (ANCHOR FILE)
        if "application_for" in name_lower:
            return "AppSummary"
            
        # PRIORITY 0.5: Z83 Stamped (Special Case)
        if "z83" in name_lower and "stamped" in name_lower:
            return "Z83_Stamped"
        
        # PRIORITY 1: Auto-read PDF text if not provided
        if not text and path.suffix.lower() == '.pdf':
            text = self._read_pdf_text(path)
        
        text_lower = text.lower() if text else ""
        
        # PRIORITY 2: Content Analysis
        if text_lower:
            if "z83" in text_lower and "republic of south africa" in text_lower:
                return "Z83"
            
            cv_signals = ["curriculum vitae", "resume", "professional summary", "work experience", "education"]
            if any(sig in text_lower for sig in cv_signals):
                return "CV"
            
            cl_signals = ["application for the post", "cover letter", "dear sir", "dear madam", "hiring manager"]
            if any(sig in text_lower for sig in cl_signals):
                return "CoverLetter"
            
            cert_signals = ["certificate", "degree", "academic record", "transcript", "statement of results", 
                           "identity document", "id number", "driver", "license"]
            if any(sig in text_lower for sig in cert_signals):
                return "Certificate"
        
        # PRIORITY 3: Filename Analysis (Fallback)
        if "z83" in name_lower:
            return "Z83"
        if any(kw in name_lower for kw in ["cv", "resume", "curriculum"]):
            return "CV"
        if "cover" in name_lower and "letter" in name_lower:
            return "CoverLetter"
        if any(kw in name_lower for kw in ["cert", "transcript", "degree", "diploma", "drivers", "license", "id_copy", "identity"]):
            return "Certificate"
        
        # PRIORITY 4: Project/Code Files
        code_extensions = ['.py', '.js', '.java', '.cpp', '.html', '.css', '.json', '.xml']
        if path.suffix.lower() in code_extensions or 'requirements.txt' in name_lower:
            return "ProjectFile"
        
        # PRIORITY 5: Educational Materials
        if any(x in name_lower for x in ['circular', 'guide', 'study', 'tutorial', 'lecture', 'notes', 'exam', 'assignment']):
            return "Educational"
        
        # PRIORITY 6: File Extension Fallback
        if path.suffix.lower() == '.docx':
            # Check for known applicant names
            if any(name in name_lower for name in ['sandiso', 'mazibuko', 'rex', 'stone']):
                return "CV"
        
        return "Document"
    
    def extract_metadata(self, file_path: Path) -> Dict[str, str]:
        """
        Extracts metadata from PDF files.
        Returns dict with position, reference, applicant, etc.
        """
        if file_path.suffix.lower() != '.pdf':
            return {}
        
        text = self._read_pdf_text(file_path)
        if not text:
            return {}
        
        metadata = {}
        
        # 1. Reference Number (Highest Priority for Identity)
        ref = self._find_match(text, self.patterns['reference'])
        if ref:
            clean_ref = ref.strip().upper().replace(' ', '_').replace('-', '_').replace('/', '_')
            metadata['reference'] = f"REF_{clean_ref}"
            metadata['entity'] = metadata['reference']
        
        # 2. Position Identification
        pos = self._find_match(text, self.patterns['position'])
        if pos:
            clean_pos = pos.strip().upper().replace(' ', '_').replace('&', 'AND').replace('/', '_')
            metadata['position'] = clean_pos
            if 'entity' not in metadata:
                metadata['entity'] = clean_pos
        
        # 3. Applicant Name
        applicant = self._find_match(text, self.patterns['applicant'])
        if applicant:
            metadata['applicant'] = applicant.strip().upper().replace(' ', '_')
            
        # 4. Department
        dept = self._find_match(text, self.patterns['department'])
        if dept:
            metadata['department'] = dept.strip().upper()
            
        return metadata
    
    def _find_match(self, text: str, patterns: List[str]) -> Optional[str]:
        """Helper to find first matching pattern in text."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                if match.groups():
                    return match.group(1)
                return match.group(0)
        return None
    
    def extract_from_filename(self, filename: str) -> Dict[str, str]:
        """
        Extracts entity info from filename patterns.
        Handles V8 organized files, job packets, firm applications, etc.
        """
        # 0. Handle V8 Organized Filenames (Prevention of regressive re-extraction)
        v8_match = re.search(
            r'^(?P<entity>.+)_(?P<subtype>Z83|Z83_Stamped|CV|CoverLetter|Certificate|AppSummary|ProjectFile|Document|Educational)_\d{8}_v\d+',
            filename
        )
        if v8_match:
            return {
                'entity': v8_match.group('entity'),
                'sub_type': v8_match.group('subtype'),
                'type': 'v8_managed'
            }

        # 1. Handle generic filenames
        if "in_a_government" in filename.lower():
            return {'type': 'generic_government', 'entity': 'in_a_government'}

        # 2. Job Application Packet Anchor
        job_match = re.search(
            r'(?:Sandiso_Mazibuko|Rex_Stone)_Application_for_(?P<job>.+)_at',
            filename,
            re.IGNORECASE
        )
        if job_match:
            job = job_match.group('job').strip().replace(' ', '_')
            return {'entity': job, 'type': 'job_packet'}
        
        # 3. Standalone Firm Application
        firm_match = re.search(
            r'CV_(?:Sandiso_Mazibuko|Rex_Stone)_for_(?P<firm>.+)_',
            filename,
            re.IGNORECASE
        )
        if firm_match:
            firm = firm_match.group('firm').strip().replace(' ', '_')
            return {'entity': firm, 'type': 'firm_application'}
        
        # 4. Extract known applicant names
        name_lower = filename.lower()
        if "sandiso" in name_lower or "mazibuko" in name_lower:
            return {'applicant': 'Sandiso_Mazibuko'}
        if "rex" in name_lower and "stone" in name_lower:
            return {'applicant': 'Rex_Stone'}
        
        return {}
    
    def extract_reference_number(self, path: Path) -> Optional[str]:
        """Quick reference number extraction."""
        meta = self.extract_metadata(path)
        return meta.get('reference')
