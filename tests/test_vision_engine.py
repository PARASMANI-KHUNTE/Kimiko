"""Unit tests for VisionEngine."""

import base64
import io
import unittest
from PIL import Image
from kimiko.services.vision_engine import VisionEngine

class TestVisionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = VisionEngine(max_image_size=(100, 100))

    def create_test_image(self, size=(200, 200), format="PNG"):
        file = io.BytesIO()
        image = Image.new("RGB", size, color="red")
        image.save(file, format=format)
        return base64.b64encode(file.getvalue()).decode("utf-8")

    def test_resize_large_image(self):
        # Create a 200x200 image
        b64_img = self.create_test_image(size=(200, 200))
        
        # Process it (max size is 100x100)
        processed_b64 = self.engine.validate_and_preprocess(b64_img)
        
        # Decode and check size
        img_data = base64.b64decode(processed_b64)
        img = Image.open(io.BytesIO(img_data))
        
        self.assertLessEqual(img.width, 100)
        self.assertLessEqual(img.height, 100)
        self.assertEqual(img.format, "JPEG") # Should be converted to JPEG by default

    def test_invalid_image(self):
        with self.assertRaises(ValueError):
            self.engine.validate_and_preprocess("not-a-base64-image")

    def test_vision_payload_detection(self):
        self.assertTrue(self.engine.is_vision_payload(["some-data"]))
        self.assertFalse(self.engine.is_vision_payload([]))
        self.assertFalse(self.engine.is_vision_payload(None))

if __name__ == "__main__":
    unittest.main()
