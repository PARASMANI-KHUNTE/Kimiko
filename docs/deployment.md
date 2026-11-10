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
OLLAMA_HOST=http://ollama:11434
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
- **`ollama`**: Serves the local LLM and embedding models.
- **`qdrant`**: Vector database for semantic search.
- **`db` (Postgres)**: Relational storage for memories and facts.
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

After the first boot, you must pull the required models into Ollama:
```bash
docker exec -it ollama ollama pull qwen2.5
docker exec -it ollama ollama pull qwen2-vl
docker exec -it ollama ollama pull nomic-embed-text
```
