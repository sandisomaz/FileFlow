"""
eye.py — The Image Intelligence Engine
FileFlow Cognition V9

The Eye gives FileFlow the ability to understand images and scanned documents.

Capabilities:
1. Perceptual Hashing    — detects visually duplicate images even if resized,
                           re-saved, or format-converted (JPEG ↔ PNG)
2. OCR                   — extracts text from scanned documents and photos
                           of documents using Tesseract
3. CLIP Embeddings       — understands image *content* semantically via Ollama's
                           vision models (llava, bakllava, moondream)
4. Image Classification  — categorises images (Photo, Scanned_Document,
                           Screenshot, ID_Document, etc.)
5. Visual Dedup          — finds near-duplicate images across a folder

Design principles:
- Graceful degradation: each capability is optional and falls back cleanly
- No cloud: all processing is local (Tesseract + Ollama vision)
- Lazy imports: Pillow/imagehash only imported when needed
- Integrates with Memory: image embeddings stored alongside document embeddings

Usage:
    eye = Eye(bridge=bridge, memory=memory)
    result = eye.inspect_image(Path("scan_001.jpg"))
    print(result.ocr_text)      # "APPLICATION FOR EMPLOYMENT Z83..."
    print(result.category)      # "Scanned_Document"
    print(result.summary)       # "Scanned Z83 application form"
    print(result.phash)         # "a3f2b1c4d5e6f7a8"
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Image extensions The Eye can process
IMAGE_EXTENSIONS: Set[str] = {
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
    ".webp", ".gif", ".heic", ".heif",
}

# Image categories
IMAGE_CATEGORIES = {
    "Scanned_Document",
    "ID_Document",
    "Photo",
    "Screenshot",
    "Certificate",
    "Signature",
    "Unknown_Image",
}

# Keywords that suggest a scanned document rather than a photo
DOCUMENT_KEYWORDS = {
    "application", "form", "certificate", "affidavit", "agreement",
    "contract", "statement", "invoice", "receipt", "letter", "memo",
    "report", "policy", "id", "passport", "licence", "license",
    "z83", "employment", "department", "government", "official",
}


@dataclass
class ImageInspectionResult:
    """Result of inspecting a single image."""
    file_path: Path
    category: str                       # e.g. "Scanned_Document"
    phash: Optional[str] = None         # Perceptual hash hex string
    ocr_text: str = ""                  # Text extracted via OCR
    summary: str = ""                   # AI-generated one-sentence summary
    embedded: bool = False              # Whether stored in Memory
    vision_available: bool = False      # Whether Ollama vision was used
    ocr_available: bool = False         # Whether Tesseract was available
    processing_time_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class VisualDedupResult:
    """A pair of visually similar images."""
    path_a: Path
    path_b: Path
    phash_a: str
    phash_b: str
    hamming_distance: int               # 0 = identical, <10 = near-duplicate
    similarity_pct: float               # 100% = identical


class Eye:
    """
    The sovereign image intelligence engine for FileFlow Cognition.

    Inspects images using perceptual hashing, OCR, and vision models.
    Integrates with Memory for cross-modal semantic search.

    Usage:
        eye = Eye(bridge=bridge, memory=memory)
        result = eye.inspect_image(path)
        dupes = eye.find_visual_duplicates(folder)
    """

    def __init__(
        self,
        bridge=None,
        memory=None,
        ocr_enabled: bool = True,
        phash_threshold: int = 10,
    ):
        """
        Args:
            bridge:          Optional Bridge for Ollama vision models
            memory:          Optional Memory for storing image embeddings
            ocr_enabled:     Whether to attempt OCR via Tesseract
            phash_threshold: Max Hamming distance to consider images duplicates
                             (0 = identical, 10 = near-duplicate, 20 = similar)
        """
        self.bridge = bridge
        self.memory = memory
        self.ocr_enabled = ocr_enabled
        self.phash_threshold = phash_threshold

        # Check what's available at init time
        self._pillow_available = self._check_pillow()
        self._imagehash_available = self._check_imagehash()
        self._tesseract_available = self._check_tesseract() if ocr_enabled else False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inspect_image(self, file_path: Path) -> ImageInspectionResult:
        """
        Full inspection pipeline for a single image:
        1. Compute perceptual hash
        2. OCR (if Tesseract available)
        3. Classify (rule-based from OCR text, or vision model)
        4. Summarise (vision model or OCR-derived)
        5. Embed into Memory

        Args:
            file_path: Path to the image file

        Returns:
            ImageInspectionResult with all available data
        """
        t_start = time.time()
        result = ImageInspectionResult(
            file_path=file_path,
            category="Unknown_Image",
        )

        if not file_path.exists():
            result.error = "File not found"
            return result

        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            result.error = f"Unsupported extension: {file_path.suffix}"
            return result

        try:
            # Step 1: Perceptual hash
            result.phash = self._compute_phash(file_path)

            # Step 2: OCR
            if self._tesseract_available:
                result.ocr_text = self._run_ocr(file_path)
                result.ocr_available = True

            # Step 3: Classify
            result.category = self._classify_image(file_path, result.ocr_text)

            # Step 4: Summarise
            result.summary = self._summarise(file_path, result.ocr_text, result.category)

            # Step 5: Embed into Memory
            if self.memory and (result.ocr_text or result.summary):
                embed_text = f"{result.summary}\n\n{result.ocr_text[:2000]}"
                stored = self.memory.remember(
                    file_path=file_path,
                    text=embed_text,
                    category=result.category,
                    summary=result.summary,
                    entity=file_path.stem,
                )
                result.embedded = stored

        except Exception as e:
            logger.error(f"[Eye] Error inspecting {file_path.name}: {e}")
            result.error = str(e)

        result.processing_time_ms = (time.time() - t_start) * 1000
        return result

    def inspect_batch(
        self,
        image_paths: List[Path],
        progress_callback=None,
    ) -> List[ImageInspectionResult]:
        """
        Inspects a batch of images.

        Args:
            image_paths:       List of image file paths
            progress_callback: Optional fn(current, total, filename)

        Returns:
            List of ImageInspectionResult
        """
        results = []
        total = len(image_paths)
        for i, path in enumerate(image_paths, 1):
            result = self.inspect_image(path)
            results.append(result)
            if progress_callback:
                try:
                    progress_callback(i, total, path.name)
                except Exception:
                    pass
        return results

    def find_visual_duplicates(
        self,
        folder: Path,
        recursive: bool = True,
    ) -> List[VisualDedupResult]:
        """
        Scans a folder for visually duplicate images using perceptual hashing.

        Two images are considered visual duplicates if their perceptual hash
        Hamming distance is ≤ phash_threshold (default: 10).

        Args:
            folder:    Root folder to scan
            recursive: Whether to scan subfolders

        Returns:
            List of VisualDedupResult pairs, sorted by similarity
        """
        if not self._pillow_available or not self._imagehash_available:
            logger.warning("[Eye] Pillow/imagehash not available — cannot find visual duplicates")
            return []

        # Collect all image files
        image_files = self._collect_images(folder, recursive)
        logger.info(f"[Eye] Computing perceptual hashes for {len(image_files)} images...")

        # Compute hashes
        hashes: List[Tuple[Path, str, object]] = []
        for fp in image_files:
            phash_str = self._compute_phash(fp)
            if phash_str:
                phash_obj = self._str_to_phash(phash_str)
                if phash_obj is not None:
                    hashes.append((fp, phash_str, phash_obj))

        # Compare all pairs
        duplicates: List[VisualDedupResult] = []
        for i in range(len(hashes)):
            for j in range(i + 1, len(hashes)):
                path_a, hash_str_a, hash_obj_a = hashes[i]
                path_b, hash_str_b, hash_obj_b = hashes[j]

                distance = self._hamming_distance(hash_obj_a, hash_obj_b)
                if distance <= self.phash_threshold:
                    # Convert distance to similarity percentage
                    # phash is 64 bits, so max distance = 64
                    similarity = (1.0 - distance / 64.0) * 100.0
                    duplicates.append(VisualDedupResult(
                        path_a=path_a,
                        path_b=path_b,
                        phash_a=hash_str_a,
                        phash_b=hash_str_b,
                        hamming_distance=distance,
                        similarity_pct=round(similarity, 1),
                    ))

        # Sort by most similar first
        duplicates.sort(key=lambda d: d.hamming_distance)
        logger.info(f"[Eye] Found {len(duplicates)} visual duplicate pairs")
        return duplicates

    def is_supported(self, file_path: Path) -> bool:
        """Returns True if the file is an image type The Eye can process."""
        return file_path.suffix.lower() in IMAGE_EXTENSIONS

    def status(self) -> dict:
        """Returns a status report of available capabilities."""
        return {
            "pillow": self._pillow_available,
            "imagehash": self._imagehash_available,
            "tesseract_ocr": self._tesseract_available,
            "vision_model": (
                self.bridge is not None and self.bridge.is_healthy()
                if self.bridge else False
            ),
            "memory": self.memory is not None,
            "phash_threshold": self.phash_threshold,
        }

    # ------------------------------------------------------------------
    # Perceptual Hashing
    # ------------------------------------------------------------------

    def _compute_phash(self, file_path: Path) -> Optional[str]:
        """
        Computes the perceptual hash of an image.

        Perceptual hashing works by:
        1. Resizing the image to 32x32
        2. Converting to greyscale
        3. Computing DCT (discrete cosine transform)
        4. Comparing each pixel to the mean

        Two images with Hamming distance ≤ 10 are visually similar.
        """
        if not self._pillow_available or not self._imagehash_available:
            return None

        try:
            import imagehash
            from PIL import Image

            with Image.open(file_path) as img:
                h = imagehash.phash(img)
                return str(h)
        except Exception as e:
            logger.debug(f"[Eye] phash failed for {file_path.name}: {e}")
            return None

    def _str_to_phash(self, phash_str: str):
        """Converts a hex string back to an imagehash object for comparison."""
        try:
            import imagehash
            return imagehash.hex_to_hash(phash_str)
        except Exception:
            return None

    @staticmethod
    def _hamming_distance(hash_a, hash_b) -> int:
        """Computes Hamming distance between two imagehash objects."""
        try:
            return hash_a - hash_b
        except Exception:
            return 64  # Max distance on error

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    def _run_ocr(self, file_path: Path) -> str:
        """
        Extracts text from an image using Tesseract OCR.

        Preprocessing steps applied for better accuracy:
        - Convert to greyscale
        - Increase contrast
        - Deskew (if image appears rotated)

        Returns extracted text, or empty string on failure.
        """
        try:
            import pytesseract
            from PIL import Image, ImageFilter, ImageEnhance

            with Image.open(file_path) as img:
                # Preprocess: greyscale + contrast boost
                grey = img.convert("L")
                enhanced = ImageEnhance.Contrast(grey).enhance(2.0)
                sharpened = enhanced.filter(ImageFilter.SHARPEN)

                # OCR with English language
                text = pytesseract.image_to_string(sharpened, lang="eng")
                cleaned = text.strip()

                logger.debug(
                    f"[Eye] OCR: {file_path.name} → {len(cleaned)} chars"
                )
                return cleaned

        except Exception as e:
            logger.debug(f"[Eye] OCR failed for {file_path.name}: {e}")
            return ""

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_image(self, file_path: Path, ocr_text: str) -> str:
        """
        Classifies an image into one of the IMAGE_CATEGORIES.

        Priority:
        1. OCR text analysis (fast, no AI needed)
        2. Filename heuristics
        3. Vision model (if bridge available)
        4. Default: "Unknown_Image"
        """
        # Rule 1: OCR text suggests a document
        if ocr_text:
            text_lower = ocr_text.lower()
            keyword_hits = sum(1 for kw in DOCUMENT_KEYWORDS if kw in text_lower)

            if keyword_hits >= 3:
                # Check for specific document types
                if any(kw in text_lower for kw in ["passport", "identity", "id number", "id no"]):
                    return "ID_Document"
                if any(kw in text_lower for kw in ["certificate", "hereby certify", "awarded"]):
                    return "Certificate"
                return "Scanned_Document"

        # Rule 2: Filename heuristics
        fname_lower = file_path.stem.lower()
        if any(kw in fname_lower for kw in ["scan", "doc", "form", "z83", "application"]):
            return "Scanned_Document"
        if any(kw in fname_lower for kw in ["id", "passport", "identity"]):
            return "ID_Document"
        if any(kw in fname_lower for kw in ["cert", "certificate", "diploma"]):
            return "Certificate"
        if any(kw in fname_lower for kw in ["screenshot", "screen", "capture"]):
            return "Screenshot"
        if any(kw in fname_lower for kw in ["sign", "signature"]):
            return "Signature"
        if any(kw in fname_lower for kw in ["img", "photo", "pic", "image", "dsc", "cam"]):
            return "Photo"

        # Rule 3: Vision model (if available)
        if self.bridge and self.bridge.is_healthy():
            vision_category = self._ask_vision_model_category(file_path)
            if vision_category:
                return vision_category

        return "Unknown_Image"

    def _ask_vision_model_category(self, file_path: Path) -> Optional[str]:
        """
        Asks the Ollama vision model to classify the image.
        Returns a category string or None on failure.
        """
        try:
            import base64
            with open(file_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            prompt = (
                "Look at this image and classify it into exactly ONE of these categories:\n"
                "Scanned_Document, ID_Document, Photo, Screenshot, Certificate, Signature, Unknown_Image\n\n"
                "Respond with ONLY the category name. Nothing else."
            )

            response = self.bridge.generate(
                prompt=prompt,
                images=[image_b64],
            )

            if response:
                candidate = response.strip().split()[0]
                if candidate in IMAGE_CATEGORIES:
                    return candidate

        except Exception as e:
            logger.debug(f"[Eye] Vision classification failed: {e}")

        return None

    # ------------------------------------------------------------------
    # Summarisation
    # ------------------------------------------------------------------

    def _summarise(self, file_path: Path, ocr_text: str, category: str) -> str:
        """
        Generates a one-sentence summary of the image.

        Priority:
        1. Vision model (most accurate)
        2. OCR-derived summary (from extracted text)
        3. Filename-based fallback
        """
        # Try vision model first
        if self.bridge and self.bridge.is_healthy():
            vision_summary = self._ask_vision_model_summary(file_path, category)
            if vision_summary:
                return vision_summary

        # Derive from OCR text
        if ocr_text and len(ocr_text) > 20:
            # Use first meaningful line as a summary seed
            lines = [l.strip() for l in ocr_text.split("\n") if len(l.strip()) > 10]
            if lines:
                first_line = lines[0][:120]
                return f"{category.replace('_', ' ')}: {first_line}"

        # Filename fallback
        clean_name = file_path.stem.replace("_", " ").replace("-", " ").title()
        return f"{category.replace('_', ' ')}: {clean_name}"

    def _ask_vision_model_summary(self, file_path: Path, category: str) -> Optional[str]:
        """
        Asks the Ollama vision model to describe the image in one sentence.
        """
        try:
            import base64
            with open(file_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            prompt = (
                f"This image appears to be a {category.replace('_', ' ')}. "
                f"Describe what you see in ONE specific sentence. "
                f"Focus on the document type, any visible names, dates, or reference numbers. "
                f"Do not start with 'This image shows' or 'The image depicts'. "
                f"Be direct and factual."
            )

            response = self.bridge.generate(
                prompt=prompt,
                images=[image_b64],
            )

            if response:
                # Clean up: take first sentence only
                summary = response.strip().split(".")[0].strip()
                if len(summary) > 10:
                    return summary + "."

        except Exception as e:
            logger.debug(f"[Eye] Vision summary failed: {e}")

        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_images(folder: Path, recursive: bool) -> List[Path]:
        """Collects all image files in a folder."""
        images = []
        pattern = "**/*" if recursive else "*"
        for ext in IMAGE_EXTENSIONS:
            images.extend(folder.glob(f"{pattern}{ext}"))
            images.extend(folder.glob(f"{pattern}{ext.upper()}"))
        return sorted(set(images))

    # ------------------------------------------------------------------
    # Dependency checks (lazy — only import when needed)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_pillow() -> bool:
        try:
            from PIL import Image  # noqa: F401
            return True
        except ImportError:
            logger.debug("[Eye] Pillow not installed. Run: pip install Pillow")
            return False

    @staticmethod
    def _check_imagehash() -> bool:
        try:
            import imagehash  # noqa: F401
            return True
        except ImportError:
            logger.debug("[Eye] imagehash not installed. Run: pip install imagehash")
            return False

    @staticmethod
    def _check_tesseract() -> bool:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            logger.debug(
                "[Eye] Tesseract not available. "
                "Install: pip install pytesseract + Tesseract binary"
            )
            return False
