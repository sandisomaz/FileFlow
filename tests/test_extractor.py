"""
Unit tests for UnifiedExtractor.
"""

import pytest
from pathlib import Path
from fileflow.intelligence.extractor import UnifiedExtractor


class TestUnifiedExtractor:
    """Test suite for metadata extraction and classification."""
    
    def setup_method(self):
        """Initialize extractor before each test."""
        self.extractor = UnifiedExtractor()
    
    def test_classify_application_summary(self):
        """Test that Application_for files are classified as AppSummary."""
        path = Path("Sandiso_Mazibuko_Application_for_Judge_at_Office.pdf")
        result = self.extractor.classify_sub_type(path)
        assert result == "AppSummary"
        
    def test_classify_z83_stamped(self):
        """Test that Z83 Stamped files are classified correctly."""
        path = Path("Z83_Stamped.pdf")
        result = self.extractor.classify_sub_type(path)
        assert result == "Z83_Stamped"
    
    def test_classify_cv_from_filename(self):
        """Test CV classification from filename."""
        path = Path("CV_Sandiso_Mazibuko.pdf")
        result = self.extractor.classify_sub_type(path)
        assert result == "CV"
    
    def test_classify_z83_from_filename(self):
        """Test Z83 classification from filename."""
        # Note: if it has "Stamped" it goes to Z83_Stamped, otherwise Z83
        path = Path("Z83_Ref_123.pdf")
        result = self.extractor.classify_sub_type(path)
        assert result == "Z83"
    
    def test_classify_cover_letter(self):
        """Test cover letter classification."""
        path = Path("Cover_Letter_Bowmans.docx")
        result = self.extractor.classify_sub_type(path)
        assert result == "CoverLetter"
    
    def test_classify_certificate(self):
        """Test certificate/ID classification."""
        path = Path("Drivers_License_Copy.pdf")
        result = self.extractor.classify_sub_type(path)
        assert result == "Certificate"
    
    def test_extract_entity_from_job_packet(self):
        """Test entity extraction from job packet filename."""
        filename = "Sandiso_Mazibuko_Application_for_Judges_Secretary_at_Office.pdf"
        result = self.extractor.extract_from_filename(filename)
        
        assert result['entity'] == "Judges_Secretary"
        assert result['type'] == "job_packet"
    
    def test_extract_entity_from_firm_application(self):
        """Test entity extraction from firm application."""
        filename = "CV_Sandiso_Mazibuko_for_Bowmans_Inc_2024.pdf"
        result = self.extractor.extract_from_filename(filename)
        
        assert result['entity'] == "Bowmans_Inc"
        assert result['type'] == "firm_application"
    
    def test_generic_document_fallback(self):
        """Test that unrecognized files get 'Document' type."""
        path = Path("random_file_12345.pdf")
        result = self.extractor.classify_sub_type(path)
        assert result == "Document"
