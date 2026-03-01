import shutil
import os
import glob

def rescue_valid_pdfs(source_dir, dest_dir):
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        
    print(f"Scanning {source_dir}...")
    pdf_files = glob.glob(os.path.join(source_dir, "**/*.pdf"), recursive=True)
    
    rescued_count = 0
    for f in pdf_files:
        try:
            with open(f, 'rb') as pdf_file:
                header = pdf_file.read(10)
                if b'%PDF' in header:
                    shutil.copy2(f, dest_dir)
                    rescued_count += 1
        except Exception:
            pass
            
    print(f"✅ Successfully rescued {rescued_count} valid PDF files to {dest_dir}")

if __name__ == "__main__":
    SOURCE = r"C:\Users\sandi\Desktop\RECOVERED_SUCCESS_FEB10"
    DEST = r"C:\Users\sandi\Desktop\VERIFIED_GOOD_FILES"
    rescue_valid_pdfs(SOURCE, DEST)
