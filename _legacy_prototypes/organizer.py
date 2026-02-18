# organizer.py

import argparse
from pathlib import Path
from typing import List, Dict, Any

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from utils.categorizer import Categorizer, FileInfo
from utils.file_utils import FileUtils
from utils.log_utils import log_move, get_last_log_entry, remove_last_log_entry
import sys
from typing import Optional

# Initialize Rich Console for beautiful output. `record=True` allows saving output.
console = Console(record=True)

def generate_file_table(files_data: List[FileInfo], categorizer: Categorizer) -> Table:
    """Generates a Rich table object from the file data."""
    table = Table(title="[bold cyan]📁 Files Found for Organization[/bold cyan]", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("File Name", style="bold", min_width=20)
    table.add_column("Suggested Category", style="yellow", min_width=15)
    table.add_column("Size", justify="right")
    table.add_column("Last Modified", justify="right")
 
    for i, f_info in enumerate(files_data):
        category = categorizer.categorize_file(f_info)
        table.add_row(
            str(i),
            f_info['name'],
            category,
            FileUtils.format_size(f_info['size']),
            f_info['modified'].strftime('%Y-%m-%d %H:%M'),
        )
    return table

def save_table_to_file(table: Table, output_file: Path, console: Console):
    """Saves a text representation of the table to a file."""
    try:
        with output_file.open("w", encoding="utf-8") as f:
            # Use Rich's console to render the table to a text format
            with console.capture() as capture:
                console.print(table)
            f.write(capture.get())
        console.print(f"[green]✅ Full file list saved to:[/] [bold cyan]{output_file}[/]")
    except IOError as e:
        console.print(f"[red]❌ Error: Could not write to output file {output_file}: {e}[/red]")

# ... (The rest of the functions like parse_selection, organize_files, etc., remain the same) ...

def parse_selection(selection: str, total: int) -> List[int]:
    """Parses user input like '1,3,5-7' into a list of indices."""
    s = selection.strip().lower()
    if s in ("none", "cancel", "exit"):
        return []
    if s == "all":
        return list(range(total))
    
    selected = set()
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start, end = map(int, part.split('-', 1))
                selected.update(range(start, end + 1))
            except ValueError:
                continue
        else:
            try:
                selected.add(int(part))
            except ValueError:
                continue
    
    return sorted([i for i in selected if 0 <= i < total])

def organize_files(
    files_data: List[FileInfo],
    selected_indices: List[int],
    categorizer: Categorizer,
    dest_base: Path,
    dry_run: bool = False
) -> Dict[str, List[Dict]]:
    """Processes and moves files, logging the results."""
    results: Dict[str, List[Dict]] = {'success': [], 'failed': []}
    settings = categorizer.settings
    
    with console.status("[bold green]Organizing files...") as status:
        for idx in selected_indices:
            if idx >= len(files_data):
                continue
            
            f_info = files_data[idx]
            category = categorizer.categorize_file(f_info)
            status.update(f"Processing [bold magenta]{f_info['name']}[/]...")

            date_folder = ""
            if settings.get('organize_by_date', True):
                date_folder = f_info['modified'].strftime(settings.get('date_format', '%Y-%m'))
            
            dest_folder = dest_base / category / date_folder
            dest_path = dest_folder / f_info['name']

            # Handle duplicates
            if dest_path.exists():
                handle_dup = settings.get('handle_duplicates', 'rename')
                if handle_dup == 'rename':
                    dest_path = Path(FileUtils.get_unique_filename(str(dest_path)))
                elif handle_dup == 'skip':
                    results['failed'].append({'name': f_info['name'], 'error': 'File exists, skipped.'})
                    continue
                elif handle_dup == 'overwrite' and not dry_run:
                    dest_path.unlink()

            if dry_run:
                results['success'].append({'name': f_info['name'], 'destination': str(dest_path)})
            else:
                try:
                    dest_folder.mkdir(parents=True, exist_ok=True)
                    FileUtils.safe_move(f_info['path'], str(dest_path))
                    log_move(f_info['path'], str(dest_path), category=category, success=True)
                    results['success'].append({'name': f_info['name'], 'destination': str(dest_path)})
                except Exception as e:
                    log_move(f_info['path'], str(dest_path), category=category, success=False, error=str(e))
                    results['failed'].append({'name': f_info['name'], 'error': str(e)})

    return results

def undo_last_move() -> None:
    """Reverts the last successful move operation from the log file."""
    last_log = get_last_log_entry()
    if not last_log:
        console.print("[yellow]No log entries to undo.[/yellow]")
        return
    
    if not last_log.get('success'):
        console.print("[yellow]Last operation was a failure, cannot undo.[/yellow]")
        return

    dest = Path(last_log['destination'])
    src = Path(last_log['source'])

    if not dest.exists():
        console.print(f"[red]Cannot undo: Destination file missing -> {dest}[/red]")
        return
    
    console.print(f"Attempting to undo move: '[cyan]{dest.name}[/cyan]' from '[bold]{dest.parent}[/]' back to '[bold]{src.parent}[/]'.")
    if not Confirm.ask("[bold yellow]Proceed with undo?[/bold yellow]"):
        console.print("Undo cancelled.")
        return

    try:
        src.parent.mkdir(parents=True, exist_ok=True)
        FileUtils.safe_move(str(dest), str(src))
        remove_last_log_entry()
        console.print(f"[green]✅ Undo successful:[/green] Restored [cyan]{src.name}[/] to its original location.")
    except Exception as e:
        console.print(f"[bold red]❌ Undo failed:[/bold red] {e}")

def main() -> None:
    """Main entry point for the CLI application."""
    parser = argparse.ArgumentParser(
        prog="FileFlow",
        description="A smart file organizer CLI with interactive and automated modes."
    )
    parser.add_argument("source", nargs="?", help="Source folder to scan.")
    parser.add_argument("dest", nargs="?", help="Destination base folder.")
    parser.add_argument("-c", "--config", default="config.json", help="Path to config file.")
    # --- ADDED NEW ARGUMENTS ---
    parser.add_argument("-o", "--output-file", help="Save the full file list table to a text file.")
    parser.add_argument("--no-recursive", action="store_true", help="Only scan the top-level source folder, not subfolders.")
    # --- END OF NEW ARGUMENTS ---
    parser.add_argument("--auto", action="store_true", help="Automatically select all files.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm all prompts (use with --auto).")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the organization without moving files.")
    parser.add_argument("--undo", action="store_true", help="Undo the last successful file move.")
    args = parser.parse_args()

    console.print("[bold green]🚀 Welcome to FileFlow! 🚀[/bold green]")

    if args.undo:
        undo_last_move()
        sys.exit(0)

    source_dir = args.source or Prompt.ask("[bold]📂 Enter source folder to scan[/bold]")
    dest_dir = args.dest or Prompt.ask("[bold]🎯 Enter destination folder[/bold]")
    
    source = Path(source_dir).expanduser()
    dest = Path(dest_dir).expanduser()

    if not source.is_dir():
        console.print(f"[red]Error: Source folder not found at '{source}'[/red]")
        sys.exit(1)

    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        console.print(f"[red]Error: Could not create destination folder at '{dest}': {e}[/red]")
        sys.exit(1)

    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        console.print(f"[red]Error: Could not create destination folder at '{dest}': {e}[/red]")
        sys.exit(1)

    categorizer = Categorizer(config_path=args.config)
    ignore_rules = categorizer.config.get("ignore", {})
    
    # --- MODIFIED SCANNING LOGIC ---
    is_recursive = not args.no_recursive
    console.print(f"🔍 Scanning [cyan]{source}[/]... (Recursive: {is_recursive})")
    files = FileUtils.scan_folder(str(source), ignore_rules, recursive=is_recursive)
    # --- END OF MODIFIED LOGIC ---
 
    if not files:
        console.print("[yellow]No files found to organize (after applying ignore rules).[/yellow]")
        sys.exit(0)
    
    console.print(f"✅ Found {len(files)} files.")
    files.sort(key=lambda x: x['modified'], reverse=True)

    # Generate the table of files
    file_table = generate_file_table(files, categorizer)

    # --- ADDED SAVE-TO-FILE LOGIC ---
    if args.output_file:
        save_table_to_file(file_table, Path(args.output_file), console)
    # --- END OF SAVE-TO-FILE LOGIC ---

    # Display the table to the console regardless
    console.print(file_table)

    if args.auto:
        selected_indices = list(range(len(files)))
        console.print(f"[cyan]--auto mode enabled. Selected all {len(selected_indices)} files.[/cyan]")
        if not args.yes and not args.dry_run:
            if not Confirm.ask(f"Proceed with organizing {len(selected_indices)} files?"):
                console.print("Operation cancelled.")
                sys.exit(0)
    else:
        selection_str = Prompt.ask("\n[bold]✅ Select files to organize (e.g., 0,1,4-7 or 'all')[/bold]")
        selected_indices = parse_selection(selection_str, len(files))

    if not selected_indices:
        console.print("[yellow]No files selected. Exiting.[/yellow]")
        sys.exit(0)

    if args.dry_run:
        console.print("\n[bold yellow]-- DRY RUN MODE --[/bold yellow]")
    else:
        console.print(f"\n[bold]Moving {len(selected_indices)} files to subfolders within '{dest}'[/bold]")
        if not args.yes and not Confirm.ask("[bold yellow]Are you sure you want to proceed?[/bold yellow]"):
            console.print("Operation cancelled.")
            sys.exit(0)

    results = organize_files(files, selected_indices, categorizer, dest, dry_run=args.dry_run)
    
    # Final Results Summary
    console.print("\n[bold green]✨ Organization Complete ✨[/bold green]")
    if results['success']:
        success_table = Table(title="[bold green]Successful Moves[/bold green]")
        success_table.add_column("File Name", style="cyan")
        success_table.add_column("Destination Path")
        for item in results['success']:
            success_table.add_row(item['name'], item['destination'])
        console.print(success_table)

    if results['failed']:
        fail_table = Table(title="[bold red]Failed Moves[/bold red]")
        fail_table.add_column("File Name", style="cyan")
        fail_table.add_column("Reason")
        for item in results['failed']:
            fail_table.add_row(item['name'], item['error'])
        console.print(fail_table)

# Keep the original helper functions (parse_selection, organize_files, undo_last_move) as they were.

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Operation cancelled by user.[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]An unexpected error occurred: {e}[/bold red]")