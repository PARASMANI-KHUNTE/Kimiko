"""Multi-User Isolation Test — verifies no cross-contamination of memory, facts, or conversations."""

import unittest
import os
import httpx


API_URL = os.getenv("API_URL", "http://localhost:8000/v1")
HEADERS = {"X-API-Key": "test-key-123"}

# Use valid UUIDs for user IDs
USER_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class TestMultiUserIsolation(unittest.TestCase):
    """Ensures user A's memory and facts never bleed into user B's context."""

    def test_user_memory_isolation(self):
        """User A and User B should never see each other's memories."""
        print("\n--- Testing Multi-User Memory Isolation ---")

        with httpx.Client(timeout=120.0, headers=HEADERS) as client:
            # 1. User A sends a personal message
            user_a_msg = {
                "model": "qwen2.5",
                "message": "My name is Alice and my favorite color is blue.",
                "session_id": "session-user-a",
                "user_id": USER_A_ID,
            }
            resp_a = client.post(f"{API_URL}/chat", json=user_a_msg)
            print(f"User A chat status: {resp_a.status_code}")
            self.assertEqual(resp_a.status_code, 200)

            # 2. User B sends a personal message
            user_b_msg = {
                "model": "qwen2.5",
                "message": "My name is Bob and my favorite color is red.",
                "session_id": "session-user-b",
                "user_id": USER_B_ID,
            }
            resp_b = client.post(f"{API_URL}/chat", json=user_b_msg)
            print(f"User B chat status: {resp_b.status_code}")
            self.assertEqual(resp_b.status_code, 200)

            # 3. User B asks about favorite colors — should NOT mention Alice or blue
            user_b_recall = {
                "model": "qwen2.5",
                "message": "What is my favorite color?",
                "session_id": "session-user-b",
                "user_id": USER_B_ID,
            }
            resp_recall = client.post(f"{API_URL}/chat", json=user_b_recall)
            print(f"User B recall status: {resp_recall.status_code}")
            self.assertEqual(resp_recall.status_code, 200)

            if resp_recall.status_code == 200:
                data = resp_recall.json()
                answer = data.get("response", {}).get("content", "").lower()
                print(f"User B recall answer: {answer}")

                # Critical assertion: User B should NOT see User A's data
                self.assertNotIn("alice", answer, 
                    "CROSS-USER LEAK DETECTED: User B's response contains User A's name!")


if __name__ == "__main__":
    unittest.main()
