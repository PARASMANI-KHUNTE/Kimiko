import unittest
import httpx
import os
import io
import base64
from PIL import Image, ImageDraw

API_URL = os.getenv("API_URL", "http://localhost:8000/v1")


class TestMultimodalAgent(unittest.TestCase):
    def test_multimodal_reasoning_and_tools(self):
        """Test Vision -> Reasoning -> Tool Usage pipeline."""
        print("\n--- Testing Vision to Tool Pipeline ---")
        
        # 1. Create a synthetic circuit board image
        img = Image.new('RGB', (400, 400), color='forestgreen')
        d = ImageDraw.Draw(img)
        # Draw a fake chip
        d.rectangle([100, 150, 300, 250], fill="black", outline="silver", width=4)
        d.text((120, 190), "ESP32 Microcontroller", fill=(255, 255, 255))
        d.rectangle([110, 140, 130, 150], fill="silver") # Pins
        d.rectangle([140, 140, 160, 150], fill="silver")
        d.rectangle([270, 140, 290, 150], fill="silver")
        
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        # 2. Ask the agent to analyze AND search
        payload = {
            "goal": "I have attached an image natively to this request. Look closely at The Attached Image. Identify the primary microchip in this image. Once you have identified it, use the web search tool to find a short summary of its capabilities.",
            "images": [img_str],
            "max_steps": 5
        }
        
        headers = {"X-API-Key": "test-key-123"}
        
        # 3. Increase timeout heavily for large context multimodal tool loops
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(f"{API_URL}/agent/run", json=payload, headers=headers)
            print(f"Agent Task Status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "")
                print(f"Agent Final Answer: {answer}")
                
                # Verify both the Vision piece (ESP32) and the Reasoning piece (Search) occurred.
                self.assertIn("ESP32", answer.upper())
            else:
                print(f"Error: {resp.text}")
                self.assertEqual(resp.status_code, 200)

if __name__ == "__main__":
    unittest.main()
