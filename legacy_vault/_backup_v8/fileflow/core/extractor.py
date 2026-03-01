import re
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
import PyPDF2
from fileflow.config import Config

class ContextExtractor:
    @staticmethod
    def extract_date_from_string(text: str) -> Optional[datetime]:
        match = re.search(r'(202[3-9])(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', text)
        if match:
            try:
                return datetime.strptime(match.group(0), "%Y%m%d")
            except: pass
        return None

    @staticmethod
    def extract_from_filename(filename: str) -> Dict[str, str]:
        applicant = None
        position = None
        fname_lower = filename.lower()
        
        if "rex" in fname_lower: applicant = "Rex_Stone"
        elif "sandiso" in fname_lower: applicant = "Sandiso_Mazibuko"
        
        for key, value in Config.FOLDER_JOB_MAP.items():
            if key.lower() in fname_lower:
                position = value
                break
        
        return {"applicant": applicant, "position": position}

    @staticmethod
    def analyze_path_context(file_path: Path) -> Dict[str, Any]:
        parent = file_path.parent.name
        grandparent = file_path.parent.parent.name
        
        inferred_position = None
        inferred_date = None

        for key, value in Config.FOLDER_JOB_MAP.items():
            if key in parent.upper():
                inferred_position = value
                break
        
        if not inferred_position:
            for firm in Config.LAW_FIRMS:
                if firm in parent.upper():
                    inferred_position = "Candidate_Attorney"
                    break

        if not inferred_position and "DEPARTMENT" in parent.upper():
            clean_name = re.sub(r'^\d+_', '', parent)
            inferred_position = f"App_{clean_name[:30]}"

        date_found = ContextExtractor.extract_date_from_string(parent)
        if not date_found:
            date_found = ContextExtractor.extract_date_from_string(grandparent)
        
        if date_found:
            inferred_date = date_found

        return {
            "position": inferred_position,
            "date": inferred_date
        }

class PDFExtractor:
    @staticmethod
    def extract_metadata(pdf_path: Path) -> Optional[Dict[str, Any]]:
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                # Read first few pages
                for i in range(min(3, len(reader.pages))):
                    text += reader.pages[i].extract_text()
            
            metadata = {}
            
            # 1. Position Extraction
            # Check known mappings first
            text_upper = text.upper()
            for key, value in Config.FOLDER_JOB_MAP.items():
                if key.replace('_', ' ') in text_upper:
                    metadata['position'] = value
                    break
            
            if 'position' not in metadata:
                 # Regex fallback for Z83/Generic
                pos_match = re.search(
                    r'(?:Position for which you are applying|JUDGE\'S SECRETARY|STATE LAW ADVISOR|LEGAL ADMIN OFFICER)',
                    text, re.IGNORECASE
                )
                if pos_match:
                     # Refine this if needed, for now trust the map more
                     pass

            # 2. Applicant Extraction
            if "REX" in text_upper and "STONE" in text_upper: metadata['applicant'] = "Rex_Stone"
            elif "SANDISO" in text_upper: metadata['applicant'] = "Sandiso_Mazibuko"
            
            # Z83 Name extraction fallback
            if 'applicant' not in metadata:
                name_pattern = r'(?:Surname and Full names|SURNAME).*?:\s*([A-Za-z\s]+?)(?:\n|Date of Birth)'
                name_match = re.search(name_pattern, text)
                if name_match:
                    name = name_match.group(1).strip()
                    metadata['applicant'] = re.sub(r'\s+', '_', name)

            return metadata
        except Exception:
            return None

class UnifiedExtractor:
    @staticmethod
    def get_metadata(file_path: Path) -> Dict[str, Any]:
        final_meta = {
            'applicant': "Unknown_Applicant",
            'position': "General_Application",
            'source': "default",
            'final_date': None
        }

        # 1. Filename Analysis
        name_meta = ContextExtractor.extract_from_filename(file_path.name)
        if name_meta['applicant']: final_meta['applicant'] = name_meta['applicant']
        if name_meta['position']: 
            final_meta['position'] = name_meta['position']
            final_meta['source'] = "filename"

        # 2. PDF Content Analysis (Stronger signal for Position/Applicant)
        if file_path.suffix.lower() == '.pdf':
            pdf_meta = PDFExtractor.extract_metadata(file_path)
            if pdf_meta:
                if pdf_meta.get('applicant'): final_meta['applicant'] = pdf_meta['applicant']
                if pdf_meta.get('position'): 
                    final_meta['position'] = pdf_meta['position']
                    final_meta['source'] = "pdf_content"

        # 3. Folder Context Analysis (Fallback for Position, Primary for Date)
        context = ContextExtractor.analyze_path_context(file_path)
        
        if final_meta['position'] == "General_Application" and context['position']:
            final_meta['position'] = context['position']
            final_meta['source'] = "folder_context"

        # Date priority: Context > File Mod Time (handled by scanner)
        final_meta['final_date'] = context['date']
        
        return final_meta
