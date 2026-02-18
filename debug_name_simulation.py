from fileflow.intelligence.extractor import UnifiedExtractor
from pathlib import Path

# Simulation Data from User Screenshots
filenames = [
    "CV_Rex_Stone_for_Vezi_De_Beer_Inc_Attorneys.pdf",
    "CV_Rex_Stone_for_Burger_Huyser_Attorneys.pdf",
    "Cover_Letter_CV_Rex_Stone_for_Jonathan_Cohen_&_Associates.pdf",
    "2015_11_FEBRUARY_PART-1.pdf",
    "ESTATES-PAPER-2_15-MARCH-2022.pdf",
    "PART 2_ANSWERS_FINAL 2022.pdf",
    "2021_17-March_PART-2_FINAL.pdf"
]

extractor = UnifiedExtractor()

print("🔍 SIMULATION REPORT:")
print(f"{'FILENAME':<60} | {'ENTITY':<25} | {'SUBTYPE'}")
print("-" * 100)

for name in filenames:
    # Create a dummy path
    p = Path(f"C:/Fake/{name}")
    
    # 1. Try filename rescue (since text likely won't match "Reference Number" for these)
    meta = extractor.extract_metadata(text="", file_path=p)
    
    entity = meta.get('entity', '❌ FAILED')
    subtype = meta.get('sub_type', 'N/A')
    
    print(f"{name[:60]:<60} | {entity:<25} | {subtype}")
