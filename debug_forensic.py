from fileflow.staging.manager import forensic_worker, StagingManager
from fileflow.intelligence.extractor import UnifiedExtractor
from pathlib import Path
import sys
import json

# Test file for Filename Rescue (Dummy PDF created for this purpose)
test_file = Path(r"C:\Users\sandi\Desktop\FileFlow\test_Application_for_Judges_Secretary.pdf")

print(f"Testing: {test_file}")

print("\n--- Running Manager Integration with Dirty Scraper ---")
extractor = UnifiedExtractor()
manager = StagingManager(extractor)

try:
    # This should now trigger _dirty_scrape internally if PDF read fails
    manager.stage_file(test_file)
    
    print("Staging Complete. Preview:")
    preview = manager.get_preview()
    # Iterate and print only the entity keys to confirm
    for entity in preview.keys():
        print(f"FOUND ENTITY: {entity}")
        
    print(json.dumps(preview, indent=2))
    
    # Check if it was recovered or still fully quarantined
    if "_Quarantine" in preview:
        print("\nResult: Still Quarantined (Scraping Failed or Empty)")
    else:
        print("\nResult: SUCCESS! Recovered via Scraping!")
        
except Exception as e:
    print(f"Manager Error: {e}")
