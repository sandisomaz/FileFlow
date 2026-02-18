import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fileflow.intelligence.extractor import UnifiedExtractor
from fileflow.staging.manager import StagingManager

def test_unbucketing_logic():
    # 1. Setup Mock Extractor
    extractor = UnifiedExtractor()
    z83_text = """
    REPUBLIC OF SOUTH AFRICA
    Position for which you are applying: LEGAL ADMIN OFFICER
    Reference number: HR4/4/7/210
    Surname and Full names: MAZIBUKO SANDISO
    """
    
    # Patch the extractor to return our fake text
    extractor._read_pdf_text = MagicMock(return_value=z83_text)
    
    # 2. Setup Staging Manager
    staging = StagingManager(extractor)
    
    # 3. Patch Path.stat and hashing to avoid disk hits
    with patch.object(Path, 'stat') as mock_stat, \
         patch.object(StagingManager, '_calculate_content_hash') as mock_hash:
        
        mock_stat.return_value.st_size = 1024
        mock_stat.return_value.st_mtime = 123456789
        mock_hash.return_value = "fake_hash_123"
        
        generic_path = Path("C:/Source/bucket/in_a_government_1.pdf")
        
        # Run staging
        staging.stage_file(generic_path)
    
    # Verify it was re-assigned to the Reference Number entity
    assert "REF_HR4_4_7_210" in staging.staged_files
    assert len(staging.staged_files["REF_HR4_4_7_210"]) == 1
    assert "in_a_government" not in staging.staged_files

def test_sibling_packet_reassociation():
    # Test that files in the same folder as a Z83 get grouped into the same Reference entity
    extractor = UnifiedExtractor()
    
    def mock_read(path):
        if "in_a_government_1" in str(path):
            return "Reference number: HR4/4/7/210\nPosition: LEGAL OFFICER"
        return "Normal document text"
        
    extractor._read_pdf_text = MagicMock(side_effect=mock_read)
    staging = StagingManager(extractor)
    
    with patch.object(Path, 'stat') as mock_stat, \
         patch.object(StagingManager, '_calculate_content_hash') as mock_hash:
        
        mock_stat.return_value.st_size = 1
        mock_stat.return_value.st_mtime = 1
        mock_hash.side_effect = ["hash1", "hash2"]
        
        # File 1: Generic Z83 with internal Ref
        f1 = Path("C:/Source/bucket/in_a_government_1.pdf")
        
        # File 2: Generic CV in same folder
        f2 = Path("C:/Source/bucket/in_a_government_2.pdf")
        
        staging.stage_file(f1)
        staging.stage_file(f2)
    
    # Resolve contexts
    staging._resolve_folder_contexts()
    
    # Both should now be in the REF folder because they are in the same parent
    # and f1 provided the anchor (REF_HR4_4_7_210)
    assert "REF_HR4_4_7_210" in staging.staged_files
    assert len(staging.staged_files["REF_HR4_4_7_210"]) == 2
