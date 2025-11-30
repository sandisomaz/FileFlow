#!/usr/bin/env python3
"""
FileFlow Select (v6) - The "House Cleaning" Tool
Features:
1. Interactive Subfolder Selection (Pick which "room" to clean)
2. Local Staging: Creates _Organized_Output INSIDE the selected subfolder
3. Genius Intelligence: Extracts dates and jobs from folder structures
"""

import os
import shutil
import re
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import PyPDF2
import json
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.table import Table

console = Console(width=100) 

# ============================================================================
# ⚙️ CONFIGURATION
# ============================================================================

IGNORED_SYSTEM_DIRS = {
    '.venv', 'venv', 'env', '__pycache__', '.git', 'node_modules', 
    '.vscode', 'site-packages', 'Lib', 'Scripts', 'assets', 'images', 'css', 'js',
    'reports', '_Organized_Output', 'System Volume Information'
}

TARGET_EXTENSIONS = {'.pdf', '.docx', '.doc'}

KEYWORDS_NEGATIVE = [
    "statement", "invoice", "receipt", "lease", "agreement", 
    "contract", "payment", "study guide", "textbook", "exam", 
    "tutorial", "assignment", "transcript", "ticket", "cheque",
    "curriculum_plan", "id_copy", "matric", "template", "flyer",
    "udemy", "course resource"
]

FOLDER_JOB_MAP = {
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

LAW_FIRMS = [
    "ENS", "WEBBER", "BOWMANS", "CLIFFE", "DEKKER", "HOFMEYR", 
    "WERKSMANS", "NORTON", "ROSE", "FASKEN", "HOGAN", "LOVELLS",
    "MACROBERT", "ADAMS", "SPOOR", "FISHER", "STRAUSS", "DALY",
    "ATTORNEYS", "INC", "LAW"
]

# ============================================================================
# 🧠 INTELLIGENT EXTRACTOR
# ============================================================================

class ContextExtractor:
    @staticmethod
    def extract_from_pdf_content(pdf_path: Path) -> Optional[Dict[str, str]]:
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = reader.pages[0].extract_text() if len(reader.pages) > 0 else ""
            
            text_upper = text.upper()
            metadata = {}
            
            for key, value in FOLDER_JOB_MAP.items():
                if key.replace('_', ' ') in text_upper:
                    metadata['position'] = value
                    break
            
            if "REX" in text_upper and "STONE" in text_upper: metadata['applicant'] = "Rex_Stone"
            elif "SANDISO" in text_upper: metadata['applicant'] = "Sandiso_Mazibuko"
            
            return metadata if 'position' in metadata else None
        except: return None

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
        
        for key, value in FOLDER_JOB_MAP.items():
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

        for key, value in FOLDER_JOB_MAP.items():
            if key in parent.upper():
                inferred_position = value
                break
        
        if not inferred_position:
            for firm in LAW_FIRMS:
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

    @staticmethod
    def get_metadata(file_path: Path) -> Dict[str, Any]:
        final_meta = {
            'applicant': "Unknown_Applicant",
            'position': "General_Application",
            'source': "default",
            'final_date': None
        }

        name_meta = ContextExtractor.extract_from_filename(file_path.name)
        if name_meta['applicant']: final_meta['applicant'] = name_meta['applicant']
        if name_meta['position']: 
            final_meta['position'] = name_meta['position']
            final_meta['source'] = "filename"

        if file_path.suffix.lower() == '.pdf':
            pdf_meta = ContextExtractor.extract_from_pdf_content(file_path)
            if pdf_meta:
                if pdf_meta.get('applicant'): final_meta['applicant'] = pdf_meta['applicant']
                if pdf_meta.get('position'): 
                    final_meta['position'] = pdf_meta['position']
                    final_meta['source'] = "pdf_content"

        context = ContextExtractor.analyze_path_context(file_path)
        
        if final_meta['position'] == "General_Application" and context['position']:
            final_meta['position'] = context['position']
            final_meta['source'] = "folder_context"

        final_meta['final_date'] = context['date']
        
        return final_meta

# ============================================================================
# 🔍 SCANNER
# ============================================================================

class TacticalScanner:
    @staticmethod
    def is_wanted_file(filename: str) -> bool:
        name_lower = filename.lower()
        for junk in KEYWORDS_NEGATIVE:
            if junk in name_lower: return False
        return True 

    @staticmethod
    def scan_specific_folder(root_folder: Path) -> List[Dict]:
        """Scans ONE specific folder recursively."""
        files_found = []
        
        # We create a new progress bar for EACH folder we scan
        with Progress(
            SpinnerColumn(), 
            TextColumn("[bold cyan]Scanning...[/bold cyan]"),
            BarColumn(bar_width=40),
            TextColumn("[dim]{task.description}[/dim]"),
            console=console,
            transient=True 
        ) as progress:
            task = progress.add_task("Initializing...", total=None)
            
            for root, dirs, files in os.walk(root_folder, topdown=True):
                dirs[:] = [d for d in dirs if d not in IGNORED_SYSTEM_DIRS and not d.startswith('.')]
                
                folder_name = Path(root).name
                display_name = (folder_name[:30] + '..') if len(folder_name) > 30 else folder_name
                progress.update(task, description=f"📂 {display_name}")
                
                for filename in files:
                    file_path = Path(root) / filename
                    
                    if file_path.suffix.lower() not in TARGET_EXTENSIONS: continue
                    if not TacticalScanner.is_wanted_file(filename): continue

                    try:
                        stat = file_path.stat()
                        phys_date = datetime.fromtimestamp(stat.st_mtime)
                        meta = ContextExtractor.get_metadata(file_path)
                        final_date = meta['final_date'] if meta['final_date'] else phys_date
                        
                        files_found.append({
                            'path': file_path, 
                            'name': filename,
                            'date': final_date,
                            'metadata': meta
                        })
                    except: pass
        return files_found

# ============================================================================
# 📄 REPORTING & LOGGING
# ============================================================================

def generate_folder_report(files: List[Dict], folder_name: str) -> Path:
    """Generates a report specific to the folder being processed."""
    report_dir = Path.cwd() / "reports"
    report_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"Log_{folder_name}_{timestamp}.txt"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"SCAN REPORT FOR: {folder_name}\n")
        f.write(f"TOTAL FILES    : {len(files)}\n")
        f.write("="*100 + "\n")
        f.write(f"{'FILENAME':<50} | {'APPLICANT':<15} | {'DETECTED JOB':<25} | {'SMART DATE'}\n")
        f.write("-" * 100 + "\n")
        
        for file in files:
            meta = file['metadata']
            date_str = file['date'].strftime("%Y-%m-%d")
            app_name = meta.get('applicant', 'Unknown')
            job_name = meta.get('position', 'General')
            f.write(f"{file['name'][:45]:<50} | {app_name:<15} | {job_name:<25} | {date_str}\n")
            
    return report_file

# ============================================================================
# 📦 ORGANIZER
# ============================================================================

def organize_files(files: List[Dict], root_folder: Path):
    # OUTPUT goes INSIDE the folder being scanned
    output_base = root_folder / "_Organized_Output"
    output_base.mkdir(exist_ok=True)
    success_count = 0
    
    with Progress(
        SpinnerColumn(), 
        TextColumn("[bold green]Staging Files...[/bold green]"),
        BarColumn(bar_width=40),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Copying...", total=len(files))
        
        for f in files:
            meta = f['metadata']
            date_obj = f['date']
            clean_job = re.sub(r'[^\w\-_]', '_', meta.get('position', 'General'))
            
            # Create Job Subfolder (e.g. _Organized_Output/Judges_Secretary)
            dest_folder = output_base / clean_job
            dest_folder.mkdir(parents=True, exist_ok=True)
            
            date_str = date_obj.strftime("%Y%m%d")
            applicant = meta.get('applicant', 'Unknown')
            base_name = f"{applicant}_{clean_job}_{date_str}"
            
            # Versioning
            existing = list(dest_folder.glob(f"{base_name}_v*.pdf"))
            version = len(existing) + 1
            
            new_name = f"{base_name}_v{version}{f['path'].suffix}"
            dest_path = dest_folder / new_name
            
            try:
                shutil.copy2(f['path'], dest_path)
                success_count += 1
            except: pass
            progress.advance(task)
            
    return output_base, success_count

# ============================================================================
# 🎯 SELECTOR UI
# ============================================================================

def select_subfolders(root: Path) -> List[Path]:
    """Interactive subfolder selector."""
    all_items = [d for d in root.iterdir() if d.is_dir() and d.name not in IGNORED_SYSTEM_DIRS]
    all_items.sort(key=lambda x: x.name)
    
    if not all_items:
        return [root] 

    console.print(f"\n[bold]Found {len(all_items)} folders in {root.name}:[/bold]")
    
    table = Table(show_header=False, box=None)
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Folder Name", style="yellow")
    
    for i, folder in enumerate(all_items, 1):
        table.add_row(str(i), folder.name)
    
    console.print(table)
    console.print("\n[dim]Enter numbers separated by commas (e.g. '1,3,5') or 'all'[/dim]")
    
    selection = Prompt.ask("Select folders to process")
    
    selected_folders = []
    if selection.lower().strip() == 'all':
        return all_items
    
    try:
        indices = [int(x.strip()) for x in selection.split(',') if x.strip().isdigit()]
        for i in indices:
            if 1 <= i <= len(all_items):
                selected_folders.append(all_items[i-1])
    except:
        console.print("[red]Invalid selection.[/red]")
        return []
        
    return selected_folders

# ============================================================================
# 🚀 MAIN
# ============================================================================

def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]FileFlow Select (v6)[/bold cyan]"))
    
    target_str = Prompt.ask("Folder path to scan", default=r"C:\Users\sandi\Desktop\Courses")
    if not target_str: return
    root_folder = Path(target_str.strip('"').strip("'"))
    
    if not root_folder.exists():
        console.print("[red]Folder not found[/red]")
        return

    # 1. Select Folders
    folders_to_process = select_subfolders(root_folder)
    if not folders_to_process: return

    console.print(f"\n[bold]Processing {len(folders_to_process)} folders...[/bold]\n")

    # 2. Loop through each selected folder
    for folder in folders_to_process:
        console.print(f"[bold cyan]Room: {folder.name}[/bold cyan]")
        
        # Scan
        files = TacticalScanner.scan_specific_folder(folder)
        if not files:
            console.print(f"  [yellow]No files found in {folder.name}[/yellow]")
            continue
            
        # Report
        report = generate_folder_report(files, folder.name)
        console.print(f"  [green]✓ Found {len(files)} files.[/green] Report: {report.name}")
        
        # Confirm & Action
        if Confirm.ask(f"  Centralize these {len(files)} files into '{folder.name}/_Organized_Output'?", default=True):
            out, count = organize_files(files, folder)
            console.print(f"  [bold green]✓ {count} files centralized.[/bold green]")
        else:
            console.print("  [dim]Skipped.[/dim]")
        
        console.print("-" * 50)

    console.print("\n[bold green]✨ Batch Processing Complete![/bold green]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Cancelled.[/bold red]")