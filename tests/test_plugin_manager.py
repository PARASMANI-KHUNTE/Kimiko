import unittest
import os
import httpx
from unittest.mock import patch, MagicMock

API_URL = os.getenv("API_URL", "http://localhost:8000/v1")

class TestPluginManager(unittest.TestCase):
    def test_plugin_loads_and_registers(self):
        """Test that the weather plugin correctly loads and exposes its namespace tool."""
        print("\n--- Testing Plugin Manager ---")
        
        # 1. Ask the agent a question that explicitly triggers the weather plugin
        payload = {
            "goal": "What is the current weather in Tokyo, Japan?",
            "max_steps": 5
        }
        
        headers = {"X-API-Key": "test-key-123"}
        
        with httpx.Client(timeout=100.0) as client:
            resp = client.post(f"{API_URL}/agent/run", json=payload, headers=headers)
            print(f"Agent Task Status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "")
                print(f"Agent Final Answer: {answer}")
                
                # Verify the agent used the weather plugin's mocked tool output
                # The mocked output for Tokyo is "72°F (22°C), partly cloudy."
                self.assertTrue("72" in answer or "partly cloudy" in answer.lower(), 
                               "The agent failed to trigger or parse the weather.get_current plugin tool.")
            else:
                print(f"Error: {resp.text}")
                self.assertEqual(resp.status_code, 200)

if __name__ == "__main__":
    unittest.main()
