import shutil
import os
from pathlib import Path
from rich.console import Console
from rich.progress import track

console = Console()

def is_valid_pdf(file_path):
    """
    Checks if a PDF is valid (has header, not empty).
    Returns True if valid, False if corrupted/ghost.
    """
    try:
        if os.path.getsize(file_path) < 1024: # Skip < 1KB
            return False
            
        with open(file_path, 'rb') as f:
            header = f.read(1024)
            # Check for standard PDF signature
            if b'%PDF' not in header:
                return False
            # Check for null-byte saturation (Ghost file characteristic)
            if header.count(b'\x00') > 500:
                return False
                
        return True
    except Exception:
        return False

def deep_recover():
    # CONFIGURATION
    SOURCE_ROOT = Path(r"C:\Restore_Portal\Users\sandi\Desktop\Courses")
    DEST_ROOT = Path(r"C:\Users\sandi\Desktop\FULL_RECOVERY_FROM_SHADOW")
    
    if not SOURCE_ROOT.exists():
        console.print(f"[bold red]❌ Error: Shadow Portal not found at {SOURCE_ROOT}[/bold red]")
        console.print("Please make sure the link is active.")
        return

    console.print(f"[bold blue]🚀 Starting Deep Recovery from: {SOURCE_ROOT}[/bold blue]")
    console.print(f"[bold blue]📂 Saving to: {DEST_ROOT}[/bold blue]")

    pdf_files = list(SOURCE_ROOT.rglob("*.pdf"))
    console.print(f"[yellow]Found {len(pdf_files)} potential PDFs to inspect...[/yellow]")
    
    recovered_count = 0
    corrupted_count = 0
    
    for src_file in track(pdf_files, description="Inspecting & Recovering..."):
        if is_valid_pdf(src_file):
            try:
                # Calculate relative path to preserve structure
                rel_path = src_file.relative_to(SOURCE_ROOT)
                dest_file = DEST_ROOT / rel_path
                
                # Create parent directory
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy
                shutil.copy2(src_file, dest_file)
                recovered_count += 1
            except Exception as e:
                console.print(f"[red]Failed to copy {src_file.name}: {e}[/red]")
        else:
            corrupted_count += 1

    console.print("\n[bold]Recovery Complete:[/bold]")
    console.print(f"[bold green]✅ Recovered: {recovered_count} valid files[/bold green]")
    console.print(f"[bold red]❌ Corrupted/Ghost: {corrupted_count} files[/bold red]")
    console.print(f"Files are waiting in: {DEST_ROOT}")

if __name__ == "__main__":
    deep_recover()
