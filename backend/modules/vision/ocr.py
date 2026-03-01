"""
Leomail Vision - OCR wrapper using Tesseract.
Extracts all text + bounding boxes from a screenshot.
Falls back to basic pattern matching if Tesseract is not installed.
"""
import re
from pathlib import Path
from loguru import logger

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.warning("[Vision] pytesseract/Pillow not installed - OCR disabled")

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


# Try to find Tesseract binary on Windows
import shutil
_tess = shutil.which("tesseract")
if not _tess:
    # Common Windows install paths
    for p in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Tesseract-OCR\tesseract.exe",
    ]:
        if Path(p).exists():
            _tess = p
            break
if _tess and HAS_TESSERACT:
    pytesseract.pytesseract.tesseract_cmd = _tess
    logger.info(f"[Vision] Tesseract found: {_tess}")
elif HAS_TESSERACT:
    logger.warning("[Vision] Tesseract binary not found - OCR will fail. Install: choco install tesseract")


class OCR:
    """Extract text and positions from screenshots."""

    @staticmethod
    def extract_all_text(image_path: str | Path) -> str:
        """Get all text from image as one string."""
        if not HAS_TESSERACT:
            return ""
        try:
            img = Image.open(str(image_path))
            text = pytesseract.image_to_string(img, lang="eng")
            return text.strip()
        except Exception as e:
            logger.error(f"[OCR] Failed to extract text: {e}")
            return ""

    @staticmethod
    def extract_text_with_boxes(image_path: str | Path) -> list[dict]:
        """
        Get text with bounding boxes.
        Returns: [{"text": "Next", "x": 100, "y": 200, "w": 80, "h": 30, "conf": 95}, ...]
        """
        if not HAS_TESSERACT:
            return []
        try:
            img = Image.open(str(image_path))
            data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
            results = []
            n = len(data["text"])
            for i in range(n):
                text = data["text"][i].strip()
                conf = int(data["conf"][i])
                if text and conf > 30:  # filter noise
                    results.append({
                        "text": text,
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "w": data["width"][i],
                        "h": data["height"][i],
                        "conf": conf,
                    })
            return results
        except Exception as e:
            logger.error(f"[OCR] Failed to extract boxes: {e}")
            return []

    @staticmethod
    def extract_from_bytes(img_bytes: bytes) -> str:
        """Extract text from raw image bytes (from Playwright screenshot)."""
        if not HAS_TESSERACT:
            return ""
        try:
            import io
            img = Image.open(io.BytesIO(img_bytes))
            return pytesseract.image_to_string(img, lang="eng").strip()
        except Exception as e:
            logger.error(f"[OCR] Failed bytes extraction: {e}")
            return ""

    @staticmethod
    def extract_boxes_from_bytes(img_bytes: bytes) -> list[dict]:
        """Extract text + boxes from raw image bytes."""
        if not HAS_TESSERACT:
            return []
        try:
            import io
            img = Image.open(io.BytesIO(img_bytes))
            data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
            results = []
            n = len(data["text"])
            for i in range(n):
                text = data["text"][i].strip()
                conf = int(data["conf"][i])
                if text and conf > 30:
                    results.append({
                        "text": text,
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "w": data["width"][i],
                        "h": data["height"][i],
                        "conf": conf,
                    })
            return results
        except Exception as e:
            logger.error(f"[OCR] Failed bytes box extraction: {e}")
            return []

    @staticmethod
    def find_text_location(img_bytes: bytes, target: str, case_insensitive: bool = True) -> dict | None:
        """
        Find a specific text on the screen and return its center coordinates.
        Returns: {"x": center_x, "y": center_y, "w": w, "h": h} or None
        """
        boxes = OCR.extract_boxes_from_bytes(img_bytes)
        target_lower = target.lower() if case_insensitive else target

        # Try exact match first
        for box in boxes:
            t = box["text"].lower() if case_insensitive else box["text"]
            if target_lower == t:
                return {
                    "x": box["x"] + box["w"] // 2,
                    "y": box["y"] + box["h"] // 2,
                    "w": box["w"],
                    "h": box["h"],
                }

        # Try partial match (multi-word)
        full_text = " ".join(b["text"] for b in boxes)
        if case_insensitive:
            full_text_lower = full_text.lower()
        else:
            full_text_lower = full_text

        if target_lower in full_text_lower:
            # Find the first word of target in boxes
            first_word = target.split()[0]
            for box in boxes:
                t = box["text"].lower() if case_insensitive else box["text"]
                if first_word.lower() == t if case_insensitive else first_word == t:
                    return {
                        "x": box["x"] + box["w"] // 2,
                        "y": box["y"] + box["h"] // 2,
                        "w": box["w"],
                        "h": box["h"],
                    }

        return None
