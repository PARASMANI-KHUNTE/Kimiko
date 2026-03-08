"""Pydantic schemas for API request/response — versioned (v1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── Enums ──


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Intent(str, Enum):
    CHAT = "chat"
    CODE = "code"
    QUESTION = "question"
    GREETING = "greeting"
    IMAGE_ANALYSIS = "image_analysis"
    SPEECH = "speech"
    AGENT_TASK = "agent_task"
    TOOL_REQUEST = "tool_request"
    DOCUMENT_QUERY = "document_query"


class StreamEventType(str, Enum):
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"
    METADATA = "metadata"


# ── Chat ──


class Message(BaseModel):
    role: Role
    content: str
    timestamp: datetime | None = None


class ChatRequest(BaseModel):
    messages: list[Message] = Field(..., min_length=1)
    model: str | None = None
    stream: bool = False
    session_id: str | None = None
    user_id: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = None


class ChatResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: Message
    model: str
    intent: str | None = None
    usage: TokenUsage | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class StreamEvent(BaseModel):
    event: StreamEventType
    data: str
    metadata: dict | None = None


# ── Memory ──


class MemoryCreate(BaseModel):
    user_id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    memory_type: str = "general"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    text: str
    tags: list[str]
    memory_type: str
    importance: float
    created_at: datetime

    model_config = {"from_attributes": True}


class MemorySearchRequest(BaseModel):
    user_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


# ── Models ──


class ModelInfo(BaseModel):
    name: str
    size: str | None = None
    modified_at: str | None = None
    details: dict | None = None


class ModelListResponse(BaseModel):
    models: list[ModelInfo]


# ── Intent ──


class IntentResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)


# ── Retrieval ──


class RetrievalResult(BaseModel):
    text: str
    score: float
    source: str  # "semantic", "long_term", "short_term"
    metadata: dict = Field(default_factory=dict)


# ── Health ──


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    services: dict[str, str] = Field(default_factory=dict)
