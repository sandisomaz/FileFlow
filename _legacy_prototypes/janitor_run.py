from fileflow.operations.janitor import PruneExecutor
from pathlib import Path

def run_janitor():
    janitor = PruneExecutor(dry_run=False)
    manifest_path = Path(r"C:\Users\sandi\Desktop\Courses\_FileFlow_Final_Clean_V7\Forensic_Manifest.json")
    
    print(f"Loading manifest: {manifest_path}")
    report = janitor.purge_from_manifest(manifest_path)
    
    print("\n--- JANITOR PURGE REPORT ---")
    print(f"Files Deleted: {report['deleted']}")
    print(f"Space Reclaimed: {report['space_reclaimed_bytes'] / (1024*1024):.2f} MB")
    
    if report['errors']:
        print("\nErrors encountered:")
        for err in report['errors']:
            print(f" - {err}")
            
    print("\nStarting Prune Protocol (Empty Folders)...")
    pruned_count = janitor.execute_prune(Path(r"C:\Users\sandi\Desktop\Courses\applications"))
    print(f"Empty Folders Pruned: {pruned_count}")

if __name__ == "__main__":
    run_janitor()
