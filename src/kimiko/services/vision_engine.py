"""Vision engine — image preprocessing and vision model routing."""

from __future__ import annotations

import base64
import io
from typing import Any, Dict, List, Optional

import structlog
from PIL import Image

logger = structlog.get_logger(__name__)


class VisionEngine:
    """Handles image validation, resizing, and vision model selection."""

    def __init__(
        self,
        max_image_size: tuple[int, int] = (1024, 1024),
        default_vision_model: str = "qwen2-vl",
    ) -> None:
        self.max_image_size = max_image_size
        self.default_vision_model = default_vision_model

    def validate_and_preprocess(self, base64_image: str) -> str:
        """Validate base64 image and resize if it exceeds max dimensions.
        
        Returns the processed image as a base64 string.
        """
        try:
            # 1. Decode
            img_data = base64.b64decode(base64_image)
            img = Image.open(io.BytesIO(img_data))
            
            # 2. Check format
            if img.format not in ["JPEG", "PNG", "WEBP"]:
                # Attempt to convert to RGB/JPEG
                img = img.convert("RGB")
            
            # 3. Resize if necessary
            if img.width > self.max_image_size[0] or img.height > self.max_image_size[1]:
                img.thumbnail(self.max_image_size, Image.Resampling.LANCZOS)
                logger.debug("image_resized", original_size=(img.width, img.height))

            # 4. Encode back to base64
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")

        except Exception as e:
            logger.error("image_preprocessing_failed", error=str(e))
            raise ValueError(f"Invalid image data: {str(e)}")

    def get_vision_model(self, requested_model: str | None = None) -> str:
        """Determine the best vision model to use."""
        # For now, we always route to the default vision model if images are present
        return requested_model or self.default_vision_model

    def is_vision_payload(self, images: list[str] | None) -> bool:
        """Check if the payload requires vision capabilities."""
        return bool(images and len(images) > 0)
