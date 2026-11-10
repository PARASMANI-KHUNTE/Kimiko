"""Kimiko Screen Context Engine.

Handles:
  - OCR (Text extraction) using pytesseract
  - UI Tree access using uiautomation (Windows)
  - Region detection using OpenCV
"""

import os
import json
import logging
import cv2
import numpy as np
import pytesseract
import uiautomation as auto
from PIL import Image
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Tesseract path configuration (User might need to adjust this)
# Typical Windows path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
TESSERACT_PATH = os.getenv("KIMIKO_TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

class ScreenContextEngine:
    """Extracts semantic information from the current screen."""

    @staticmethod
    def extract_text(image_path: str) -> str:
        """Extract all text from an image file using OCR."""
        try:
            img = Image.open(image_path)
            return ScreenContextEngine.extract_text_pil(img)
        except Exception as e:
            logger.error(f"OCR File Error: {e}")
            return f"[Error in OCR File: {str(e)}]"

    @staticmethod
    def extract_text_pil(img: Image.Image) -> str:
        """Extract all text from a PIL Image using OCR."""
        try:
            if not os.path.exists(TESSERACT_PATH):
                return "[Error: Tesseract-OCR not found.]"
            
            # Pre-processing
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            text = pytesseract.image_to_string(gray)
            return text.strip()
        except Exception as e:
            logger.error(f"OCR PIL Error: {e}")
            return f"[Error in OCR PIL: {str(e)}]"

    @staticmethod
    def get_ui_elements() -> List[Dict[str, Any]]:
        """Extract visible UI elements using Windows uiautomation."""
        elements = []
        try:
            # Get the focused/active window
            active_window = auto.GetForegroundControl()
            if not active_window:
                return []

            # Traverse child elements (depth=2 for performance)
            def traverse(control, depth=0):
                if depth > 2: return
                
                # Filter for useful elements: Buttons, Edits, ListItems, MenuItem
                control_type = control.ControlTypeName
                if control_type in ["ButtonControl", "EditControl", "ListItemControl", "MenuItemControl", "TextControl"]:
                    rect = control.BoundingRectangle
                    elements.append({
                        "name": control.Name,
                        "type": control_type,
                        "rect": [rect.left, rect.top, rect.right, rect.bottom]
                    })
                
                for child in control.GetChildren():
                    traverse(child, depth + 1)

            traverse(active_window)
        except Exception as e:
            logger.error(f"UI Automation Error: {e}")
        
        return elements[:50] # Limit for token budget

    @staticmethod
    def get_full_context(screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """Combine all context sources into a single dictionary."""
        context = {
            "active_app": "Unknown",
            "visible_text": "",
            "ui_elements": [],
        }

        try:
            # 1. Active App
            active_window = auto.GetForegroundControl()
            if active_window:
                context["active_app"] = active_window.Name

            # 2. UI Elements
            context["ui_elements"] = ScreenContextEngine.get_ui_elements()

            # 3. OCR (if screenshot provided)
            if screenshot_path and os.path.exists(screenshot_path):
                context["visible_text"] = ScreenContextEngine.extract_text(screenshot_path)

        except Exception as e:
            logger.error(f"Screen context extraction failed: {e}")

        return context

if __name__ == "__main__":
    # Quick test
    print("Testing Screen Context Engine...")
    ctx = ScreenContextEngine.get_full_context()
    print(json.dumps(ctx, indent=2))
