# Kimiko AI

Intelligent AI middleware platform.

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- NVIDIA GPU (recommended for LLM inference)

### Local Development (Docker)

```bash
# Start all services
docker-compose up -d

# Pull required models
docker exec kimiko-ollama ollama pull qwen2.5
docker exec kimiko-ollama ollama pull nomic-embed-text

# Check health
curl http://localhost:8000/health

# Chat
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello, Kimiko!"}]}'
```

### Local Development (Without Docker)

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
copy .env.example .env

# Run database migrations
alembic upgrade head

# Start the server
uvicorn kimiko.main:app --reload --port 8000
```

## Architecture

```
Client → API Gateway → Orchestrator → [Intent → Retrieval → Context → Model Router → LLM] → Response
```

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health check |
| `/metrics` | GET | Prometheus metrics |
| `/v1/chat` | POST | Chat (sync) |
| `/v1/chat/stream` | POST | Chat (SSE streaming) |
| `/v1/memory` | POST | Store memory |
| `/v1/memory/{user_id}` | GET | Retrieve memories |
| `/v1/memory/search` | POST | Semantic search |
| `/v1/models` | GET | List available models |

## Tech Stack

- **API**: FastAPI + Uvicorn
- **LLM**: Ollama (Qwen, Llama, CodeLlama)
- **Embeddings**: nomic-embed-text
- **Vector DB**: Qdrant
- **Cache/Sessions**: Redis
- **Database**: PostgreSQL + SQLAlchemy
- **Workers**: Celery + Redis
- **Observability**: Prometheus + structlog
