# Performance notes

This document records the backend performance work in `src/kimiko`: what
changed, why, and how to reproduce the measurements.

Most of the request path is dominated by Ollama generation, so the goal here is
to remove everything *around* the LLM that was adding avoidable latency:

- repeated network round-trips (model list, embeddings)
- serial work that could run concurrently
- N+1 queries and per-item sorting
- O(n²) string/list building
- per-token Pydantic serialization

## Reproduce

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install structlog pydantic pydantic-settings `
    sqlalchemy[asyncio] qdrant-client redis tenacity httpx prometheus-client `
    pytest pytest-asyncio

$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe benchmarks\perf_bench.py
.\.venv\Scripts\python.exe -m pytest tests/test_perf_primitives.py `
    tests/test_conflict_resolution.py tests/test_fact_store.py -q
```

## Measured micro-benchmarks

Single process, CPU-bound, median of 5 runs. Numbers vary by machine; the
relative gains and the algorithmic change are the point.

| Benchmark | Before | After | Speedup |
|---|---:|---:|---:|
| `truncate_messages` (2k messages kept) | 1.0–9.5 ms | 0.38–0.76 ms | **2.5–12×** |
| Hybrid rank (2k results) | 4.9–10.1 ms | 4.2–8.9 ms | **~1.1–1.6×** |
| Conflict winner (100k, large groups) | 91–148 ms | 93–143 ms | ~1.0× |
| Knowledge section assembly (2k entries) | 0.58–1.17 ms | 0.42–1.00 ms | **~1.4×** |
| Intent classify (1k messages) | 14.4–29.2 ms | 13.3–26.8 ms | ~1.05–1.1× |
| SSE token frame (5k tokens) | 12.3–21.4 ms | 0.89–1.7 ms | **8–23×** |
| Embedding batch (100 chunks) | ~1520 ms | 4.5–12 ms | **120–335×** |
| Retrieval dedup (6k items) | 88–181 ms | 1.0–1.3 ms | **~90–140×** |
| Embedding cache hits (400) | 400 ms | 0.28–0.50 ms | **800–1450×** |

Ranges reflect run-to-run variance on a shared machine; re-run the benchmark for
numbers on your hardware.

Notes on interpretation:

- The embedding rows simulate a **1 ms** upstream round-trip. Real Ollama
  embeddings are typically 5–50 ms per call, so the wall-clock savings scale up.
  The important structural result is **100 upstream calls → 1** for a 100-chunk
  document, and **0** calls for cache hits.
- Conflict resolution is intentionally neutral. The `O(k)` max replaces an
  `O(k log k)` sort, but CPython's Timsort is C-level and competitive for the
  small group sizes that actually occur. The single-pass version still avoids
  the second scan that the earlier implementation used to find the group's
  strongest score.
- Intent classification was already fast. Precompiled patterns + `search`
  (instead of `findall`) remove allocations but are a small constant-factor win.
- Knowledge section assembly: list + `join` beats repeated `str +=`, and the
  per-entry token formula is inlined with the divisor hoisted. (The benchmark
  pre-tokenizes entries outside the timer, matching the real pipeline.)

## What changed

### Caching and request coalescing

- `core/cache.py` (new): bounded LRU+TTL cache and `AsyncSingleFlight`.
- `services/embedding.py`:
  - deterministic embeddings are cached (`KIMIKO_EMBEDDING_CACHE_SIZE`,
    `KIMIKO_EMBEDDING_CACHE_TTL`);
  - concurrent identical misses are coalesced into one upstream call;
  - `embed_batch()` sends unique misses in a single `/api/embed` request and
    preserves input order.
- `services/llm.py`:
  - the Ollama model list is cached for `KIMIKO_MODEL_LIST_CACHE_TTL` seconds
    with a lock so refreshes never stampede;
  - `is_available()` is an O(1) set lookup on the cached list;
  - vision-model detection is memoized.

### Concurrency

- `core/retrieval_engine.py`: summary, vector search, and SQL memory/fact
  retrieval run in `asyncio.gather`. One failing source is isolated and logged
  instead of discarding the whole result set.
- `core/orchestrator.py`: retrieval, conversation history, and model routing run
  concurrently on both streaming and non-streaming paths. The conversation
  summary is fetched once and shared with retrieval.
- `main.py`: Redis, Postgres, and Qdrant connect in parallel at startup.
- `db/qdrant.py`: payload indexes are created concurrently.

### Batching and query shape

- `memory/fact_store.py`: `store_facts()` performs one bulk SELECT and indexes
  existing facts by `(category, fact)` instead of one SELECT per extracted fact.
  `get_facts()` accepts a `limit`.
- `memory/document_engine.py`: uses the new `SemanticMemory.index_many()`
  (batch embed + one Qdrant upsert) instead of one embed + one upsert per chunk.
- `models/database.py` + `alembic/versions/b7c9d1e2f3a4_add_hot_path_indexes.py`:
  composite indexes for the two hot retrieval queries.

### Algorithmic hot spots

- `core/token_manager.py`: `truncate_messages()` appends and reverses (O(n))
  instead of `insert(0, ...)` per message (O(n²)); budget lookup tries the exact
  base model first.
- `core/ranking.py`: one clock read per batch, query tag set built once, and
  wrapped dict output with precomputed timestamps.
- `core/context_builder.py`: retrieval texts are tokenized once and reused;
  sections are assembled with a list + `join`.
- `core/retrieval_engine.py`: duplicate texts are collapsed with a hash map;
  conflict winners use a single `max()` scan; conflict-key regex is compiled
  once and memoized with `lru_cache`.
- `core/intent.py`: patterns compiled at import, first-match `search`, early
  exit once confidence reaches 1.0.
- `memory/short_term.py`: `RPUSH` + `EXPIRE` pipelined; returns the new list
  length so callers skip an extra `LLEN`; summary write + `LTRIM` pipelined;
  active-session gauge no longer increments per message.
- `memory/long_term.py`: UUID parsing memoized.

### Streaming

- `core/streaming.py`: no Pydantic model per token. Frames are built with
  `json.encoder.encode_basestring` and a constant prefix, and the labeled
  Prometheus counter is resolved once per stream.
- SSE frames are now returned as `{"data": ...}` mappings because
  `EventSourceResponse` adds the `data:` prefix and framing. The previous
  pre-framed strings would be double-prefixed.
- The orchestrator collects tokens through a tee wrapper instead of parsing each
  SSE frame back from JSON.

### LLM verification

- The second grounding LLM call is now opt-in (`KIMIKO_VERIFY_GROUNDING=true`).
  By default the pipeline logs a cheap lexical-overlap score and skips the extra
  round-trip. Answers are persisted after citation cleanup/grounding.

### Workers

- `workers/async_runner.py` (new): Celery tasks reuse a persistent thread-local
  event loop instead of creating (and abandoning) one per task.
- Service singletons are initialized idempotently and left warm so HTTP/Redis
  pools are reused across tasks.
- `fact_worker` uses `session_scope()` for transactional DB work.

### Configuration

New settings in `config.py`:

| Setting | Default | Purpose |
|---|---:|---|
| `model_list_cache_ttl` | `30.0` | Seconds to cache Ollama `/api/tags` |
| `embedding_cache_size` | `512` | Max cached embedding vectors (LRU) |
| `embedding_cache_ttl` | `600.0` | Embedding cache entry lifetime |
| `verify_grounding` | `false` | Enable the extra grounding LLM call |
| `db_echo` | `false` | Log SQL statements (was implicitly `is_development`) |

## Operational notes

- Caches are **per process**, not shared across API/worker processes. That is
  intentional for cheap-to-recompute values like embeddings and the model list.
- If a model is pulled while the API is running, the model list refreshes after
  `model_list_cache_ttl` seconds (or call `invalidate_model_cache()`).
- Apply the new migration with `alembic upgrade head` to get the hot-path
  indexes; without it the queries are still correct but slower.
- `KIMIKO_VERIFY_GROUNDING=true` restores the stricter (slower) answer check.
