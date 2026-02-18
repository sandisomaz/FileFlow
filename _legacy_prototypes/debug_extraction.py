from fileflow.intelligence.text_extractor import TextExtractor
from pathlib import Path

def debug_pdf(path_str):
    path = Path(path_str)
    extractor = TextExtractor()
    
    # 1. Read Raw Text
    text = extractor._read_pdf_text(path)
    # print("--- RAW TEXT START ---")
    # print(text[:1000]) # First 1000 chars
    # print("--- RAW TEXT END ---")
    
    # 2. Test Extraction
    import re
    text = extractor._read_pdf_text(path)
    print("\n--- REGEX DEBUG ---")
    # Paste the regex from text_extractor.py
    pattern = r'(?:Position for which you are applying|Position|POSITION).*?[:\s]+([A-Za-z\s&]+?)(?:\n|Department|Reference)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    print(f"Matches for 'Position': {matches}")
    
    metadata = extractor.extract_metadata(path)
    print("\n--- EXTRACTED METADATA ---")
    print(metadata)

if __name__ == "__main__":
    # Point to one of the bad files
    target = r"C:\Users\sandi\Desktop\Courses\_FileFlow_Staging_Area\in_a_government\in_a_government_75.pdf"
    debug_pdf(target)
