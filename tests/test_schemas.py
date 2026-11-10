"""Tests for Pydantic schemas and configuration."""

from __future__ import annotations

from kimiko.config import Settings
from kimiko.models.schemas import (
    ChatRequest,
    Intent,
    IntentResult,
    MemoryCreate,
    Message,
    Role,
    StreamEvent,
    StreamEventType,
)


class TestSchemas:
    """Tests for Pydantic request/response schemas."""

    def test_message_creation(self):
        msg = Message(role=Role.USER, content="Hello")
        assert msg.role == Role.USER
        assert msg.content == "Hello"

    def test_chat_request_validation(self):
        req = ChatRequest(
            messages=[Message(role=Role.USER, content="Hi")],
            temperature=0.5,
        )
        assert len(req.messages) == 1
        assert req.stream is False
        assert req.temperature == 0.5

    def test_chat_request_requires_messages(self):
        import pytest
        with pytest.raises(Exception):
            ChatRequest(messages=[])

    def test_memory_create(self):
        mem = MemoryCreate(
            user_id="user-1",
            text="Likes robotics",
            tags=["interest"],
            importance=0.8,
        )
        assert mem.importance == 0.8
        assert "interest" in mem.tags

    def test_intent_result(self):
        result = IntentResult(intent=Intent.CODE, confidence=0.85)
        assert result.intent == Intent.CODE

    def test_stream_event(self):
        event = StreamEvent(
            event=StreamEventType.TOKEN,
            data="Hello",
        )
        json_str = event.model_dump_json()
        assert "token" in json_str
        assert "Hello" in json_str


class TestConfig:
    """Tests for configuration loading."""

    def test_default_settings(self):
        settings = Settings()
        assert settings.api_port == 8000
        assert settings.default_model == "qwen3.5:4b"
        assert settings.embedding_model == "embeddinggemma-2:270m"
        assert settings.vector_size == 768

    def test_development_check(self):
        settings = Settings(env="development")
        assert settings.is_development is True
        assert settings.is_production is False
