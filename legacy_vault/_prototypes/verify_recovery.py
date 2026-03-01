import os
from pathlib import Path
import sys
from rich.console import Console
from rich.table import Table
from rich.progress import track

console = Console()

def verify_pdf(file_path: Path) -> str:
    """
    Returns 'OK', 'CORRUPT_HEADER', 'CORRUPT_EOF', 'HOLLOW', or 'READ_ERROR'
    """
    try:
        file_size = file_path.stat().st_size
        if file_size == 0:
            return "EMPTY_ZERO_BYTE"
            
        with open(file_path, "rb") as f:
            header = f.read(1024)
            
            # 1. Check Header
            if not b"%PDF" in header:
                return "CORRUPT_HEADER"
                
            # 2. Check for Hollowness (Null bytes in first 1KB)
            if header.count(b'\x00') > 500: # Arbitrary threshold for "mostly nulls"
                return "HOLLOW_NULL_BYTES"
                
            # 3. Check EOF
            try:
                f.seek(-1024, 2) # Go to end
                tail = f.read()
            except OSError:
                 # File might be smaller than 1024
                 tail = header
                 
            if b"%%EOF" not in tail:
                return "CORRUPT_EOF_TRUNCATED"
                
            return "OK"
            
    except Exception as e:
        return f"READ_ERROR: {str(e)}"

def scan_folder(target_folder: str):
    root = Path(target_folder)
    if not root.exists():
        console.print(f"[bold red]❌ Folder not found: {root}[/bold red]")
        return

    pdf_files = list(root.rglob("*.pdf"))
    console.print(f"[bold blue]Scanning {len(pdf_files)} PDF files in {root.name}...[/bold blue]")

    results = {
        "OK": 0,
        "CORRUPT_HEADER": 0,
        "CORRUPT_EOF_TRUNCATED": 0,
        "HOLLOW_NULL_BYTES": 0,
        "EMPTY_ZERO_BYTE": 0,
        "READ_ERROR": 0
    }
    
    bad_files = []

    for pdf in track(pdf_files, description="Verifying..."):
        status = verify_pdf(pdf)
        if status == "OK":
            results["OK"] += 1
        else:
            if status.startswith("READ_ERROR"):
                results["READ_ERROR"] += 1
            else:
                results[status] += 1
            bad_files.append((pdf, status))

    # Report
    table = Table(title="Recovery Integrity Report")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="magenta")
    
    for status, count in results.items():
        color = "green" if status == "OK" else "red"
        table.add_row(f"[{color}]{status}[/{color}]", str(count))
        
    console.print(table)
    
    if bad_files:
        console.print("\n[bold red]Corrupted Files (First 10):[/bold red]")
        for f, s in bad_files[:10]:
            console.print(f" - {f.name} ({s})")
            
    if results["OK"] > 0:
         console.print(f"\n[bold green]✅ SUCCESS: {results['OK']} valid files recovered![/bold green]")
    else:
         console.print(f"\n[bold red]⚠️  WARNING: No valid PDFs found.[/bold red]")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = r"C:\Users\sandi\Desktop\RECOVERED_SUCCESS_FEB10"
        
    scan_folder(target)
