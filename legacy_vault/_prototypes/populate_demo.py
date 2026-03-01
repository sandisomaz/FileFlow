import shutil
import os
import glob
from pathlib import Path

def populate_demo_folder():
    # 1. Define Paths
    desktop = Path(os.path.expanduser("~/Desktop"))
    demo_folder = desktop / "INTERNSHIP_DEMO_SOURCE"
    verified_source = desktop / "VERIFIED_GOOD_FILES"
    school_source = desktop / "school"
    
    # 2. Create Destination
    if not demo_folder.exists():
        demo_folder.mkdir()
        print(f"Created demo folder: {demo_folder}")
    else:
        print(f"Demo folder exists: {demo_folder}")

    count = 0
    
    # 3. Import Verified "Good" Files (The Recovery Win)
    if verified_source.exists():
        print(f"Importing verified files from {verified_source.name}...")
        for f in verified_source.glob("*.pdf"):
            try:
                shutil.copy2(f, demo_folder / f.name)
                count += 1
            except Exception as e:
                print(f"Error copying {f.name}: {e}")
    else:
        print("⚠️ VERIFIED_GOOD_FILES not found. Skipping.")

    # 4. Import "School" Files (The Chaos/Noise)
    if school_source.exists():
        print(f"Importing entropy from {school_source.name}...")
        # Grab a mix of files to show the system handles non-PDFs too
        extensions = ['*.pdf', '*.docx', '*.xlsx', '*.txt']
        for ext in extensions:
            for f in school_source.rglob(ext):
                # Avoid huge files for demo speed
                if f.stat().st_size < 10 * 1024 * 1024: # < 10MB
                    try:
                        # flatten structure for maximum chaos
                        dest_name = f"{f.parent.name}_{f.name}" if f.parent.name != "school" else f.name
                        shutil.copy2(f, demo_folder / dest_name)
                        count += 1
                    except Exception:
                        pass
    
    print(f"\n✅ DEMO READY. {count} files prepared in {demo_folder.name}")
    print("next step: Download your recent sent emails and drag them in here manually.")

if __name__ == "__main__":
    populate_demo_folder()
