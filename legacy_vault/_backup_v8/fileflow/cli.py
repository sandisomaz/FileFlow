import argparse
import sys
from pathlib import Path
from fileflow.tui import FileFlowApp
from fileflow.core.scanner import Scanner
from fileflow.core.organizer import Organizer

def main():
    parser = argparse.ArgumentParser(description="FileFlow - Job PDF Organizer")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Dashboard (Default)
    parser_dash = subparsers.add_parser('dashboard', help='Launch Interactive Dashboard')
    
    # Scan
    parser_scan = subparsers.add_parser('scan', help='Scan a folder')
    parser_scan.add_argument('path', help='Path to scan')
    
    args = parser.parse_args()

    if args.command == 'dashboard' or args.command is None:
        app = FileFlowApp()
        app.run()
    elif args.command == 'scan':
        path = Path(args.path)
        if not path.exists():
            print(f"Error: {path} does not exist.")
            return
        
        print(f"Scanning {path}...")
        results = Scanner.scan_directory(path)
        total = sum(len(files) for files in results.values())
        print(f"Found {total} files.")
        
        for folder, files in results.items():
            for f in files:
                print(f"- {f['name']} ({f['metadata'].get('position')})")

if __name__ == "__main__":
    main()
