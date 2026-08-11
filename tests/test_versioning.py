"""
Unit tests for Versioning engine.
"""

import pytest
import os
import time
from pathlib import Path
from datetime import datetime
from app.muscle.versioning import Versioning


class TestVersioning:
    """Test suite for filename generation."""
    
    def test_date_extraction_from_file(self, tmp_path):
        """Test that file modification time is correctly extracted."""
        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.touch()
        
        # Set modification time to specific past date
        target_date = datetime(2024, 10, 15)
        timestamp = target_date.timestamp()
        os.utime(test_file, (timestamp, timestamp))
        
        # Generate filename
        result = Versioning.generate_name(
            entity="Test_Entity",
            original_path=test_file,
            index=1,
            metadata={'sub_type': 'CV'}
        )
        
        # Should contain the file's date
        assert "20241015" in result
        assert "Test_Entity_CV_20241015_v1.pdf" == result
    
    def test_date_extraction_from_filename(self):
        """Test fallback to filename date parsing."""
        fake_path = Path("CV_20240523_final.pdf")
        
        # Even if file doesn't exist, should extract date from name if stat fails
        # (Though _extract_file_date now tries stat first)
        date_str = Versioning._extract_file_date(fake_path)
        
        assert date_str == "20240523"
    
    def test_subtype_in_filename(self, tmp_path):
        """Test that SubType appears in final filename."""
        test_file = tmp_path / "document.pdf"
        test_file.touch()
        
        result = Versioning.generate_name(
            entity="Judges_Secretary",
            original_path=test_file,
            index=2,
            metadata={'sub_type': 'Z83'}
        )
        
        assert "Z83" in result
        assert "_v2" in result
    
    def test_entity_abbreviation(self, tmp_path):
        """Test that long entity names are abbreviated."""
        test_file = tmp_path / "file.pdf"
        test_file.touch()
        
        result = Versioning.generate_name(
            entity="Uif_Client_Service_Officer",
            original_path=test_file,
            index=1,
            metadata={'sub_type': 'CV'}
        )
        
        # Should be abbreviated
        assert "UIF_CSO" in result
        assert "Uif_Client_Service_Officer" not in result
    
    def test_duplicate_marking(self, tmp_path):
        """Test that duplicates get DUP marker."""
        test_file = tmp_path / "dup.pdf"
        test_file.touch()
        
        result = Versioning.generate_name(
            entity="Test",
            original_path=test_file,
            index=1,
            metadata={'sub_type': 'CV'},
            is_duplicate=True,
            duplicate_hash="abcd1234abcd1234"
        )
        
        assert "_DUP_" in result
        assert "abcd1234" in result 
    
    def test_filename_parsing(self):
        """Test parsing formatted filenames back to components."""
        filename = "Judge_Sec_CV_20241015_v3.pdf"
        parsed = Versioning.parse_filename(filename)
        
        assert parsed['entity'] == 'Judge_Sec'
        assert parsed['subtype'] == 'CV'
        assert parsed['date'] == '20241015'
        assert parsed['version'] == 3
        assert parsed['ext'] == '.pdf'
        assert parsed['is_duplicate'] == False
