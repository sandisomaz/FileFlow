import pypdf
from pathlib import Path
import os

FOLDER = Path(r"C:\Users\sandi\Desktop\LIVE_DEMO_CHAOS")

def check_files():
    print(f"🔍 Scanning {FOLDER}...")
    if not FOLDER.exists():
        print("❌ Folder not found!")
        return

    corrupt_count = 0
    valid_count = 0

    for f in FOLDER.glob("*.pdf"):
        try:
            if f.stat().st_size == 0:
                print(f"❌ ZERO BYTE: {f.name}")
                f.unlink()
                corrupt_count += 1
                continue

            with open(f, 'rb') as pdf_file:
                # Check Header
                header = pdf_file.read(4)
                if header != b'%PDF':
                    print(f"❌ BAD HEADER: {f.name}")
                    # Close before delete
                
            # Check Structure with pypdf
            reader = pypdf.PdfReader(f)
            if len(reader.pages) > 0:
                # Try reading page 1 text to be sure
                _ = reader.pages[0].extract_text()
                # print(f"✅ OK: {f.name}")
                valid_count += 1
            else:
                print(f"❌ NO PAGES: {f.name}")
                f.unlink()
                corrupt_count += 1

        except Exception as e:
            print(f"❌ EXCEPTION ({e}): {f.name}")
            try:
                f.unlink()
                corrupt_count += 1
            except:
                print(f"   ⚠️ Could not delete {f.name}")

    print(f"\n📊 Summary:")
    print(f"   ✅ Valid: {valid_count}")
    print(f"   ❌ Corrupt/Deleted: {corrupt_count}")

if __name__ == "__main__":
    check_files()
