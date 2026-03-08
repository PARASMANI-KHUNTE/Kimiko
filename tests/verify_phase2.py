"""Phase 2 Verification Script — Kimiko AI Tools & Agents."""

import asyncio
import os
import requests
import json

BASE_URL = "http://localhost:8000/v1"
API_KEY = "test-api-key"
HEADERS = {"X-API-Key": API_KEY}
USER_ID = "test-user-123"

def test_document_upload():
    print("\n--- Testing Document Upload ---")
    # Create a dummy markdown file
    with open("test_doc.md", "w") as f:
        f.write("# Kimiko Architecture\nKimiko uses LangGraph for agent reasoning and Qdrant for semantic memory.")
    
    with open("test_doc.md", "rb") as f:
        response = requests.post(
            f"{BASE_URL}/documents/upload",
            headers=HEADERS,
            files={"file": f},
            data={"user_id": USER_ID, "tags": "verify,test"}
        )
    
    os.remove("test_doc.md")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 201 or response.status_code == 200

def test_agent_calculator():
    print("\n--- Testing Agent (Calculator) ---")
    goal = "What is 125 * 8 + 45?"
    response = requests.post(
        f"{BASE_URL}/agent/run",
        headers=HEADERS,
        json={
            "goal": goal,
            "user_id": USER_ID,
            "max_steps": 3
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Answer: {response.json().get('answer')}")
    return response.status_code == 200

def test_agent_search():
    print("\n--- Testing Agent (Web Search) ---")
    goal = "Who is the current Prime Minister of India?"
    response = requests.post(
        f"{BASE_URL}/agent/run",
        headers=HEADERS,
        json={
            "goal": goal,
            "user_id": USER_ID,
            "max_steps": 3
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Answer: {response.json().get('answer')}")
    return response.status_code == 200

if __name__ == "__main__":
    # Ensure server is running before this
    try:
        if test_document_upload():
            print("Document Upload: PASS")
        if test_agent_calculator():
            print("Agent Calculator: PASS")
        if test_agent_search():
            print("Agent Search: PASS")
    except Exception as e:
        print(f"Verification FAILED: {str(e)}")
