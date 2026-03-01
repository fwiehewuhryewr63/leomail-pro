"""
Leomail Vision Engine — main orchestrator.
Takes Playwright page → screenshot → OCR → stage detection → element finding.
Integrates with birth engine to replace fragile CSS selectors.
"""
import asyncio
import os
import time
from pathlib import Path
from loguru import logger

from .ocr import OCR
from .stage_detector import StageDetector


class VisionEngine:
    """
    Visual recognition engine for automated email registration.
    
    Usage in birth engine:
        vision = VisionEngine("yahoo")
        
        # Take screenshot and detect stage
        result = await vision.analyze(page)
        # result = {"stage": "signup_form", "confidence": 0.85, ...}
        
        # Find and click a button
        await vision.click_text(page, "Next")
        
        # Find and fill an input by its label
        await vision.fill_near_label(page, "First name", "John")
    """

    def __init__(self, provider: str = "yahoo", debug: bool = False):
        self.provider = provider.lower()
        self.detector = StageDetector(provider)
        self.debug = debug
        self.debug_dir = Path("user_data/vision_debug")
        if debug:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
        self._last_screenshot = None
        self._last_result = None

    async def screenshot(self, page) -> bytes:
        """Take a full-page screenshot and return as bytes."""
        try:
            img_bytes = await page.screenshot(full_page=False, type="png")
            self._last_screenshot = img_bytes

            if self.debug:
                ts = int(time.time() * 1000)
                debug_path = self.debug_dir / f"{self.provider}_{ts}.png"
                debug_path.write_bytes(img_bytes)

            return img_bytes
        except Exception as e:
            logger.error(f"[Vision] Screenshot failed: {e}")
            return b""

    async def analyze(self, page) -> dict:
        """
        Take screenshot and detect current stage.
        
        Returns: {
            "stage": "signup_form",
            "confidence": 0.85,
            "description": "Main signup form",
            "all_text": "...",
            "matched_keywords": [...],
            "text_boxes": [...]
        }
        """
        img_bytes = await self.screenshot(page)
        if not img_bytes:
            return {"stage": "unknown", "confidence": 0, "description": "Screenshot failed"}

        result = self.detector.detect_from_bytes(img_bytes)
        self._last_result = result

        if self.debug:
            logger.debug(f"[Vision] Stage: {result['stage']} ({result['confidence']:.0%}) — {result['description']}")
            if result['matched_keywords']:
                logger.debug(f"[Vision] Matched: {result['matched_keywords']}")

        return result

    async def click_text(self, page, text: str, timeout: float = 2.0) -> bool:
        """
        Find text on screen via OCR and click its center.
        Fallback: tries page.get_by_text() if OCR fails.
        
        Returns True if clicked successfully.
        """
        img_bytes = await self.screenshot(page)
        if not img_bytes:
            return False

        loc = OCR.find_text_location(img_bytes, text)
        if loc:
            logger.info(f"[Vision] 🎯 OCR found '{text}' at ({loc['x']}, {loc['y']})")
            await page.mouse.click(loc["x"], loc["y"])
            await asyncio.sleep(0.3)
            return True

        # Fallback to Playwright selector
        logger.debug(f"[Vision] OCR miss for '{text}', trying Playwright fallback")
        try:
            el = page.get_by_text(text, exact=False)
            if await el.count() > 0:
                await el.first.click(timeout=timeout * 1000)
                logger.info(f"[Vision] [OK] Playwright fallback clicked '{text}'")
                return True
        except Exception:
            pass

        logger.warning(f"[Vision] [FAIL] Could not find '{text}' on screen")
        return False

    async def click_button(self, page, button_texts: list[str], timeout: float = 2.0) -> bool:
        """
        Try clicking a button by trying multiple possible texts.
        Example: click_button(page, ["Next", "Continue", "Next"])
        """
        for text in button_texts:
            if await self.click_text(page, text, timeout):
                return True
        return False

    async def fill_near_label(self, page, label: str, value: str, offset_y: int = 40) -> bool:
        """
        Find a label text, then click below it (where input likely is) and type.
        Fallback: tries page.get_by_label().
        
        Returns True if filled successfully.
        """
        img_bytes = await self.screenshot(page)
        if not img_bytes:
            return False

        loc = self.detector.find_input_near_label(img_bytes, label, offset_y)
        if loc:
            logger.info(f"[Vision] 🎯 Found label '{label}' — clicking input at ({loc['x']}, {loc['y']})")
            await page.mouse.click(loc["x"], loc["y"])
            await asyncio.sleep(0.2)
            await page.keyboard.type(value, delay=30 + __import__("random").randint(10, 80))
            return True

        # Fallback to Playwright
        logger.debug(f"[Vision] OCR miss for label '{label}', trying Playwright fallback")
        try:
            el = page.get_by_label(label, exact=False)
            if await el.count() > 0:
                await el.first.fill(value)
                logger.info(f"[Vision] [OK] Playwright fallback filled '{label}'")
                return True
        except Exception:
            pass

        logger.warning(f"[Vision] [FAIL] Could not fill '{label}'")
        return False

    async def fill_by_placeholder(self, page, placeholder: str, value: str) -> bool:
        """Fill input found by its placeholder text (via OCR or Playwright)."""
        # Try OCR first
        img_bytes = await self.screenshot(page)
        if img_bytes:
            loc = OCR.find_text_location(img_bytes, placeholder)
            if loc:
                await page.mouse.click(loc["x"], loc["y"])
                await asyncio.sleep(0.15)
                # Select all existing text and replace
                await page.keyboard.press("Control+a")
                await page.keyboard.type(value, delay=30 + __import__("random").randint(10, 80))
                return True

        # Fallback
        try:
            el = page.get_by_placeholder(placeholder, exact=False)
            if await el.count() > 0:
                await el.first.fill(value)
                return True
        except Exception:
            pass

        return False

    async def is_error(self, page) -> dict | None:
        """
        Quick check: is current screen an error?
        Returns: {"type": "blocked"|"phone"|"username", "text": "..."} or None
        """
        img_bytes = await self.screenshot(page)
        if not img_bytes:
            return None
        return self.detector.is_error(img_bytes)

    async def wait_for_stage(
        self, page, target_stages: list[str],
        timeout: float = 30.0, poll: float = 2.0
    ) -> dict | None:
        """
        Wait until one of the target stages is detected.
        Returns the stage result dict, or None on timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            result = await self.analyze(page)
            if result["stage"] in target_stages:
                return result
            if result["stage"].startswith("error_"):
                return result  # Return errors immediately
            await asyncio.sleep(poll)
        return None

    async def has_text(self, page, text: str) -> bool:
        """Check if specific text exists on the current screen."""
        img_bytes = await self.screenshot(page)
        if not img_bytes:
            return False
        all_text = OCR.extract_from_bytes(img_bytes)
        return text.lower() in all_text.lower()

    async def get_all_text(self, page) -> str:
        """Get all text from current screen."""
        img_bytes = await self.screenshot(page)
        if not img_bytes:
            return ""
        return OCR.extract_from_bytes(img_bytes)

    async def smart_click(self, page, css_selector: str, ocr_text: str = None) -> bool:
        """
        Smart click — tries OCR first (if text given), falls back to CSS.
        This is the primary replacement for page.click(selector).
        
        Usage:
            # Before:  await page.click("#next-btn")
            # After:   await vision.smart_click(page, "#next-btn", "Next")
        """
        # Try OCR first
        if ocr_text:
            success = await self.click_text(page, ocr_text, timeout=1.5)
            if success:
                return True

        # Fallback to CSS selector
        try:
            await page.click(css_selector, timeout=3000)
            logger.info(f"[Vision] [OK] CSS fallback clicked '{css_selector}'")
            return True
        except Exception:
            logger.warning(f"[Vision] [FAIL] Both OCR('{ocr_text}') and CSS('{css_selector}') failed")
            return False

    async def smart_fill(self, page, css_selector: str, value: str, ocr_label: str = None) -> bool:
        """
        Smart fill — tries OCR label first, falls back to CSS. 
        This is the primary replacement for page.fill(selector, value).
        
        Usage:
            # Before:  await page.fill("#first-name", "Jessica")
            # After:   await vision.smart_fill(page, "#first-name", "Jessica", "First name")
        """
        # Try OCR first
        if ocr_label:
            success = await self.fill_near_label(page, ocr_label, value)
            if success:
                return True

        # Fallback to CSS
        try:
            await page.fill(css_selector, value, timeout=3000)
            logger.info(f"[Vision] [OK] CSS fallback filled '{css_selector}'")
            return True
        except Exception:
            logger.warning(f"[Vision] [FAIL] Both OCR('{ocr_label}') and CSS('{css_selector}') failed")
            return False
