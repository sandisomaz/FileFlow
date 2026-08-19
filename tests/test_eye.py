"""
Tests for eye.py — The Image Intelligence Engine

We test the Eye's own logic without requiring Pillow, imagehash,
or Tesseract to be installed. All external dependencies are mocked.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from app.brain.eye import (
    Eye,
    ImageInspectionResult,
    VisualDedupResult,
    IMAGE_EXTENSIONS,
    IMAGE_CATEGORIES,
)
from app.brain.bridge import Bridge
from app.memory.memory import Memory


def make_eye(
    pillow=True,
    imagehash=True,
    tesseract=True,
    bridge_healthy=False,
    memory_available=False,
    phash_threshold=10,
):
    """Helper: creates an Eye with mocked dependencies."""
    bridge = MagicMock(spec=Bridge)
    bridge.is_healthy.return_value = bridge_healthy
    bridge.generate.return_value = None

    memory = MagicMock(spec=Memory)
    memory.remember.return_value = memory_available

    eye = Eye(bridge=bridge, memory=memory, ocr_enabled=tesseract, phash_threshold=phash_threshold)
    eye._pillow_available = pillow
    eye._imagehash_available = imagehash
    eye._tesseract_available = tesseract
    return eye


# =============================================================================
# is_supported
# =============================================================================

class TestEyeIsSupported:
    def test_jpg_supported(self, tmp_path):
        eye = make_eye()
        assert eye.is_supported(tmp_path / "photo.jpg") is True

    def test_png_supported(self, tmp_path):
        eye = make_eye()
        assert eye.is_supported(tmp_path / "scan.png") is True

    def test_pdf_not_supported(self, tmp_path):
        eye = make_eye()
        assert eye.is_supported(tmp_path / "doc.pdf") is False

    def test_exe_not_supported(self, tmp_path):
        eye = make_eye()
        assert eye.is_supported(tmp_path / "setup.exe") is False

    def test_all_image_extensions_supported(self, tmp_path):
        eye = make_eye()
        for ext in IMAGE_EXTENSIONS:
            assert eye.is_supported(tmp_path / f"file{ext}") is True


# =============================================================================
# Classification
# =============================================================================

class TestEyeClassification:
    def test_classifies_scanned_doc_from_ocr(self, tmp_path):
        eye = make_eye(tesseract=False)
        ocr_text = (
            "DEPARTMENT OF JUSTICE\n"
            "APPLICATION FOR EMPLOYMENT\n"
            "Z83 FORM\n"
            "Reference Number: HR/4/4/7/56\n"
            "Position: Judge's Secretary"
        )
        category = eye._classify_image(tmp_path / "scan.jpg", ocr_text)
        assert category == "Scanned_Document"

    def test_classifies_id_document_from_ocr(self, tmp_path):
        eye = make_eye(tesseract=False)
        ocr_text = "REPUBLIC OF SOUTH AFRICA\nIDENTITY DOCUMENT\nID NUMBER: 9001015800088"
        category = eye._classify_image(tmp_path / "id.jpg", ocr_text)
        assert category == "ID_Document"

    def test_classifies_certificate_from_ocr(self, tmp_path):
        eye = make_eye(tesseract=False)
        ocr_text = "UNIVERSITY OF PRETORIA\nHEREBY CERTIFY that this certificate is awarded to\nJane Doe"
        category = eye._classify_image(tmp_path / "cert.jpg", ocr_text)
        assert category == "Certificate"

    def test_classifies_photo_from_filename(self, tmp_path):
        eye = make_eye(tesseract=False)
        category = eye._classify_image(tmp_path / "IMG_20240312.jpg", "")
        assert category == "Photo"

    def test_classifies_screenshot_from_filename(self, tmp_path):
        eye = make_eye(tesseract=False)
        category = eye._classify_image(tmp_path / "screenshot_2024.png", "")
        assert category == "Screenshot"

    def test_unknown_image_fallback(self, tmp_path):
        eye = make_eye(tesseract=False, bridge_healthy=False)
        category = eye._classify_image(tmp_path / "random_file.jpg", "")
        assert category == "Unknown_Image"


# =============================================================================
# Summarisation
# =============================================================================

class TestEyeSummarise:
    def test_ocr_derived_summary(self, tmp_path):
        eye = make_eye(bridge_healthy=False)
        summary = eye._summarise(
            tmp_path / "scan.jpg",
            ocr_text="APPLICATION FOR EMPLOYMENT Z83 FORM\nDepartment of Justice",
            category="Scanned_Document",
        )
        assert "Scanned Document" in summary or "APPLICATION" in summary

    def test_filename_fallback_summary(self, tmp_path):
        eye = make_eye(bridge_healthy=False)
        summary = eye._summarise(
            tmp_path / "id_document_scan.jpg",
            ocr_text="",
            category="ID_Document",
        )
        assert "Id Document" in summary or "ID" in summary.upper()

    def test_vision_model_summary_used_when_available(self, tmp_path):
        eye = make_eye(bridge_healthy=True)
        eye.bridge.generate.return_value = "Z83 application form for Judge's Secretary position."
        f = tmp_path / "scan.jpg"
        f.write_bytes(b"fake image data")
        with patch("builtins.open", create=True), \
             patch("base64.b64encode", return_value=b"fakebase64"):
            summary = eye._ask_vision_model_summary(f, "Scanned_Document")
        # Should return the vision model's response
        assert summary is not None


# =============================================================================
# Perceptual Hashing
# =============================================================================

class TestEyePhash:
    def test_phash_returns_none_without_pillow(self, tmp_path):
        eye = make_eye(pillow=False, imagehash=False)
        result = eye._compute_phash(tmp_path / "img.jpg")
        assert result is None

    def test_phash_returns_string_with_mocked_libs(self, tmp_path):
        import sys
        import types

        eye = make_eye(pillow=True, imagehash=True)
        f = tmp_path / "img.jpg"
        f.write_bytes(b"fake")

        # Build a minimal fake imagehash module
        fake_imagehash = types.ModuleType("imagehash")
        mock_hash = MagicMock()
        mock_hash.__str__ = lambda self: "a3f2b1c4d5e6f7a8"
        fake_imagehash.phash = MagicMock(return_value=mock_hash)

        # Build a minimal fake PIL.Image module
        fake_pil = types.ModuleType("PIL")
        fake_image_mod = types.ModuleType("PIL.Image")
        mock_img_ctx = MagicMock()
        mock_img_ctx.__enter__ = lambda s: MagicMock()
        mock_img_ctx.__exit__ = MagicMock(return_value=False)
        fake_image_mod.open = MagicMock(return_value=mock_img_ctx)
        fake_pil.Image = fake_image_mod

        original_imagehash = sys.modules.get("imagehash")
        original_pil = sys.modules.get("PIL")
        original_pil_image = sys.modules.get("PIL.Image")

        try:
            sys.modules["imagehash"] = fake_imagehash
            sys.modules["PIL"] = fake_pil
            sys.modules["PIL.Image"] = fake_image_mod
            result = eye._compute_phash(f)
        finally:
            # Restore originals
            if original_imagehash is None:
                sys.modules.pop("imagehash", None)
            else:
                sys.modules["imagehash"] = original_imagehash
            if original_pil is None:
                sys.modules.pop("PIL", None)
            else:
                sys.modules["PIL"] = original_pil
            if original_pil_image is None:
                sys.modules.pop("PIL.Image", None)
            else:
                sys.modules["PIL.Image"] = original_pil_image

        assert result is not None

    def test_hamming_distance_identical(self):
        """Identical hash objects should have distance 0."""
        mock_a = MagicMock()
        mock_a.__sub__ = lambda self, other: 0
        assert Eye._hamming_distance(mock_a, mock_a) == 0

    def test_hamming_distance_error_returns_max(self):
        """On error, should return 64 (max distance)."""
        bad = object()  # Not a valid hash
        result = Eye._hamming_distance(bad, bad)
        assert result == 64


# =============================================================================
# Visual Dedup
# =============================================================================

class TestEyeVisualDedup:
    def test_returns_empty_without_pillow(self, tmp_path):
        eye = make_eye(pillow=False, imagehash=False)
        result = eye.find_visual_duplicates(tmp_path)
        assert result == []

    def test_finds_identical_images(self, tmp_path):
        """Two images with the same phash should be flagged as duplicates."""
        eye = make_eye(pillow=True, imagehash=True)

        # Create two fake image files
        (tmp_path / "a.jpg").write_bytes(b"fake")
        (tmp_path / "b.jpg").write_bytes(b"fake")

        # Mock phash to return the same hash for both
        mock_hash = MagicMock()
        mock_hash.__str__ = lambda self: "0000000000000000"
        mock_hash.__sub__ = lambda self, other: 0  # Distance = 0

        with patch.object(eye, "_compute_phash", return_value="0000000000000000"), \
             patch.object(eye, "_str_to_phash", return_value=mock_hash):
            dupes = eye.find_visual_duplicates(tmp_path, recursive=False)

        assert len(dupes) == 1
        assert dupes[0].hamming_distance == 0
        assert dupes[0].similarity_pct == 100.0

    def test_no_duplicates_when_different(self, tmp_path):
        """Images with high hamming distance should not be flagged."""
        eye = make_eye(pillow=True, imagehash=True, phash_threshold=5)

        (tmp_path / "a.jpg").write_bytes(b"fake")
        (tmp_path / "b.jpg").write_bytes(b"fake")

        hash_a = MagicMock()
        hash_a.__sub__ = lambda self, other: 20  # Distance = 20 > threshold 5

        with patch.object(eye, "_compute_phash", return_value="abc123"), \
             patch.object(eye, "_str_to_phash", return_value=hash_a):
            dupes = eye.find_visual_duplicates(tmp_path, recursive=False)

        assert dupes == []


# =============================================================================
# Full Inspection Pipeline
# =============================================================================

class TestEyeInspect:
    def test_returns_error_for_missing_file(self, tmp_path):
        eye = make_eye()
        result = eye.inspect_image(tmp_path / "nonexistent.jpg")
        assert result.error == "File not found"

    def test_returns_error_for_unsupported_extension(self, tmp_path):
        eye = make_eye()
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake")
        result = eye.inspect_image(f)
        assert "Unsupported extension" in result.error

    def test_inspect_sets_category(self, tmp_path):
        eye = make_eye(tesseract=False, pillow=False, imagehash=False)
        f = tmp_path / "screenshot_2024.png"
        f.write_bytes(b"fake")
        result = eye.inspect_image(f)
        assert result.category == "Screenshot"
        assert result.file_path == f

    def test_embedded_true_when_memory_stores(self, tmp_path):
        eye = make_eye(tesseract=False, pillow=False, imagehash=False, memory_available=True)
        f = tmp_path / "scan_z83.jpg"
        f.write_bytes(b"fake")
        # Give it a summary so it tries to embed
        with patch.object(eye, "_summarise", return_value="Z83 application form."):
            result = eye.inspect_image(f)
        assert result.embedded is True


# =============================================================================
# Status
# =============================================================================

class TestEyeStatus:
    def test_status_reflects_capabilities(self):
        eye = make_eye(pillow=True, imagehash=True, tesseract=False)
        status = eye.status()
        assert status["pillow"] is True
        assert status["imagehash"] is True
        assert status["tesseract_ocr"] is False
        assert "phash_threshold" in status

    def test_status_vision_false_when_bridge_offline(self):
        eye = make_eye(bridge_healthy=False)
        status = eye.status()
        assert status["vision_model"] is False
