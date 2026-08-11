"""
Unit tests for UnifiedExtractor.

NOTE: rewritten against the current extractor.py. The previous version of
this file tested an older classify_sub_type(path) — filename-only, single
argument — that classified into categories like "AppSummary", "Z83_Stamped",
"Certificate", "Document". The current classify_sub_type(path, text) is
content-first (falls back to filename), and returns a different, smaller
set of sub-types: "Z83", "CV", "CoverLetter", "Recovered_Fragment",
"Supporting_Doc". This file tests that current behavior instead of the
old one.
"""

import pytest
from pathlib import Path
from app.brain.extractor import UnifiedExtractor


class TestClassifySubType:
    """
    classify_sub_type(path, text) — content is checked first (via `text`),
    filename is the fallback. Default when nothing matches is
    "Supporting_Doc", not "Document".
    """

    def setup_method(self):
        self.extractor = UnifiedExtractor()

    def test_z83_detected_from_content(self):
        path = Path("random_scan_003.pdf")
        text = "APPLICATION FOR EMPLOYMENT Z83 FORM. Position: Judge's Secretary."
        assert self.extractor.classify_sub_type(path, text) == "Z83"

    def test_z83_falls_back_to_supporting_doc_without_filename_match(self):
        # CORRECTED EXPECTATION: unlike CV and CoverLetter, the current
        # classify_sub_type() has no filename fallback for Z83 — it only
        # checks extracted text ("z83" in t_low). A file literally named
        # "Z83_Ref_123.pdf" with no extractable text (e.g. a scanned
        # image or corrupted PDF) currently falls through to
        # "Supporting_Doc". Worth a product decision: Z83 forms are
        # central to this tool's stated purpose, and CV/CoverLetter both
        # get a filename safety net for exactly this failure mode — Z83
        # doesn't. Flagging, not silently changing extractor.py.
        path = Path("Z83_Ref_123.pdf")
        assert self.extractor.classify_sub_type(path, text="") == "Supporting_Doc"

    def test_cv_detected_from_content(self):
        path = Path("document.pdf")
        text = "CURRICULUM VITAE\nWork Experience\nEducation"
        assert self.extractor.classify_sub_type(path, text) == "CV"

    def test_cv_detected_from_filename(self):
        path = Path("CV_Sandiso_Mazibuko.pdf")
        assert self.extractor.classify_sub_type(path, text="") == "CV"

    def test_cover_letter_detected_from_content(self):
        path = Path("letter.docx")
        text = "Dear Hiring Manager, please find attached my cover letter."
        assert self.extractor.classify_sub_type(path, text) == "CoverLetter"

    def test_cover_letter_detected_from_filename(self):
        path = Path("Cover_Letter_Bowmans.docx")
        assert self.extractor.classify_sub_type(path, text="") == "CoverLetter"

    def test_recovered_fragment_marker(self):
        # BUGFIX: the original filename "recovered_001.pdf" contains
        # "cover" as a substring (re-COVER-ed), which matched the
        # CoverLetter filename check on the line above Recovered_Fragment
        # in classify_sub_type() — the test was silently checking the
        # wrong branch. Renamed to a filename with no substring collision.
        path = Path("fragment_001.pdf")
        text = "scraped_from_corrupt_file some partial garbage text here"
        assert self.extractor.classify_sub_type(path, text) == "Recovered_Fragment"

    def test_unrecognized_file_falls_back_to_supporting_doc(self):
        # REGRESSION GUARD: the old test asserted this returns "Document" —
        # the current default is "Supporting_Doc". If this ever starts
        # returning "Document" again, something reverted without the
        # rest of the pipeline (which expects "Supporting_Doc") being
        # updated to match.
        path = Path("random_file_12345.pdf")
        assert self.extractor.classify_sub_type(path, text="") == "Supporting_Doc"

    def test_content_takes_priority_over_filename(self):
        # Filename says CV, content says Z83 — content should win per the
        # method's own stated priority (content first, filename fallback).
        path = Path("CV_looking_file.pdf")
        text = "APPLICATION FOR EMPLOYMENT Z83 FORM"
        assert self.extractor.classify_sub_type(path, text) == "Z83"


class TestExtractFromFilename:
    """
    extract_from_filename() is currently a stub — it unconditionally
    returns {}. Nothing in the actual pipeline calls this method;
    unpacker.py has its own separate _entity_from_filename() that does
    real filename-based entity extraction under a different name.
    This test documents the current (stub) behavior rather than asserting
    fictional entity-extraction results the method doesn't implement.
    """

    def setup_method(self):
        self.extractor = UnifiedExtractor()

    def test_currently_returns_empty_dict(self):
        result = self.extractor.extract_from_filename(
            "Sandiso_Mazibuko_Application_for_Judges_Secretary_at_Office.pdf"
        )
        assert result == {}, (
            "extract_from_filename() changed from its documented stub "
            "behavior — if real logic was added, update this test to "
            "cover it properly instead of just asserting {}."
        )
