"""Test fixtures and shared configuration."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_chat_request():
    """Sample chat request for testing."""
    return {
        "messages": [{"role": "user", "content": "Hello, Kimiko!"}],
        "model": None,
        "stream": False,
        "session_id": "test-session-001",
        "user_id": "test-user-001",
        "temperature": 0.7,
    }


@pytest.fixture
def sample_memory_request():
    """Sample memory creation request."""
    return {
        "user_id": "test-user-001",
        "text": "Paras loves building robots",
        "tags": ["interest", "robotics"],
        "memory_type": "interest",
        "importance": 0.8,
    }
