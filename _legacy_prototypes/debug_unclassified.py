import json
from pathlib import Path
from collections import Counter

manifest_path = Path(r"C:\Users\sandi\Desktop\Courses\_FileFlowV8_Recovered\Forensic_Manifest.json")

def analyze():
    if not manifest_path.exists():
        print(f"Error: Manifest not found at {manifest_path}")
        return

    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    print(f"--- Manifest Analysis ---")
    print(f"Total Entities: {len(manifest)}")
    
    entities = list(manifest.keys())
    
    # Classification logic mirrored from main.py for debugging
    categories = Counter()
    unclassified_files = []
    other_details = []

    government_files_found = 0
    government_distribution = Counter()
    unclassified_government_files = []

    for entity, files in manifest.items():
        for f in files:
            path_lower = f['original_path'].lower()
            if "in_a_government" in path_lower:
                government_files_found += 1
                
                # Determine its category
                file_type = f['metadata'].get('type', '')
                sub_type = f['metadata'].get('sub_type', '')
                
                if entity.startswith('REF_') or file_type == 'job_packet':
                    cat = "Job Packets (REF)"
                elif entity == "Unclassified":
                    cat = "Unclassified"
                    unclassified_government_files.append(f)
                else:
                    cat = f"Other ({entity})"
                
                government_distribution[cat] += 1

    print(f"\n--- Government Folder Trace (Goal: 269 files) ---")
    print(f"Total Government Files Processed: {government_files_found}")
    for cat, count in government_distribution.items():
        print(f"  {cat}: {count}")

    if unclassified_government_files:
        print(f"\n--- Unclassified Government Files Sample ---")
        for f in unclassified_government_files[:10]:
            print(f"  Path: {f['original_path']}")
            print(f"  Metadata: {f['metadata']}")
    else:
        print("\n✅ All Government files were classified into non-Unclassified entities!")

if __name__ == "__main__":
    analyze()
