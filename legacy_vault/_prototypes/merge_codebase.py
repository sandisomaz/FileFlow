import os
from pathlib import Path

# Configuration
SOURCE_DIR = Path(r"c:/Users/sandi/Desktop/FileFlow")
OUTPUT_FILE = SOURCE_DIR / "fileflow_codebase.txt"

# Files/Dirs to ignore
IGNORE_DIRS = {'.git', '.venv', '__pycache__', '.idea', '.vscode', 'reports', 'utils'}
IGNORE_EXTENSIONS = {'.pyc', '.pdf', '.docx', '.doc', '.jpg', '.png', '.exe', '.bin', '.csv', '.zip'}
IGNORE_FILES = {
    'fileflow_codebase.txt', 
    'package-lock.json', 
    'yarn.lock',
    'dry_run_report.txt',
    'Scan_Report_Courses_20251123_0908.txt'
}

def is_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read(1024)
        return True
    except (UnicodeDecodeError, IOError):
        return False

def merge_files():
    print(f"Scanning {SOURCE_DIR}...")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        outfile.write(f"# FileFlow Codebase Export\n")
        outfile.write(f"# Generated on {os.path.basename(__file__)}\n\n")
        
        for root, dirs, files in os.walk(SOURCE_DIR):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                if file in IGNORE_FILES:
                    continue
                
                file_path = Path(root) / file
                
                if file_path.suffix.lower() in IGNORE_EXTENSIONS:
                    continue
                
                # Calculate relative path for display
                try:
                    rel_path = file_path.relative_to(SOURCE_DIR)
                except ValueError:
                    rel_path = file_path
                
                if not is_text_file(file_path):
                    print(f"Skipping binary file: {rel_path}")
                    continue
                
                print(f"Processing: {rel_path}")
                
                # Write file header
                outfile.write(f"\n{'='*80}\n")
                outfile.write(f"FILE: {rel_path}\n")
                outfile.write(f"{'='*80}\n\n")
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as infile:
                        content = infile.read()
                        outfile.write(content)
                        outfile.write("\n")
                except Exception as e:
                    outfile.write(f"ERROR READING FILE: {e}\n")
                    print(f"Error reading {rel_path}: {e}")

    print(f"\nSuccessfully created {OUTPUT_FILE}")

if __name__ == "__main__":
    merge_files()
