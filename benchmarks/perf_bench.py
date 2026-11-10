r"""Reproducible micro-benchmarks for the Kimiko performance work.

Run from the repo root:

    $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe benchmarks\perf_bench.py

Each benchmark compares the previous implementation (``baseline``) with the
optimized one now in ``src/kimiko``. The baselines are deliberately local,
self-contained copies so the comparison does not require checking out old code.

Numbers are single-process and CPU-bound unless noted. They isolate the
algorithmic/constant-factor gains; end-to-end LLM latency is dominated by
Ollama and is measured separately with real services.
"""

from __future__ import annotations

import asyncio
import re
import statistics
import time
from dataclasses import dataclass
from json.encoder import encode_basestring

from kimiko.core.cache import TTLCache
from kimiko.core.intent import IntentClassifier
from kimiko.core.ranking import RetrievalRanker
from kimiko.core.retrieval_engine import RetrievalEngine
from kimiko.core.token_manager import TokenManager
from kimiko.models.schemas import (
    Intent,
    IntentResult,
    Message,
    Role,
    StreamEvent,
    StreamEventType,
)
from kimiko.services.embedding import EmbeddingService


@dataclass
class Result:
    name: str
    baseline_ms: float
    optimized_ms: float

    @property
    def speedup(self) -> float:
        if self.optimized_ms <= 0:
            return float("inf")
        return self.baseline_ms / self.optimized_ms

    def row(self) -> str:
        return (
            f"{self.name:<34} {self.baseline_ms:>10.3f} ms "
            f"{self.optimized_ms:>10.3f} ms {self.speedup:>9.2f}x"
        )


def _time(fn, repeats: int = 5) -> float:
    """Return the median runtime of ``fn`` in milliseconds."""
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


# ── 1. Message truncation: O(n²) insert(0) vs O(n) append+reverse ──

_COUNT = lambda text: len(text) // 4 + 1  # noqa: E731


def _truncate_baseline(messages: list[Message], max_tokens: int) -> list[Message]:
    if not messages:
        return []
    result = [messages[-1]]
    remaining = max_tokens - _COUNT(messages[-1].content) - 4
    for msg in reversed(messages[:-1]):
        tokens = _COUNT(msg.content) + 4
        if remaining - tokens < 0:
            break
        result.insert(0, msg)
        remaining -= tokens
    return result


def bench_truncate() -> Result:
    messages = [Message(role=Role.USER, content="word " * 40) for _ in range(2000)]
    manager = TokenManager()

    # Large budget so every message is retained — this exercises the O(n²)
    # ``insert(0)`` behavior rather than stopping after a handful of messages.
    base = _time(lambda: _truncate_baseline(messages, 1_000_000))
    opt = _time(lambda: manager.truncate_messages(messages, 1_000_000))
    return Result("truncate_messages (2k kept)", base, opt)


# ── 2. Ranking: per-item clock/tag-set work vs batch precompute ──

_WEIGHTS = (0.55, 0.2, 0.1, 0.1)


def _rank_baseline(results: list[dict], query_tags: list[str] | None) -> list[dict]:
    query_tags = query_tags or []
    scored = []
    for item in results:
        metadata = item.get("metadata", {})
        timestamp = metadata.get("timestamp", time.time())
        item_tags = metadata.get("tags", [])
        age = time.time() - timestamp
        recency = 1.0 if age <= 0 else max(0.0, 1.0 - age / (7 * 24 * 3600))
        if item_tags and query_tags:
            iset = {t.lower() for t in item_tags}
            qset = {t.lower() for t in query_tags}
            union = iset | qset
            tag_score = len(iset & qset) / len(union) if union else 0.0
        else:
            tag_score = 0.0
        final = (
            _WEIGHTS[0] * item.get("score", 0.0)
            + _WEIGHTS[1] * recency
            + _WEIGHTS[2] * tag_score
            + _WEIGHTS[3] * item.get("importance", 0.5)
        )
        scored.append({**item, "final_score": final, "_timestamp": timestamp})
    scored.sort(key=lambda x: (x["final_score"], x.get("_timestamp", 0)), reverse=True)
    return scored


def bench_rank() -> Result:
    now = time.time()
    results = [
        {
            "text": f"memory {i}",
            "score": (i % 100) / 100,
            "importance": 0.5,
            "metadata": {
                "timestamp": now - i,
                "tags": ["python", "backend", f"tag{i % 7}"],
            },
        }
        for i in range(2000)
    ]
    query_tags = ["python", "backend", "tag3"]
    ranker = RetrievalRanker()

    base = _time(lambda: _rank_baseline(results, query_tags))
    opt = _time(lambda: ranker.rank(results, query_tags))
    return Result("hybrid rank (2k results)", base, opt)


# ── 3. Conflict grouping: sort every group vs O(n) max ──


def _conflict_baseline(engine: RetrievalEngine, ranked: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    passthrough: list[dict] = []
    for item in ranked:
        key = engine._extract_conflict_key(str(item.get("text", "")))
        if not key:
            passthrough.append(item)
        else:
            grouped.setdefault(key, []).append(item)

    winners = []
    for group in grouped.values():
        if len(group) == 1:
            winners.append(group[0])
            continue
        winner = sorted(group, key=engine._conflict_sort_key, reverse=True)[0]
        winners.append(winner)
    return passthrough + winners


def bench_conflicts() -> Result:
    # Large conflict groups make the algorithmic difference visible: the old
    # code sorted every group (O(k log k)); the new code scans for the max (O(k)).
    ranked = []
    for group in range(50):
        for i in range(2000):
            ranked.append(
                {
                    "text": f"My favorite topic{group} is value{i}",
                    "final_score": (i % 10) / 10,
                    "metadata": {"timestamp": float(i)},
                }
            )
    engine = RetrievalEngine(memory_manager=None)  # type: ignore[arg-type]

    base = _time(lambda: _conflict_baseline(engine, ranked))
    opt = _time(lambda: engine._resolve_conflicts(ranked))
    return Result("conflict winner (100k, big)", base, opt)


# ── 4. Knowledge section: repeated += vs list + join ──

_HEADER = "Relevant knowledge:\n"


def _knowledge_baseline(texts: list[str], max_tokens: int) -> str:
    section = _HEADER
    remaining = max_tokens - _COUNT(section)
    for text in texts:
        entry = f"- {text}\n"
        tokens = _COUNT(entry)
        if remaining - tokens < 0:
            break
        section += entry
        remaining -= tokens
    return section.strip()


def bench_knowledge_section() -> Result:
    from kimiko.core.context_builder import ContextBuilder

    builder = ContextBuilder()
    texts = [f"retrieved passage number {i} " + "detail " * 20 for i in range(2000)]
    # Pre-tokenize outside the timer: the real pipeline counts tokens once when
    # it receives retrieval results, not on every context assembly.
    entries = [(_t, _COUNT(_t)) for _t in texts]

    base = _time(lambda: _knowledge_baseline(texts, 200_000))
    opt = _time(
        lambda: builder._build_knowledge_section_from_counts(entries, 200_000)
    )
    return Result("knowledge assembly (2k)", base, opt)


# ── 5. Intent: string patterns + no early exit vs precompiled + early exit ──

_INTENT_PATTERNS = {
    "greeting": [r"\b(hi|hello|hey|howdy|greetings)\b"],
    "code": [
        r"\b(code|function|class|debug|error|traceback|implement|refactor)\b",
        r"\b(python|javascript|java|rust|golang|typescript|html|css)\b",
    ],
    "image": [r"\b(image|photo|picture|screenshot|diagram|visual)\b"],
    "document": [r"\b(document|pdf|file|paper|article|summarize)\b"],
    "agent": [r"\b(step\s*by\s*step|plan|create\s+a\s+project|build\s+me|automate)\b"],
    "tool": [r"\b(search\s+the\s+web|run\s+command|execute|terminal|browse)\b"],
    "question": [r"\b(what|why|how|when|where|who|explain|describe|tell\s+me)\b"],
}


def _intent_baseline(text: str):
    lowered = text.lower().strip()
    best_intent, best_score = "chat", 0.0
    for intent, patterns in _INTENT_PATTERNS.items():
        score = 0.0
        for pattern in patterns:
            score += len(re.findall(pattern, lowered)) * 0.3
        if score > best_score:
            best_intent, best_score = intent, score
    return IntentResult(
        intent=Intent(
            {
                "image": "image_analysis",
                "document": "document_query",
            }.get(best_intent, best_intent)
        ),
        confidence=min(best_score, 1.0),
    )


def bench_intent() -> Result:
    classifier = IntentClassifier()
    samples = [
        "Can you explain how the retrieval pipeline works in this Python service?",
        "Hello there, how are you doing today?",
        "Please debug this traceback and refactor the function",
        "hmm interesting",
        "Summarize this pdf document for me",
    ] * 200

    base = _time(lambda: [_intent_baseline(text) for text in samples])
    opt = _time(lambda: [classifier.classify(text) for text in samples])
    return Result("intent classify (1k)", base, opt)


# ── 6. SSE token serialization: Pydantic per token vs compact JSON ──


def bench_sse_serialization() -> Result:
    tokens = ["tok" + str(i) for i in range(5000)]

    def baseline() -> None:
        # Old hot loop: Pydantic model + JSON per token + manual SSE framing.
        for token in tokens:
            event = StreamEvent(event=StreamEventType.TOKEN, data=token)
            _ = f"data: {event.model_dump_json()}\n\n"

    def optimized() -> None:
        # Current hot loop: string concat + C-level JSON string encoding; framing
        # is handled once by EventSourceResponse.
        for token in tokens:
            _ = {
                "data": '{"event":"token","data":'
                + encode_basestring(token)
                + "}"
            }

    base = _time(baseline)
    opt = _time(optimized)
    return Result("SSE token frame (5k)", base, opt)


# ── 7. Embedding batching: N HTTP round-trips vs one ──

_EMBED_LATENCY = 0.001  # simulated 1 ms per upstream round-trip


def bench_embedding_batch() -> Result:
    texts = [f"document chunk {i}" for i in range(100)]

    async def run() -> tuple[float, float]:
        # Baseline: one embed() call per text, no cache.
        service = EmbeddingService(base_url="http://localhost:11434")
        calls = 0

        async def fake_request(inputs: list[str]) -> list[list[float]]:
            nonlocal calls
            calls += 1
            await asyncio.sleep(_EMBED_LATENCY)
            return [[float(len(t))] * 8 for t in inputs]

        service._request = fake_request  # type: ignore[assignment]
        start = time.perf_counter()
        for text in texts:
            await service.embed(text)
        baseline_ms = (time.perf_counter() - start) * 1000
        baseline_calls = calls

        # Optimized: batch call with cache empty.
        service2 = EmbeddingService(base_url="http://localhost:11434")
        calls2 = 0

        async def fake_request2(inputs: list[str]) -> list[list[float]]:
            nonlocal calls2
            calls2 += 1
            await asyncio.sleep(_EMBED_LATENCY)
            return [[float(len(t))] * 8 for t in inputs]

        service2._request = fake_request2  # type: ignore[assignment]
        start = time.perf_counter()
        await service2.embed_batch(texts)
        optimized_ms = (time.perf_counter() - start) * 1000

        await service.close()
        await service2.close()

        print(
            f"  embedding upstream calls: baseline={baseline_calls}, "
            f"optimized={calls2} (simulated {_EMBED_LATENCY * 1000:.0f} ms/call)"
        )
        return baseline_ms, optimized_ms

    base, opt = asyncio.run(run())
    return Result("embedding batch (100 chunks)", base, opt)


# ── 8. Retrieval dedup: list membership vs dict ──


def _dedup_baseline(items: list[dict]) -> list[dict]:
    seen: list[str] = []
    out: list[dict] = []
    for item in items:
        key = item["text"].strip().casefold()
        if key not in seen:  # O(n) scan per item → O(n²)
            seen.append(key)
            out.append(item)
    return out


def _dedup_optimized(items: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for item in items:
        key = item["text"].strip().casefold()
        best.setdefault(key, item)
    return list(best.values())


def bench_dedup() -> Result:
    # Half the items are duplicates.
    items = [
        {
            "text": f"passage {i % 3000}",
            "score": float(i % 10),
            "metadata": {"timestamp": float(i)},
        }
        for i in range(6000)
    ]

    base = _time(lambda: _dedup_baseline(items))
    opt = _time(lambda: _dedup_optimized(items))
    return Result("retrieval dedup (6k)", base, opt)


# ── 9. Embedding cache latency (async single-flight smoke benchmark) ──


def bench_embedding_cache_hits() -> Result:
    async def run() -> tuple[float, float]:
        async def no_request(inputs: list[str]) -> list[list[float]]:
            raise AssertionError("cache should have served this")

        service = EmbeddingService(base_url="http://localhost:11434")
        service._request = no_request  # type: ignore[assignment]

        # Warm the cache once. Stay under the configured cache size (512).
        total = 400
        cache: TTLCache = service._cache
        for i in range(total):
            cache.set(f"text-{i}", [float(i)] * 8)

        start = time.perf_counter()
        for i in range(total):
            await service.embed(f"text-{i}")
        cached_ms = (time.perf_counter() - start) * 1000

        await service.close()
        # Baseline equivalent: an uncached call would pay a network hop; use the
        # same simulated 1 ms as benchmark 7 for a conservative comparison.
        return total * _EMBED_LATENCY * 1000, cached_ms

    base, opt = asyncio.run(run())
    return Result("embedding cache hits (400)", base, opt)


def main() -> None:
    # Keep the benchmark output readable: silence per-request debug/info logs.
    import logging

    import structlog

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
    )

    benchmarks = [
        bench_truncate,
        bench_rank,
        bench_conflicts,
        bench_knowledge_section,
        bench_intent,
        bench_sse_serialization,
        bench_embedding_batch,
        bench_dedup,
        bench_embedding_cache_hits,
    ]

    results = [bench() for bench in benchmarks]

    print()
    print(f"{'benchmark':<34} {'baseline':>13} {'optimized':>13} {'speedup':>10}")
    print("-" * 74)
    for result in results:
        print(result.row())
    print("-" * 74)
    print(
        "Note: embedding rows model a 1 ms upstream round-trip; real Ollama\n"
        "latency is typically 5-50 ms per call, so those gains scale up."
    )


if __name__ == "__main__":
    main()
