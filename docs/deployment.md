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

## 🔄 Model Initialization

After the first boot, you must pull the required models into Ollama:
```bash
docker exec -it ollama ollama pull qwen2.5
docker exec -it ollama ollama pull qwen2-vl
docker exec -it ollama ollama pull nomic-embed-text
```
