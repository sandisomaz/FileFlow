#!/usr/bin/env python3
"""
FileFlow Granular (v3)
- ⏱️ High-Precision Timer added
- 📂 Saves reports to local 'reports' folder (keeps target clean)
- 📊 Professional System Log format
"""

import os
import shutil
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import PyPDF2
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel

# Initialize Console with soft wrapping prevention
console = Console(width=100) 

# ============================================================================
# ⚙️ CONFIGURATION
# ============================================================================

IGNORED_SYSTEM_DIRS = {
    '.venv', 'venv', 'env', '__pycache__', '.git', 'node_modules', 
    '.vscode', 'site-packages', 'Lib', 'Scripts', 'assets', 'images', 'css', 'js',
    'reports', '_Organized_Output' # Don't scan our own output
}

TARGET_EXTENSIONS = {'.pdf', '.docx', '.doc'}

KEYWORDS_POSITIVE = [
    "cv", "resume", "curriculum", "vitae", 
    "z83", "application", "cover", "letter", 
    "candidate", "attorney", "judge", "secretary", 
    "legal", "clerk", "internship", "prosecutor"
]

KEYWORDS_NEGATIVE = [
    "statement", "invoice", "receipt", "lease", "agreement", 
    "contract", "payment", "study guide", "textbook", "exam", 
    "tutorial", "assignment", "transcript", "ticket", "cheque",
    "curriculum_plan", "id_copy", "matric", "template", "flyer"
]

# ============================================================================
# 🧠 METADATA EXTRACTION
# ============================================================================

class MetadataExtractor:
    @staticmethod
    def extract_from_filename(filename: str) -> Dict[str, str]:
        applicant = "Unknown_Applicant"
        position = "General_Application"
        fname_lower = filename.lower()
        
        if "rex" in fname_lower: applicant = "Rex_Stone"
        elif "sandiso" in fname_lower: applicant = "Sandiso_Mazibuko"
        elif "lesedi" in fname_lower: applicant = "Lesedi"
        
        if "judge" in fname_lower: position = "Judges_Secretary"
        elif "legal_admin" in fname_lower: position = "Legal_Admin_Officer"
        elif "state_law" in fname_lower: position = "State_Law_Advisor"
        elif "candidate" in fname_lower: position = "Candidate_Attorney"
        elif "prosecutor" in fname_lower: position = "Public_Prosecutor"
        elif "clerk" in fname_lower: position = "Clerk"
        
        return {"applicant": applicant, "position": position, "source": "filename"}

    @staticmethod
    def extract_from_pdf_content(pdf_path: Path) -> Optional[Dict[str, str]]:
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                if len(reader.pages) > 0:
                    text = reader.pages[0].extract_text().upper()
            
            metadata = {}
            if 'JUDGE' in text and 'SECRETARY' in text: metadata['position'] = 'Judges_Secretary'
            elif 'STATE LAW ADVISOR' in text: metadata['position'] = 'State_Law_Advisor'
            elif 'LEGAL ADMIN' in text: metadata['position'] = 'Legal_Admin_Officer'
            elif 'CANDIDATE' in text and 'ATTORNEY' in text: metadata['position'] = 'Candidate_Attorney'
            else: return None 

            if "REX" in text and "STONE" in text: metadata['applicant'] = "Rex_Stone"
            elif "SANDISO" in text: metadata['applicant'] = "Sandiso_Mazibuko"
            else: metadata['applicant'] = "Unknown_Applicant"
            
            metadata['source'] = "pdf_content"
            return metadata
        except: return None

    @staticmethod
    def get_metadata(file_path: Path) -> Dict[str, str]:
        meta = None
        if file_path.suffix.lower() == '.pdf':
            meta = MetadataExtractor.extract_from_pdf_content(file_path)
        if not meta:
            meta = MetadataExtractor.extract_from_filename(file_path.name)
        return meta

# ============================================================================
# 🔍 SCANNER
# ============================================================================

class TacticalScanner:
    @staticmethod
    def is_wanted_file(filename: str) -> bool:
        name_lower = filename.lower()
        for junk in KEYWORDS_NEGATIVE:
            if junk in name_lower: return False
        for req in KEYWORDS_POSITIVE:
            if req in name_lower: return True
        return False

    @staticmethod
    def scan_folder(root_folder: Path) -> Dict[str, List[Dict]]:
        results = {} 
        
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
                display_name = (folder_name[:25] + '..') if len(folder_name) > 25 else folder_name
                progress.update(task, description=f"📂 {display_name}")
                
                for filename in files:
                    file_path = Path(root) / filename
                    
                    if file_path.suffix.lower() not in TARGET_EXTENSIONS: continue
                    if not TacticalScanner.is_wanted_file(filename): continue

                    try:
                        stat = file_path.stat()
                        mod_time = datetime.fromtimestamp(stat.st_mtime)
                        meta = MetadataExtractor.get_metadata(file_path)
                        
                        current_sub = Path(root).relative_to(root_folder)
                        folder_key = str(current_sub)
                        if folder_key == ".": folder_key = "ROOT"
                        
                        if folder_key not in results: results[folder_key] = []
                        results[folder_key].append({
                            'path': file_path, 'name': filename,
                            'modified': mod_time, 'metadata': meta
                        })
                    except: pass
                    
        return results

# ============================================================================
# 📄 REPORTING
# ============================================================================

def generate_system_report(results: Dict[str, List], root_folder: Path, duration: float) -> Path:
    # 1. Setup Report Directory inside FileFlow (Current Working Dir)
    report_dir = Path.cwd() / "reports"
    report_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"Scan_Log_{root_folder.name}_{timestamp}.txt"
    
    total_files = sum(len(files) for files in results.values())
    
    with open(report_file, "w", encoding="utf-8") as f:
        # HEADER
        f.write("================================================================================\n")
        f.write(f"                           FILEFLOW SYSTEM SCAN LOG                             \n")
        f.write("================================================================================\n")
        f.write(f"TARGET FOLDER : {root_folder}\n")
        f.write(f"SCAN DATE     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"EXECUTION TIME: {duration:.4f} seconds\n")
        f.write(f"TOTAL FILES   : {total_files}\n")
        f.write("================================================================================\n\n")
        
        # SUMMARY
        f.write("--------------------------------------------------------------------------------\n")
        f.write(f"                           SOURCE FOLDER SUMMARY                                \n")
        f.write("--------------------------------------------------------------------------------\n")
        sorted_folders = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)
        for folder, files in sorted_folders[:10]:
             f.write(f"[{len(files):4d} files] {folder}\n")
        if len(sorted_folders) > 10:
            f.write(f"... and {len(sorted_folders) - 10} more folders.\n")
        f.write("\n")

        # DETAILS
        f.write("--------------------------------------------------------------------------------\n")
        f.write(f"                           DETAILED FILE LISTING                                \n")
        f.write("--------------------------------------------------------------------------------\n")
        
        for folder, files in sorted_folders:
            if not files: continue
            f.write(f"\n📂 SOURCE: {folder} ({len(files)} files)\n")
            f.write("-" * 80 + "\n")
            for file in files:
                meta = file['metadata']
                date_str = file['modified'].strftime("%Y-%m-%d")
                # Format: Filename | Applicant | Position | Date
                f.write(f"  • {file['name'][:46]:<48} | {meta['applicant']:<17} | {meta['position']:<20} | {date_str}\n")
            
    return report_file

# ============================================================================
# 📦 ORGANIZER
# ============================================================================

def organize_files(results: Dict[str, List], root_folder: Path):
    # Create Output in the Scanned Folder
    output_base = root_folder / "_Organized_Output"
    output_base.mkdir(exist_ok=True)
    success_count = 0
    
    with Progress(
        SpinnerColumn(), 
        TextColumn("[bold green]Centralizing...[/bold green]"),
        BarColumn(bar_width=40),
        console=console,
        transient=True
    ) as progress:
        all_files = [f for sublist in results.values() for f in sublist]
        task = progress.add_task("Copying...", total=len(all_files))
        
        for f in all_files:
            meta = f['metadata']
            dest_folder = output_base / meta['position']
            dest_folder.mkdir(parents=True, exist_ok=True)
            
            date_str = f['modified'].strftime("%Y%m%d")
            base_name = f"{meta['applicant']}_{meta['position']}_{date_str}"
            
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
# 🚀 MAIN
# ============================================================================

def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]FileFlow Granular (v3)[/bold cyan]"))
    
    target_str = Prompt.ask("Folder path to scan")
    if not target_str: return
    root_folder = Path(target_str.strip('"').strip("'"))
    
    if not root_folder.exists():
        console.print("[red]Folder not found[/red]")
        return
        
    # --- START TIMER ---
    start_time = time.time()
    
    results = TacticalScanner.scan_folder(root_folder)
    
    # --- STOP TIMER ---
    end_time = time.time()
    duration = end_time - start_time
    
    total_found = sum(len(files) for files in results.values())
    if total_found == 0:
        console.print("[yellow]No files found.[/yellow]")
        return
        
    # Generate Report locally
    report_path = generate_system_report(results, root_folder, duration)
    
    console.print(f"\n[bold green]✓ Operation Completed[/bold green]")
    console.print(f"⏱️ Time Taken : [bold yellow]{duration:.4f} seconds[/bold yellow]")
    console.print(f"📂 Files Found: [bold]{total_found}[/bold]")
    
    console.print("\n[dim]Top 5 Sources:[/dim]")
    sorted_folders = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    for folder, files in sorted_folders:
        console.print(f" • [cyan]{folder[:50]}[/cyan]: {len(files)}")

    console.print(f"\n📄 System Log saved to: [underline]{report_path}[/underline]")
    console.print("[dim](This file is in your FileFlow/reports folder)[/dim]")
    
    if Confirm.ask("\nCentralize files to '_Organized_Output'?", default=False):
        out_folder, count = organize_files(results, root_folder)
        console.print(f"\n[bold green]✓ Copied {count} files to:[/bold green]")
        console.print(f"[cyan]{out_folder}[/cyan]")

if __name__ == "__main__":
    main()