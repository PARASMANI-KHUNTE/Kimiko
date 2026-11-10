"""Unit tests for the performance primitives and hot-path behavior changes.

These tests avoid external services (Postgres/Redis/Qdrant/Ollama) so they can
run in CI with only the base Python dependencies installed.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from kimiko.core.cache import AsyncSingleFlight, TTLCache
from kimiko.core.intent import IntentClassifier
from kimiko.core.retrieval_engine import RetrievalEngine
from kimiko.core.streaming import StreamingEngine
from kimiko.core.token_manager import TokenManager
from kimiko.models.schemas import Intent, Message, Role
from kimiko.services.embedding import EmbeddingService


# ── TTLCache ──


def test_ttl_cache_hit_and_miss():
    cache: TTLCache = TTLCache(maxsize=2, ttl=60)
    assert cache.get("a") is None
    cache.set("a", [1.0, 2.0])
    assert cache.get("a") == [1.0, 2.0]
    assert "a" in cache


def test_ttl_cache_expires():
    cache: TTLCache = TTLCache(maxsize=2, ttl=0.01)
    cache.set("a", 1)
    time.sleep(0.05)
    assert cache.get("a") is None
    assert len(cache) == 0


def test_ttl_cache_lru_eviction():
    cache: TTLCache = TTLCache(maxsize=2, ttl=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # mark "a" as recently used
    cache.set("c", 3)  # evicts "b"
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_ttl_cache_rejects_bad_config():
    with pytest.raises(ValueError):
        TTLCache(maxsize=0, ttl=10)
    with pytest.raises(ValueError):
        TTLCache(maxsize=10, ttl=0)


# ── AsyncSingleFlight ──


@pytest.mark.asyncio
async def test_single_flight_coalesces_concurrent_calls():
    flight: AsyncSingleFlight = AsyncSingleFlight()
    calls = 0

    async def factory() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return "value"

    results = await asyncio.gather(*(flight.run("k", factory) for _ in range(10)))
    assert results == ["value"] * 10
    assert calls == 1

    # A later call runs again (the in-flight entry was cleared).
    assert await flight.run("k", factory) == "value"
    assert calls == 2


@pytest.mark.asyncio
async def test_single_flight_separate_keys_run_independently():
    flight: AsyncSingleFlight = AsyncSingleFlight()
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        assigned = calls
        await asyncio.sleep(0.01)
        return assigned

    a, b = await asyncio.gather(flight.run("a", factory), flight.run("b", factory))
    assert {a, b} == {1, 2}
    assert calls == 2


# ── Embedding batch + cache ──


@pytest.mark.asyncio
async def test_embed_batch_deduplicates_and_caches(monkeypatch):
    service = EmbeddingService(base_url="http://localhost:11434")
    requested: list[list[str]] = []

    async def fake_request(inputs: list[str]) -> list[list[float]]:
        requested.append(list(inputs))
        return [[float(len(text))] for text in inputs]

    monkeypatch.setattr(service, "_request", fake_request)

    try:
        vectors = await service.embed_batch(["a", "bb", "a", "ccc"])
        # One upstream call, with only the unique misses.
        assert requested == [["a", "bb", "ccc"]]
        assert vectors == [[1.0], [2.0], [1.0], [3.0]]

        # Second call is fully served from cache; no new upstream request.
        again = await service.embed_batch(["ccc", "a"])
        assert requested == [["a", "bb", "ccc"]]
        assert again == [[3.0], [1.0]]
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_embed_single_uses_cache(monkeypatch):
    service = EmbeddingService(base_url="http://localhost:11434")
    calls = 0

    async def fake_request(inputs: list[str]) -> list[list[float]]:
        nonlocal calls
        calls += 1
        return [[42.0] for _ in inputs]

    monkeypatch.setattr(service, "_request", fake_request)

    try:
        assert await service.embed("hello") == [42.0]
        assert await service.embed("hello") == [42.0]
        assert calls == 1
    finally:
        await service.close()


# ── Token truncation ──


def test_truncate_messages_keeps_latest_and_order():
    manager = TokenManager()
    messages = [
        Message(role=Role.USER, content="x" * 400) for _ in range(50)
    ]
    # Each message ≈ 100 + 4 tokens; budget for ~5 messages.
    result = manager.truncate_messages(messages, max_tokens=600)
    assert result
    assert len(result) < len(messages)
    # Must keep the most recent message and preserve chronological order.
    assert result[-1] is messages[-1]
    indices = [messages.index(m) for m in result]
    assert indices == sorted(indices)


def test_truncate_messages_handles_empty():
    assert TokenManager().truncate_messages([], max_tokens=100) == []


def test_get_budget_exact_and_tagged():
    manager = TokenManager()
    assert manager.get_budget("qwen2.5") == manager.get_budget("qwen2.5:7b")
    assert manager.get_budget("totally-unknown")["context_window"] == 8192


# ── Intent ──


def test_intent_classifier_detects_code_fence():
    result = IntentClassifier().classify("Look:\n```python\nprint(1)\n```")
    assert result.intent == Intent.CODE
    assert result.confidence == 1.0


def test_intent_classifier_defaults_to_chat():
    result = IntentClassifier().classify("hmm interesting")
    assert result.intent == Intent.CHAT


# ── Streaming ──


@pytest.mark.asyncio
async def test_streaming_yields_valid_compact_json_frames():
    async def tokens():
        for token in ["Hel", "lo", " world"]:
            yield token

    engine = StreamingEngine()
    frames = [frame async for frame in engine.stream_response(tokens(), model="m")]

    assert all(isinstance(f, dict) and "data" in f for f in frames)
    # No pre-applied SSE framing: EventSourceResponse adds it.
    assert not any("data: " in f["data"] for f in frames)

    parsed = [json.loads(f["data"]) for f in frames]
    assert "".join(p["data"] for p in parsed if p["event"] == "token") == "Hello world"
    assert parsed[-1]["event"] == "done"
    assert parsed[-1]["metadata"]["total_tokens"] == 3


@pytest.mark.asyncio
async def test_streaming_stops_on_disconnect():
    async def tokens():
        for i in range(100):
            yield str(i)

    disconnect = asyncio.Event()
    disconnect.set()

    engine = StreamingEngine()
    frames = [
        frame
        async for frame in engine.stream_response(
            tokens(), model="m", check_disconnected=disconnect
        )
    ]
    # No token frames, only the terminal done frame.
    assert len(frames) == 1
    assert json.loads(frames[0]["data"])["event"] == "done"


# ── Retrieval conflict resolution ──


def test_conflict_resolution_prefers_newest():
    engine = RetrievalEngine(memory_manager=None)  # type: ignore[arg-type]

    ranked = [
        {
            "text": "My favorite programming language is Python",
            "final_score": 0.9,
            "metadata": {"timestamp": 100.0},
        },
        {
            "text": "Actually my favorite language is Rust now",
            "final_score": 0.5,
            "metadata": {"timestamp": 200.0},
        },
        {
            "text": "Unrelated memory",
            "final_score": 0.4,
            "metadata": {"timestamp": 50.0},
        },
    ]

    resolved = engine._resolve_conflicts(ranked)
    texts = {r["text"] for r in resolved}
    assert "Actually my favorite language is Rust now" in texts
    assert "My favorite programming language is Python" not in texts
    assert "Unrelated memory" in texts
    # The surviving member keeps the strongest score in its group.
    winner = next(
        r for r in resolved if r["text"].startswith("Actually")
    )
    assert winner["final_score"] == pytest.approx(0.9)
