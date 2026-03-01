#!/usr/bin/env python3
"""
FileFlow Enhanced - Intelligent Job Application File Organizer
Designed specifically for automating legal job application file management
"""

import argparse
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import PyPDF2
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

console = Console()

# ============================================================================
# PDF METADATA EXTRACTION
# ============================================================================

class PDFExtractor:
    """Extracts metadata from Z83 government application forms"""
    
    @staticmethod
    def extract_application_metadata(pdf_path: str) -> Optional[Dict[str, str]]:
        """
        Extract position, department, applicant name, and reference # from Z83 PDF.
        Returns None if extraction fails.
        """
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
            
            metadata = {}
            
            # Extract Position (e.g., "JUDGES SECRETARY" or "STATE LAW ADVISOR: LITIGATION")
            pos_match = re.search(
                r'(?:Position for which you are applying|JUDGE\'S SECRETARY|STATE LAW ADVISOR|LEGAL ADMIN OFFICER)',
                text,
                re.IGNORECASE
            )
            
            # Try structured position extraction
            if 'JUDGE' in text.upper() and 'SECRETARY' in text.upper():
                metadata['position'] = 'Judges_Secretary'
            elif 'STATE LAW ADVISOR' in text.upper() and 'LITIGATION' in text.upper():
                metadata['position'] = 'State_Law_Advisor_Litigation'
            elif 'LEGAL ADMIN' in text.upper() and 'OFFICER' in text.upper():
                metadata['position'] = 'Legal_Admin_Officer'
            else:
                # Fallback: extract from text
                pos_pattern = r'(?:Position|POSITION).*?:\s*([A-Za-z\s&:]+?)(?:\n|Department)'
                pos_match = re.search(pos_pattern, text)
                if pos_match:
                    metadata['position'] = pos_match.group(1).strip().replace(' ', '_').replace('&', 'and')
                else:
                    metadata['position'] = 'Unknown_Position'
            
            # Extract Department
            dept_pattern = r'(?:Department|DEPARTMENT).*?:\s*([A-Z\s&]+?)(?:\n|Reference)'
            dept_match = re.search(dept_pattern, text)
            if dept_match:
                dept = dept_match.group(1).strip()
                # Abbreviate common departments
                dept_abbrev = {
                    'OFFICE OF THE CHIEF JUSTICE': 'OCJ',
                    'HUMAN SETTLEMENTS': 'HS',
                    'PUBLIC WORKS': 'DPWI'
                }
                metadata['department'] = dept_abbrev.get(dept, dept[:3].upper())
            else:
                metadata['department'] = 'DEPT'
            
            # Extract Reference Number
            ref_pattern = r'(?:Reference number|REFERENCE).*?:\s*(\d+/\d+|\d+)'
            ref_match = re.search(ref_pattern, text)
            if ref_match:
                metadata['reference'] = ref_match.group(1)
            else:
                metadata['reference'] = None
            
            # Extract Applicant Name (look for surname and full names line)
            name_pattern = r'(?:Surname and Full names|SURNAME).*?:\s*([A-Za-z\s]+?)(?:\n|Date of Birth)'
            name_match = re.search(name_pattern, text)
            if name_match:
                name = name_match.group(1).strip()
                # Clean up name
                name = re.sub(r'\s+', '_', name)
                metadata['applicant'] = name
            else:
                # Try looking for common patterns in filename
                metadata['applicant'] = 'Unknown_Applicant'
            
            return metadata if metadata.get('position') and metadata.get('applicant') != 'Unknown_Applicant' else None
        
        except Exception as e:
            console.print(f"[yellow]Warning: Could not extract PDF metadata from {Path(pdf_path).name}: {e}[/yellow]")
            return None

# ============================================================================
# PROFILE MANAGEMENT
# ============================================================================

class ProfileManager:
    """Manages scan profiles (saved folder configurations)"""
    
    PROFILES_FILE = Path.home() / '.fileflow_profiles.json'
    
    @staticmethod
    def load_profiles() -> Dict[str, Dict[str, Any]]:
        """Load all saved profiles"""
        if ProfileManager.PROFILES_FILE.exists():
            with open(ProfileManager.PROFILES_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    @staticmethod
    def save_profiles(profiles: Dict) -> None:
        """Save profiles to file"""
        with open(ProfileManager.PROFILES_FILE, 'w') as f:
            json.dump(profiles, f, indent=2)
    
    @staticmethod
    def create_profile(name: str) -> Dict[str, Any]:
        """Interactive profile creation"""
        console.print(f"\n[bold cyan]Creating profile: {name}[/bold cyan]")
        
        folders = []
        console.print("[yellow]Enter folder paths to scan (one per line, empty line to finish):[/yellow]")
        while True:
            folder_input = input("Folder path: ").strip()
            if folder_input == "":
                if folders:
                    break
                console.print("[red]Please enter at least one folder[/red]")
                continue
            
            folder_path = Path(folder_input).expanduser()
            if not folder_path.is_dir():
                console.print(f"[red]Folder not found: {folder_path}[/red]")
                continue
            
            folders.append(str(folder_path))
            console.print(f"[green]✓ Added: {folder_path}[/green]")
        
        console.print("\n[yellow]Now entering date range...[/yellow]")
        date_from = input("Start date (YYYY-MM-DD) [2024-01-01]: ").strip() or "2024-01-01"
        date_to = input("End date (YYYY-MM-DD) [2025-11-22]: ").strip() or datetime.now().strftime("%Y-%m-%d")
        
        return {
            "folders": folders,
            "date_from": date_from,
            "date_to": date_to,
            "created": datetime.now().isoformat()
        }

# ============================================================================
# FILE SCANNING & ORGANIZATION
# ============================================================================

class FileScanner:
    """Scans folders for job application PDFs"""
    
    @staticmethod
    def scan_folders(
        folders: List[str],
        date_from: str,
        date_to: str,
        file_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Scan multiple folders for files within date range"""
        
        if file_types is None:
            file_types = ['.pdf', '.docx', '.doc']
        
        date_from_dt = datetime.strptime(date_from, "%Y-%m-%d")
        date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
        
        files = []
        
        for folder_str in folders:
            folder = Path(folder_str)
            if not folder.is_dir():
                console.print(f"[yellow]Skipping invalid folder: {folder}[/yellow]")
                continue
            
            console.print(f"[cyan]Scanning: {folder}[/cyan]")
            
            for file_path in folder.rglob('*'):
                if not file_path.is_file():
                    continue
                
                if file_path.suffix.lower() not in file_types:
                    continue
                
                # Check date range
                mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if not (date_from_dt <= mod_time <= date_to_dt):
                    continue
                
                file_info = {
                    'path': str(file_path.resolve()),
                    'name': file_path.name,
                    'extension': file_path.suffix.lower(),
                    'size': file_path.stat().st_size,
                    'modified': mod_time,
                    'metadata': None
                }
                
                # Extract metadata if PDF
                if file_path.suffix.lower() == '.pdf':
                    file_info['metadata'] = PDFExtractor.extract_application_metadata(str(file_path))
                
                files.append(file_info)
        
        return files

class FileOrganizer:
    """Handles versioning and file movement"""
    
    @staticmethod
    def generate_new_filename(
        applicant: str,
        position: str,
        date_obj: datetime,
        existing_count: int = 0
    ) -> str:
        """Generate filename: Applicant_Position_YYYYMMDD_vN.pdf"""
        date_str = date_obj.strftime("%Y%m%d")
        version = existing_count + 1
        return f"{applicant}_{position}_{date_str}_v{version}.pdf"
    
    @staticmethod
    def find_or_create_position_folder(base_dest: Path, position: str) -> Path:
        """Get or create position folder"""
        pos_folder = base_dest / position
        pos_folder.mkdir(parents=True, exist_ok=True)
        return pos_folder
    
    @staticmethod
    def get_version_count(pos_folder: Path, applicant: str, position: str, date_str: str) -> int:
        """Count existing versions for this applicant+position+date"""
        pattern = f"{applicant}_{position}_{date_str}_v*.pdf"
        existing = list(pos_folder.glob(pattern))
        return len(existing)
    
    @staticmethod
    def safe_move(src: Path, dst: Path) -> bool:
        """Move file safely"""
        try:
            import shutil
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return True
        except Exception as e:
            console.print(f"[red]Error moving {src.name}: {e}[/red]")
            return False

# ============================================================================
# LOGGING & UNDO
# ============================================================================

class MoveLogger:
    """Track file moves for undo functionality"""
    
    LOG_FILE = Path.home() / '.fileflow_moves.jsonl'
    
    @staticmethod
    def log_move(src: str, dst: str, position: str, applicant: str) -> None:
        """Log a file move"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": src,
            "destination": dst,
            "position": position,
            "applicant": applicant
        }
        try:
            with open(MoveLogger.LOG_FILE, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            console.print(f"[yellow]Warning: Could not log move: {e}[/yellow]")
    
    @staticmethod
    def get_last_moves(count: int = 10) -> List[Dict]:
        """Get last N moves"""
        if not MoveLogger.LOG_FILE.exists():
            return []
        
        moves = []
        with open(MoveLogger.LOG_FILE, 'r') as f:
            for line in f:
                try:
                    moves.append(json.loads(line))
                except:
                    pass
        
        return moves[-count:]
    
    @staticmethod
    def undo_last_move() -> bool:
        """Undo the last move"""
        import shutil
        moves = MoveLogger.get_last_moves(1)
        if not moves:
            console.print("[yellow]No moves to undo[/yellow]")
            return False
        
        move = moves[0]
        dst = Path(move['destination'])
        src = Path(move['source'])
        
        if not dst.exists():
            console.print(f"[red]Destination file no longer exists: {dst}[/red]")
            return False
        
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            console.print(f"[green]✓ Undone: {dst.name} → {src}[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Undo failed: {e}[/red]")
            return False

# ============================================================================
# CLI INTERFACE
# ============================================================================

def display_file_table(files: List[Dict]) -> Table:
    """Create a Rich table of files to organize"""
    table = Table(title="[bold cyan]📄 Files Found for Organization[/bold cyan]", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("File Name", style="bold", width=30)
    table.add_column("Applicant", style="cyan", width=20)
    table.add_column("Position", style="yellow", width=25)
    table.add_column("Date Modified", width=12)
    
    for i, f in enumerate(files):
        applicant = "?"
        position = "?"
        
        if f.get('metadata'):
            applicant = f['metadata'].get('applicant', '?')[:15]
            position = f['metadata'].get('position', '?')[:20]
        
        table.add_row(
            str(i),
            f['name'][:27],
            applicant,
            position,
            f['modified'].strftime('%Y-%m-%d')
        )
    
    return table

def preview_organization(files: List[Dict], dest_base: Path) -> List[Dict]:
    """Show what will happen without moving files"""
    results = []
    
    for f in files:
        if not f.get('metadata'):
            results.append({
                'file': f['name'],
                'destination': '[yellow]Could not extract metadata[/yellow]',
                'reason': 'No metadata'
            })
            continue
        
        meta = f['metadata']
        applicant = meta['applicant']
        position = meta['position']
        date_str = f['modified'].strftime("%Y%m%d")
        
        pos_folder = dest_base / position
        existing_count = FileOrganizer.get_version_count(pos_folder, applicant, position, date_str)
        new_filename = FileOrganizer.generate_new_filename(applicant, position, f['modified'], existing_count)
        
        new_path = pos_folder / new_filename
        
        results.append({
            'file': f['name'],
            'destination': str(new_path),
            'reason': 'OK'
        })
    
    return results

def main():
    parser = argparse.ArgumentParser(
        prog="FileFlow Enhanced",
        description="Smart job application file organizer with PDF extraction and versioning"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Profile commands
    profile_parser = subparsers.add_parser('profile', help='Manage scan profiles')
    profile_parser.add_argument('action', choices=['create', 'list', 'delete'], help='Profile action')
    profile_parser.add_argument('name', nargs='?', help='Profile name')
    
    # Organize command
    org_parser = subparsers.add_parser('organize', help='Organize files')
    org_parser.add_argument('--profile', help='Use saved profile')
    org_parser.add_argument('--folders', nargs='+', help='Folders to scan (overrides profile)')
    org_parser.add_argument('--from', dest='date_from', help='Start date (YYYY-MM-DD)')
    org_parser.add_argument('--to', dest='date_to', help='End date (YYYY-MM-DD)')
    org_parser.add_argument('--dest', required=True, help='Destination folder')
    org_parser.add_argument('--dry-run', action='store_true', help='Preview without moving')
    org_parser.add_argument('--yes', action='store_true', help='Skip confirmations')
    
    # Undo command
    undo_parser = subparsers.add_parser('undo', help='Undo last move')
    undo_parser.add_argument('--last', type=int, default=1, help='Number of moves to undo')
    
    args = parser.parse_args()
    
    console.print("[bold green]🚀 FileFlow Enhanced 🚀[/bold green]\n")
    
    # ===== PROFILE COMMANDS =====
    if args.command == 'profile':
        profiles = ProfileManager.load_profiles()
        
        if args.action == 'list':
            if not profiles:
                console.print("[yellow]No profiles saved[/yellow]")
            else:
                table = Table(title="[bold]Saved Profiles[/bold]")
                table.add_column("Name", style="cyan")
                table.add_column("Folders", style="yellow")
                table.add_column("Date Range", style="green")
                
                for name, profile in profiles.items():
                    folders_str = ", ".join([Path(f).name for f in profile['folders']])
                    date_range = f"{profile['date_from']} to {profile['date_to']}"
                    table.add_row(name, folders_str, date_range)
                
                console.print(table)
        
        elif args.action == 'create':
            if not args.name:
                args.name = Prompt.ask("Profile name")
            
            profile = ProfileManager.create_profile(args.name)
            profiles[args.name] = profile
            ProfileManager.save_profiles(profiles)
            console.print(f"[green]✓ Profile '{args.name}' created[/green]")
        
        elif args.action == 'delete':
            if not args.name:
                args.name = Prompt.ask("Profile name")
            
            if args.name in profiles:
                del profiles[args.name]
                ProfileManager.save_profiles(profiles)
                console.print(f"[green]✓ Profile '{args.name}' deleted[/green]")
            else:
                console.print(f"[red]Profile '{args.name}' not found[/red]")
    
    # ===== ORGANIZE COMMAND =====
    elif args.command == 'organize':
        folders = args.folders
        date_from = args.date_from
        date_to = args.date_to
        
        # Load from profile if specified
        if args.profile:
            profiles = ProfileManager.load_profiles()
            if args.profile not in profiles:
                console.print(f"[red]Profile '{args.profile}' not found[/red]")
                return
            
            profile = profiles[args.profile]
            folders = folders or profile['folders']
            date_from = date_from or profile['date_from']
            date_to = date_to or profile['date_to']
        
        if not folders:
            console.print("[red]No folders specified. Use --folders or --profile[/red]")
            return
        
        if not date_from:
            date_from = Prompt.ask("Start date (YYYY-MM-DD)", default="2024-01-01")
        if not date_to:
            date_to = Prompt.ask("End date (YYYY-MM-DD)", default=datetime.now().strftime("%Y-%m-%d"))
        
        dest_base = Path(args.dest).expanduser()
        
        # Scan
        console.print("\n[bold]Scanning files...[/bold]")
        files = FileScanner.scan_folders(folders, date_from, date_to)
        
        if not files:
            console.print("[yellow]No files found matching criteria[/yellow]")
            return
        
        console.print(f"[green]✓ Found {len(files)} files[/green]\n")
        
        # Display table
        console.print(display_file_table(files))
        
        # Preview
        console.print("\n[bold]Preview:[/bold]")
        preview = preview_organization(files, dest_base)
        
        preview_table = Table(title="[bold cyan]Organization Plan[/bold cyan]")
        preview_table.add_column("File", style="cyan", width=30)
        preview_table.add_column("→ Destination", width=50)
        
        for item in preview[:10]:  # Show first 10
            preview_table.add_row(item['file'][:28], item['destination'][-47:])
        
        if len(preview) > 10:
            preview_table.add_row("[dim]...[/dim]", f"[dim]... and {len(preview)-10} more[/dim]")
        
        console.print(preview_table)
        
        # Confirm
        if args.dry_run:
            console.print("\n[bold yellow]DRY RUN MODE - No files will be moved[/bold yellow]")
            return
        
        if not args.yes:
            if not Confirm.ask(f"\n[bold]Proceed with organizing {len(files)} files?[/bold]"):
                console.print("[yellow]Cancelled[/yellow]")
                return
        
        # Execute moves
        console.print("\n[bold]Organizing files...[/bold]\n")
        success = 0
        failed = 0
        
        for i, f in enumerate(files, 1):
            if not f.get('metadata'):
                console.print(f"[yellow]⊘ Skipped {f['name']} (no metadata)[/yellow]")
                failed += 1
                continue
            
            meta = f['metadata']
            applicant = meta['applicant']
            position = meta['position']
            
            pos_folder = FileOrganizer.find_or_create_position_folder(dest_base, position)
            date_str = f['modified'].strftime("%Y%m%d")
            existing_count = FileOrganizer.get_version_count(pos_folder, applicant, position, date_str)
            
            new_filename = FileOrganizer.generate_new_filename(applicant, position, f['modified'], existing_count)
            new_path = pos_folder / new_filename
            
            if FileOrganizer.safe_move(Path(f['path']), new_path):
                MoveLogger.log_move(f['path'], str(new_path), position, applicant)
                console.print(f"[green]✓ {i}/{len(files)} {new_filename}[/green]")
                success += 1
            else:
                console.print(f"[red]✗ {i}/{len(files)} {f['name']}[/red]")
                failed += 1
        
        console.print(f"\n[bold green]Complete: {success} moved, {failed} failed[/bold green]")
    
    # ===== UNDO COMMAND =====
    elif args.command == 'undo':
        for _ in range(args.last):
            MoveLogger.undo_last_move()
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()