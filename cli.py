
import sys
import argparse
from pathlib import Path

# Ensure internal modules are importable
sys.path.append(str(Path(__file__).parent))

from app.muscle.unpacker import Unpacker
from app.brain.extractor import UnifiedExtractor
from app.brain.judge import Judge
from app.brain.bridge import Bridge
from app.memory.config import ConfigLoader

def main():
    parser = argparse.ArgumentParser(description="FileFlow CLI — Senior Digital Associate (Headless)")
    parser.add_argument("action", choices=["audit", "organise"], help="Action to perform")
    parser.add_argument("path", help="Folder path to process")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Don't move files (default: True)")
    
    args = parser.parse_args()
    source = Path(args.path)
    
    if not source.exists() or not source.is_dir():
        print(f"Error: `{source}` is not a valid directory.")
        sys.exit(1)

    print(f"--- FileFlow CLI: {args.action.upper()} ---")
    print(f"Target: {source.absolute()}")
    
    # 1. Initialise Engine
    config = ConfigLoader()
    bridge = Bridge(slm_model=config.ai.slm_model)
    extractor = UnifiedExtractor()
    judge = Judge(bridge=bridge, extractor=extractor)
    unpacker = Unpacker(extractor=extractor, judge=judge)
    
    # 2. Run Analysis
    staging_root = Path("staging") / "cli_run"
    staging_root.mkdir(parents=True, exist_ok=True)
    
    print("Auditing folder structure (this involves AI analysis)...")
    report = unpacker.analyse(source, staging_root)
    
    # Show Summary
    summary = unpacker.summarise(report)
    print(summary)
    
    if args.action == "organise":
        if args.dry_run:
            print("\n[DRY RUN] Simulation complete. No files were moved.")
            print("Run with `--dry-run False` (or update logic) to execute for real.")
        else:
            print("\nExecuting organisation...")
            result = unpacker.execute(report, dry_run=False)
            print(f"Success: {result.moved} files moved, {result.skipped} skipped.")

if __name__ == "__main__":
    main()
