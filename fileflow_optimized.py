#!/usr/bin/env python3
"""
FileFlow Strict - Intelligent Legal Job Application Organizer
Features:
1. Strict Filtering (Ignores bank statements, ebooks, etc.)
2. Report Generation (Saves scan_results.txt instead of spamming console)
3. Smart Versioning
"""

import os
import shutil
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import PyPDF2
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()

# ============================================================================
# ⚙️ CONFIGURATION - THE FILTERING RULES
# ============================================================================

# 1. Folders to IGNORE completely
IGNORED_DIRS = {
    '.venv', 'venv', 'env', '__pycache__', '.git', 'node_modules', 
    '.vscode', 'site-packages', 'Lib', 'Scripts', 'System Volume Information'
}

# 2. File Extensions to scan
TARGET_EXTENSIONS = {'.pdf', '.docx', '.doc'}

# 3. STRICT KEYWORDS: File MUST contain one of these to be considered
REQUIRED_KEYWORDS = [
    "cv", "resume", "curriculum", "vitae", 
    "z83", "application", "cover", "letter", 
    "candidate", "attorney", "judge", "secretary", "legal"
]

# 4. JUNK WORDS: If file has these, IGNORE IT (Bank statements, etc.)
JUNK_KEYWORDS = [
    "statement", "invoice", "receipt", "lease", "agreement", 
    "contract", "payment", "study guide", "textbook", "exam", 
    "tutorial", "assignment", "transcript", "ticket"
]

# ============================================================================
# 🧠 METADATA INTELLIGENCE
# ============================================================================

class MetadataExtractor:
    @staticmethod
    def extract_from_filename(filename: str) -> Dict[str, str]:
        """Guess details from filename."""
        applicant = "Unknown_Applicant"
        position = "General_Application"
        fname_lower = filename.lower()
        
        # 1. Detect Applicant
        if "rex" in fname_lower and "stone" in fname_lower:
            applicant = "Rex_Stone"
        elif "sandiso" in fname_lower:
            applicant = "Sandiso_Mazibuko"
        
        # 2. Detect Position
        if "judge" in fname_lower:
            position = "Judges_Secretary"
        elif "legal_admin" in fname_lower:
            position = "Legal_Admin_Officer"
        elif "state_law" in fname_lower:
            position = "State_Law_Advisor"
        elif "candidate" in fname_lower:
            position = "Candidate_Attorney"
        
        return {"applicant": applicant, "position": position, "source": "filename"}

    @staticmethod
    def extract_from_pdf_content(pdf_path: Path) -> Optional[Dict[str, str]]:
        """Reads PDF text to find Z83 details."""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                # Read first 2 pages
                for i in range(min(len(reader.pages), 2)): 
                    text += reader.pages[i].extract_text()
            
            text_upper = text.upper()
            metadata = {}
            
            # Detect Position
            if 'JUDGE' in text_upper and 'SECRETARY' in text_upper:
                metadata['position'] = 'Judges_Secretary'
            elif 'STATE LAW ADVISOR' in text_upper:
                metadata['position'] = 'State_Law_Advisor'
            elif 'LEGAL ADMIN' in text_upper:
                metadata['position'] = 'Legal_Admin_Officer'
            else:
                return None # Failed to find specific position

            # Detect Applicant
            if "REX" in text_upper and "STONE" in text_upper:
                metadata['applicant'] = "Rex_Stone"
            elif "SANDISO" in text_upper:
                metadata['applicant'] = "Sandiso_Mazibuko"
            else:
                metadata['applicant'] = "Unknown_Applicant"

            metadata['source'] = "pdf_content"
            return metadata
        except:
            return None

    @staticmethod
    def get_metadata(file_path: Path) -> Dict[str, str]:
        """Master function combines PDF content and Filename analysis."""
        meta = None
        if file_path.suffix.lower() == '.pdf':
            meta = MetadataExtractor.extract_from_pdf_content(file_path)
        
        if not meta:
            meta = MetadataExtractor.extract_from_filename(file_path.name)
        return meta

# ============================================================================
# 🔍 SCANNER
# ============================================================================

class FileScanner:
    @staticmethod
    def is_relevant_file(filename: str) -> bool:
        """Decides if a file is worth looking at."""
        name_lower = filename.lower()

        # 1. Check Junk Keywords (Fail fast)
        for junk in JUNK_KEYWORDS:
            if junk in name_lower:
                return False
        
        # 2. Check Required Keywords
        for req in REQUIRED_KEYWORDS:
            if req in name_lower:
                return True
        
        return False

    @staticmethod
    def scan_strict(folders: List[str], date_from: str, date_to: str) -> List[Dict[str, Any]]:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to = datetime.strptime(date_to, "%Y-%m-%d")
        found_files = []
        
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
            BarColumn(), console=console
        ) as progress:
            
            for folder_str in folders:
                folder = Path(folder_str)
                if not folder.exists(): continue
                
                task = progress.add_task(f"Scanning {folder.name}...", total=None)
                
                # Scan Logic
                for root, dirs, files in os.walk(folder, topdown=True):
                    # Skip ignored folders
                    dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith('.')]
                    
                    for filename in files:
                        file_path = Path(root) / filename
                        
                        # 1. Extension Check
                        if file_path.suffix.lower() not in TARGET_EXTENSIONS: continue
                        
                        # 2. Strict Name Check (Skip bank statements etc)
                        if not FileScanner.is_relevant_file(filename): continue

                        try:
                            stat = file_path.stat()
                            mod_time = datetime.fromtimestamp(stat.st_mtime)
                            
                            # 3. Date Check
                            if dt_from <= mod_time <= dt_to:
                                meta = MetadataExtractor.get_metadata(file_path)
                                found_files.append({
                                    'path': file_path, 'name': filename,
                                    'modified': mod_time, 'metadata': meta
                                })
                                progress.update(task, description=f"Found: {filename}")
                        except: pass
        return found_files

# ============================================================================
# 📄 REPORTING
# ============================================================================

def save_report(files: List[Dict], dest_base: Path):
    report_path = Path("scan_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"SCAN REPORT - {datetime.now()}\n")
        f.write(f"Total Files Found: {len(files)}\n")
        f.write("="*80 + "\n")
        f.write(f"{'FILENAME':<50} | {'APPLICANT':<20} | {'POSITION':<30} | {'DATE'}\n")
        f.write("-" * 120 + "\n")
        
        for file in files:
            meta = file['metadata']
            f.write(f"{file['name'][:48]:<50} | {meta['applicant']:<20} | {meta['position']:<30} | {file['modified'].strftime('%Y-%m-%d')}\n")
            
    console.print(f"\n[green]📝 Report saved to: [bold]{report_path.resolve()}[/bold][/green]")
    console.print("[dim]Open this file to check what will be moved before confirming.[/dim]")

# ============================================================================
# 📦 ORGANIZER
# ============================================================================

class Organizer:
    @staticmethod
    def execute(files: List[Dict], dest_base: Path):
        success = 0
        fails = 0
        
        with Progress(
            SpinnerColumn(), TextColumn("Moving files..."),
            BarColumn(), console=console
        ) as progress:
            task = progress.add_task("Moving...", total=len(files))
            
            for f in files:
                meta = f['metadata']
                
                # Create Folder: e.g. Applications/Judges_Secretary
                target_folder = dest_base / meta['position']
                target_folder.mkdir(parents=True, exist_ok=True)
                
                # Generate Name: Sandiso_Mazibuko_Judges_Secretary_20250911_v1.pdf
                date_str = f['modified'].strftime("%Y%m%d")
                base_name = f"{meta['applicant']}_{meta['position']}_{date_str}"
                
                # Versioning
                existing = list(target_folder.glob(f"{base_name}_v*.pdf"))
                version = len(existing) + 1
                
                new_name = f"{base_name}_v{version}{f['path'].suffix}"
                dest_path = target_folder / new_name
                
                try:
                    shutil.copy2(f['path'], dest_path)
                    success += 1
                except Exception:
                    fails += 1
                progress.advance(task)
                
        return success, fails

# ============================================================================
# 🚀 MAIN
# ============================================================================

def main():
    console.clear()
    console.print("[bold cyan]🚀 FileFlow Strict Mode[/bold cyan]")
    console.print("[dim]Filters out junk (Statements, Ebooks, etc) & Generates Reports[/dim]\n")

    # 1. Config
    default_folders = [r"C:\Users\sandi\Desktop\Career assistant", r"C:\Users\sandi\Downloads"]
    console.print(f"Scan locations: [yellow]{', '.join([Path(p).name for p in default_folders])}[/yellow]")
    
    if not Confirm.ask("Use these folders?", default=True):
        folders = []
        while True:
            p = Prompt.ask("Path (Enter to finish)")
            if not p: break
            folders.append(p)
    else:
        folders = default_folders

    console.print()
    date_from = Prompt.ask("Start Date", default="2024-01-01")
    date_to = Prompt.ask("End Date", default=datetime.now().strftime("%Y-%m-%d"))
    dest_path = Prompt.ask("Destination", default=r"C:\Users\sandi\Desktop\Applications_Sorted")
    dest = Path(dest_path)

    # 2. Scan
    console.print("\n[bold]Scanning...[/bold]")
    files = FileScanner.scan_strict(folders, date_from, date_to)
    
    if not files:
        console.print("[red]No job applications found.[/red]")
        return

    # 3. Report
    save_report(files, dest)
    
    console.print(f"\n[bold cyan]Found {len(files)} potential applications.[/bold cyan]")
    
    # 4. Execute
    if Confirm.ask("Proceed with organization?", default=False):
        s, f = Organizer.execute(files, dest)
        console.print(f"\n[bold green]Done! {s} moved, {f} failed.[/bold green]")

if __name__ == "__main__":
    main()