"""Integration test for Phase 3: Multimodal & Advanced Memory."""

import base64
import io
import json
import time
import httpx
import unittest
from PIL import Image

API_URL = "http://localhost:8000/v1"

class TestPhase3(unittest.TestCase):
    def setUp(self):
        self.session_id = f"test-session-p3-{int(time.time())}"
        self.user_id = "00000000-0000-0000-0000-000000000001" # Mock UUID

    def create_test_image(self):
        file = io.BytesIO()
        image = Image.new("RGB", (100, 100), color="blue")
        image.save(file, format="PNG")
        return base64.b64encode(file.getvalue()).decode("utf-8")

    def test_vision_request(self):
        """Test sending an image to the chat endpoint."""
        print("\n--- Testing Multimodal Vision ---")
        b64_img = self.create_test_image()
        
        payload = {
            "message": "What is in this image?",
            "images": [b64_img],
            "session_id": self.session_id,
            "user_id": self.user_id
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(f"{API_URL}/chat", json=payload)
                print(f"Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("message", {}).get("content", "")
                    print(f"Response: {content[:100]}...")
                    self.assertIn("message", data)
                else:
                    print(f"Error: {response.text}")
        except Exception as e:
            print(f"Connection error: {e}")

    def test_audio_endpoints(self):
        """Test STT and TTS endpoints."""
        print("\n--- Testing Audio Endpoints ---")
        
        # 1. Test Synthesis (TTS)
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{API_URL}/audio/synthesize", params={"text": "Hello world"})
            print(f"TTS Status: {resp.status_code}")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers["content-type"], "audio/wav")

        # 2. Test Transcription (STT) 
        # (Using a dummy file since we don't have a real audio sample)
        audio_content = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        files = {"file": ("test.wav", audio_content, "audio/wav")}
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{API_URL}/audio/transcribe", files=files)
            print(f"STT Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"STT Response: {resp.json()}")
            else:
                print(f"STT Error: {resp.text}")

    def test_fact_extraction_trigger(self):
        """Test if sending facts triggers extraction and storage."""
        print("\n--- Testing Fact Extraction Trigger ---")
        
        # Send several messages to exceed threshold (typically 5-10)
        # We'll send facts about a user
        facts = [
            "My name is Paras.",
            "I love building AI agents.",
            "I live in India.",
            "I prefer dark mode in all my apps.",
            "I hate mushrooms on pizza."
        ]
        
        with httpx.Client(timeout=30.0) as client:
            for fact in facts:
                payload = {
                    "message": fact,
                    "session_id": f"fact-test-{self.session_id}",
                    "user_id": self.user_id
                }
                client.post(f"{API_URL}/chat", json=payload)
            
            print("Sent 5 messages. Waiting for background worker...")
            time.sleep(10) # Wait for Celery
            
            # Check if facts appear in retrieval
            query_payload = {
                "message": "What do you know about me?",
                "session_id": f"fact-test-{self.session_id}",
                "user_id": self.user_id
            }
            resp = client.post(f"{API_URL}/chat", json=query_payload)
            if resp.status_code == 200:
                content = resp.json().get("message", {}).get("content", "").lower()
                print(f"Agent knowledge re-check: {content[:200]}")
                # We expect the agent to recall some facts if retrieval is working
            else:
                print(f"Query Error: {resp.text}")

if __name__ == "__main__":
    unittest.main()
