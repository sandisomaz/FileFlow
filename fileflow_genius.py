#!/usr/bin/env python3
"""
FileFlow Select (v6) - Granular Control
Features:
- 🎯 Interactive Folder Selection (Pick exactly which subfolders to scan)
- 🧠 Genius Context & Date Extraction
- ⏱️ Precision Timer & Reporting
"""

import os
import shutil
import re
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
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
    "udemy", "course resource" # Added based on your logs
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
    def scan_folders(folders_to_scan: List[Path], root_reference: Path) -> Dict[str, List[Dict]]:
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
            
            for folder in folders_to_scan:
                for root, dirs, files in os.walk(folder, topdown=True):
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
                            
                            # Show relative path from the Main Root for the report
                            try:
                                current_sub = Path(root).relative_to(root_reference)
                            except:
                                current_sub = Path(root)

                            folder_key = str(current_sub)
                            
                            if folder_key not in results: results[folder_key] = []
                            results[folder_key].append({
                                'path': file_path, 
                                'name': filename,
                                'date': final_date,
                                'metadata': meta
                            })
                        except: pass
                    
        return results

# ============================================================================
# 📄 REPORTING & LOGGING
# ============================================================================

def format_duration(seconds: float) -> str:
    if seconds < 60: return f"{seconds:.2f} seconds"
    minutes, sec = divmod(seconds, 60)
    return f"{int(minutes)} min, {int(sec)} sec"

def generate_system_report(results: Dict[str, List], root_folder: Path, duration: float) -> Path:
    report_dir = Path.cwd() / "reports"
    report_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"Scan_Log_{root_folder.name}_{timestamp}.txt"
    
    total_files = sum(len(files) for files in results.values())
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"TARGET FOLDER : {root_folder}\n")
        f.write(f"EXECUTION TIME: {format_duration(duration)}\n")
        f.write(f"TOTAL FILES   : {total_files}\n")
        f.write("="*100 + "\n")
        f.write(f"{'SOURCE FOLDER':<50} | {'APPLICANT':<15} | {'DETECTED JOB':<25} | {'SMART DATE'}\n")
        f.write("-" * 100 + "\n")
        
        sorted_folders = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)
        
        for folder, files in sorted_folders:
            if not files: continue
            for file in files:
                meta = file['metadata']
                date_str = file['date'].strftime("%Y-%m-%d")
                folder_short = folder[-45:] if len(folder) > 45 else folder
                app_name = meta.get('applicant', 'Unknown')
                job_name = meta.get('position', 'General')
                f.write(f"{folder_short:<50} | {app_name:<15} | {job_name:<25} | {date_str}\n")
            
    return report_file

class MoveLogger:
    @staticmethod
    def get_log_path() -> Path:
        log_dir = Path.cwd() / "reports"
        log_dir.mkdir(exist_ok=True)
        return log_dir / "move_log.jsonl"

    @staticmethod
    def log_copy(src: Path, dst: Path, metadata: Dict) -> None:
        log_file = MoveLogger.get_log_path()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": str(src.resolve()),
            "destination": str(dst.resolve()),
            "applicant": metadata.get('applicant'),
            "position": metadata.get('position')
        }
        try:
            with open(log_file, 'a', encoding="utf-8") as f:
                f.write(json.dumps(entry) + '\n')
        except: pass

    @staticmethod
    def undo_last_copy() -> None:
        log_file = MoveLogger.get_log_path()
        if not log_file.exists() or log_file.stat().st_size == 0:
            console.print("[yellow]Undo log is empty.[/yellow]")
            return

        with open(log_file, 'r+', encoding="utf-8") as f:
            lines = f.readlines()
            if not lines: return
            last_move = json.loads(lines[-1])
            dest_path = Path(last_move['destination'])

            console.print(f"Undoing: deleting [cyan]{dest_path.name}[/cyan]")
            if Confirm.ask(f"Confirm delete?", default=False):
                try:
                    if dest_path.exists(): dest_path.unlink()
                    f.seek(0)
                    f.writelines(lines[:-1])
                    f.truncate()
                    console.print(f"[green]✓ Restored.[/green]")
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")

# ============================================================================
# 📦 ORGANIZER
# ============================================================================

def organize_files(results: Dict[str, List], root_folder: Path):
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
            date_obj = f['date']
            clean_job = re.sub(r'[^\w\-_]', '_', meta.get('position', 'General'))
            dest_folder = output_base / clean_job
            dest_folder.mkdir(parents=True, exist_ok=True)
            
            date_str = date_obj.strftime("%Y%m%d")
            applicant = meta.get('applicant', 'Unknown')
            base_name = f"{applicant}_{clean_job}_{date_str}"
            
            existing = list(dest_folder.glob(f"{base_name}_v*.pdf"))
            version = len(existing) + 1
            
            new_name = f"{base_name}_v{version}{f['path'].suffix}"
            dest_path = dest_folder / new_name
            
            try:
                shutil.copy2(f['path'], dest_path)
                success_count += 1
                MoveLogger.log_copy(f['path'], dest_path, meta)
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
        return [root] # No subfolders, scan root

    console.print(f"\n[bold]Found {len(all_items)} folders in {root.name}:[/bold]")
    
    # Create a display table
    table = Table(show_header=False, box=None)
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Folder Name", style="yellow")
    
    for i, folder in enumerate(all_items, 1):
        table.add_row(str(i), folder.name)
    
    console.print(table)
    console.print("\n[dim]Enter numbers separated by commas (e.g. '1,3,5') or 'all'[/dim]")
    
    selection = Prompt.ask("Select folders to scan")
    
    selected_folders = []
    if selection.lower().strip() == 'all':
        return all_items
    
    try:
        indices = [int(x.strip()) for x in selection.split(',') if x.strip().isdigit()]
        for i in indices:
            if 1 <= i <= len(all_items):
                selected_folders.append(all_items[i-1])
    except:
        console.print("[red]Invalid selection. Scanning all.[/red]")
        return all_items
        
    if not selected_folders:
        console.print("[yellow]No selection made. Scanning root.[/yellow]")
        return [root]
        
    return selected_folders

# ============================================================================
# 🚀 MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="FileFlow Genius (v6)")
    parser.add_argument("--undo", action="store_true", help="Undo last copy")
    args = parser.parse_args()

    console.clear()
    console.print(Panel.fit("[bold cyan]FileFlow Select (v6)[/bold cyan]"))

    if args.undo:
        MoveLogger.undo_last_copy()
        return
    
    target_str = Prompt.ask("Folder path to scan", default=r"C:\Users\sandi\Desktop\Courses")
    if not target_str: return
    root_folder = Path(target_str.strip('"').strip("'"))
    
    if not root_folder.exists():
        console.print("[red]Folder not found[/red]")
        return

    # 1. Interactive Selection
    folders_to_scan = select_subfolders(root_folder)
    console.print(f"\n[green]Selected {len(folders_to_scan)} folders to process.[/green]")
        
    # 2. Scan
    start_time = time.time()
    results = TacticalScanner.scan_folders(folders_to_scan, root_folder)
    duration = time.time() - start_time
    
    total_found = sum(len(files) for files in results.values())
    
    if total_found == 0:
        console.print("[yellow]No relevant files found in selected folders.[/yellow]")
        return
        
    report_path = generate_system_report(results, root_folder, duration)
    
    console.print(f"\n[bold green]✓ Found {total_found} files[/bold green] in [bold yellow]{format_duration(duration)}[/bold yellow]")
    console.print(f"📝 System Log: [underline]{report_path.name}[/underline]")
    
    if Confirm.ask("\nCentralize files to '_Organized_Output'?", default=False):
        out_folder, count = organize_files(results, root_folder)
        console.print(f"\n[bold green]✓ Copied {count} files to:[/bold green]")
        console.print(f"[cyan]{out_folder}[/cyan]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Cancelled.[/bold red]")