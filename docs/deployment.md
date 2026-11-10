# 🐳 Deployment & Setup

Kimiko is orchestrated using Docker Compose for consistent local development and production-ready environments.

## 💻 Hardware Requirements

- **Minimum**: 16GB RAM, modern CPU.
- **Recommended**: NVIDIA GPU with 6GB+ VRAM (e.g., RTX 3060/4050 or higher).
- **Storage**: ~20GB for Docker images and local LLM/Voice models.

---

## 🛠️ Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- NVIDIA Container Toolkit (for GPU acceleration)

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
OLLAMA_HOST=http://host.docker.internal:11434
POSTGRES_URL=postgresql+asyncpg://kimiko:password@db:5432/kimiko
QDRANT_HOST=qdrant
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=your_key_here_for_smart_burst
```

### 3. Launch the Stack
```bash
docker-compose up -d --build
```

---

## 🏗️ Services Overview

- **`kimiko-api`**: The main FastAPI application serving the REST endpoints.
- **`kimiko-worker`**: Background task processor (Fact extraction, document indexing).
- **`ollama`** *(optional)*: Containerised LLM runtime, enabled with the
  `docker-ollama` profile. By default Kimiko uses the Ollama running on the host.
- **`qdrant`**: Vector database for semantic search.
- **`postgres`**: Relational storage for memories and facts.
- **`redis`**: High-speed cache for chat sessions.

---

## 🗄️ Database Bootstrap

On startup the API creates any missing tables (`Base.metadata.create_all`, which
is a no-op once the schema exists) and seeds a local default user:

| Field | Value |
| --- | --- |
| username | `default` |
| id | `11111111-1111-1111-1111-111111111111` |

This makes `GET /v1/memory/facts?user_id=default` work on a brand-new database
and attributes anonymous web/CLI chats to a real `users` row. It is controlled
by `KIMIKO_AUTO_CREATE_SCHEMA` (default `true`); set it to `false` once Alembic
migrations own the schema in production.

---

## 🖥️ Web Dashboard

The Next.js dashboard in `web/` talks to the API through server-side rewrites:

| Frontend path | Backend path |
| --- | --- |
| `/health` | `/health` |
| `/api/metrics` | `/metrics` (Prometheus) |
| `/v1/:path*` | `/v1/:path*` |

The backend origin defaults to `http://localhost:8000` and can be overridden
with `KIMIKO_API_URL` (for example `KIMIKO_API_URL=http://192.168.1.10:8000`).

```bash
cd web
npm install
npm run build && npm start     # production
# or: npm run dev              # development, hot reload
```

Note: `/metrics` in the browser is the dashboard page, which is why the
Prometheus scrape endpoint is proxied at `/api/metrics` instead.

---

## 🔄 Model Initialization

Kimiko talks to whichever Ollama instance `KIMIKO_OLLAMA_BASE_URL` points at.
The default Compose stack expects Ollama on the host
(`http://host.docker.internal:11434`) because a host install already has GPU
access configured. A containerised Ollama is available behind an opt-in profile:

```bash
docker compose --profile docker-ollama up -d
```

### Recommended models for 6 GB VRAM / 16 GB RAM

| Purpose | Model | Download | Notes |
| --- | --- | --- | --- |
| Chat, reasoning, code, tools, vision | `qwen3.5:4b` | ~3.3 GB | Default. Multimodal, 256K context, thinking mode |
| Embeddings | `embeddinggemma-2:270m` | ~304 MB | 768-d, multilingual + code, 8K context |
| Quality upgrade (optional) | `qwen3.5:9b` | ~6.6 GB | Better answers; needs partial CPU offload on 6 GB |
| Code/agent upgrade (optional) | `mimo-v2.6:9b` | ~6.6 GB | Qwen3.5-9B fine-tune for code and agent workflows |

`qwen3-coder:30b` (~19 GB) and other 20B+ models do not fit this hardware and are
not recommended.

Pull the defaults and point Kimiko at them:

```bash
ollama pull qwen3.5:4b
ollama pull embeddinggemma-2:270m
```

```env
KIMIKO_DEFAULT_MODEL=qwen3.5:4b
KIMIKO_EMBEDDING_MODEL=embeddinggemma-2:270m
KIMIKO_VECTOR_SIZE=768
```

> **Switching embedding models?** Vectors from different models are not
> comparable. Recreate the `memories` collection in Qdrant so it is rebuilt with
> the new model's dimension.

