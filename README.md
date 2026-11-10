# 🏯 Kimiko AI: Comprehensive Codebase Analysis Report

## 1. Executive Summary
Kimiko AI is a **local-first, multimodal, and extensible AI agent platform**. It is designed to run sophisticated AI agents on consumer-grade hardware (like a laptop with an RTX GPU) while maintaining deep, personalized memory through a three-tier storage system. The platform is modular, allowing for easy expansion through a dynamic plugin ecosystem.

---

## 2. Core Technology Stack

### Backend
- **Language**: Python 3.11+
- **Web Framework**: FastAPI (Asynchronous, high-performance)
- **Agent Orchestration**: LangGraph & LangChain (For stateful, multi-step agent logic)
- **AI Models**: 
  - **Ollama**: Local model runner (serving Qwen2.5, Qwen2-VL)
  - **Whisper**: Speech-to-Text (STT)
  - **Piper**: Text-to-Speech (TTS)
- **Task Queue**: Celery with Redis (For background fact extraction and maintenance)

### Frontend
- **Framework**: Next.js (React 19)
- **STyling**: Tailwind CSS 4.0
- **Language**: TypeScript

### Data & Infrastructure
- **PostgreSQL**: Long-term structured data (User identities, preferences, facts)
- **Qdrant**: Vector database for semantic search (Retrieval Augmented Generation - RAG)
- **Redis**: High-speed cache for recent conversation history and message broker.
- **Docker**: Containerization and orchestration.

---

## 3. System Architecture

Kimiko follows a **Modular Pipeline** design. Every request flows through a series of dedicated engines:

```mermaid
graph TD
    A[User Request] --> B{Modality?}
    B -- Voice --> C[Whisper STT]
    B -- Image --> D[Vision Engine]
    B -- Text --> E[Intent Classifier]
    
    C --> E
    D --> E
    
    E --> F[Retrieval Engine]
    
    subgraph MemoryLayer [Memory & RAG]
        F --> G[(PostgreSQL Facts)]
        F --> H[(Qdrant Semantic)]
        F --> I[Redis History]
    end
    
    G & H & I --> J[Context Builder]
    J --> K[Model Router]
    
    subgraph Inference [Hybrid Routing]
        K -- Critical/Private --> L[Local Ollama]
        K -- Complex/Heavy --> M[Remote API]
    end
    
    L & M --> N[LangGraph Agent]
    
    subgraph AgentLoop [ReAct Loop]
        N --> O{Need Tool?}
        O -- Yes --> P[Tool Executor]
        P --> Q[Internal Tools / Plugins]
        Q --> N
        O -- No --> R[Final Answer]
    end
    
    R --> S[Streaming Engine]
    S --> T[User Response]
```

### Key Subsystems:
1.  **Memory Manager**: Mimics human recall with three tiers (Short, Middle, Long term).
2.  **Fact Evolution Cycle**: A background process that extracts structured facts from text and applies "forgetting" (exponential decay) to keep memory relevant.
3.  **Model Scheduler**: Manages VRAM by swapping models in/out of the GPU based on use.
4.  **Plugin Engine**: Dynamically registers new tools into the agent's reasoning loop.

---

## 4. Folder-by-Folder Breakdown

### Root Directory
- `Dockerfile` & `docker-compose.yml`: Orchestration for the entire stack.
- `pyproject.toml`: Backend dependencies and Python environment setup.
- `alembic/`: Database migration scripts for PostgreSQL.
- `docs/`: In-depth documentation for architecture, memory, and plugins.

### Backend (`src/kimiko/`)
- `agents/`: The "brain". Contains the LangGraph engine (`engine.py`) and agent prompts.
- `api/`: REST and WebSocket endpoints. `v1/` contains versioned routes for chat, memory, and plugins.
- `core/`: Core internal logic, including the model router and hardware scheduler.
- `db/`: Database configuration and SQLAlchemy models.
- `memory/`: The memory system.
    - `fact_extraction.py`: AI-powered logic to learn about the user.
    - `semantic.py`: Interface for Qdrant (vector search).
    - `short_term.py`: Redis-based history management.
- `plugins/`: The extension layer. `installed/` includes the active plugins.
- `services/`: Implementation of core features like vision and voice processing.
- `workers/`: Celery task definitions for background processing.

### Frontend (`web/`)
- `src/app/`: Next.js App Router structure.
    - `/agent`: The main chat interface.
    - `/memory`: Dashboard to visualize what Kimiko knows.
    - `/metrics`: System performance and VRAM monitoring.
    - `/plugins`: UI for enabling/disabling extensions.
- `src/components/`: Reusable UI elements (Chat bubbles, Sidebar, etc.).

---

## 🚀 Quick Start (Complete App)

To start everything (AI Engines, Databases, Backend, and Frontend) in one go:

```powershell
# 1. Start all containers
docker-compose up -d --build

# 2. Wait 30 seconds, then start the OS Assistant service
python -m kimiko.os.assistant
```

---

## 🛠️ Technical Stack Breakdown

Kimiko is powered by a robust and modern stack designed for high-performance AI orchestration:

### 1. AI / Machine Learning Core
*   **onnxruntime**: Efficient machine learning model execution.
*   **ctranslate2**: High-performance inference engine for transformers.
*   **tokenizers**: Fast HuggingFace tokenization.
*   **huggingface-hub**: Model and dataset management.
*   **numpy**: Numerical computing backbone.
*   **sympy / mpmath**: Symbolic and high-precision math.

### 2. LLM / Agent Framework
*   **langgraph**: Core framework for agent workflows.
*   **langgraph-sdk / utilities**: Workflow state and checkpointing.
*   **langchain-core**: LLM pipeline utilities.
*   **langsmith**: Debugging and monitoring.

### 3. Vector Database & Retrieval
*   **qdrant-client**: Interface for the Qdrant semantic memory layer.

### 4. Backend / API Framework
*   **fastapi**: Modern async Python API.
*   **starlette / uvicorn**: ASGI toolkit and server.
*   **sse-starlette**: Real-time streaming responses.
*   **httpx**: Async HTTP communication.

### 5. Task Queue / Background Workers
*   **celery**: Distributed task management.
*   **redis**: In-memory message broker and caching.

### 6. Database / Persistence
*   **sqlalchemy**: Database ORM.
*   **asyncpg**: Async PostgreSQL driver.
*   **alembic**: Database migrations.

### 7. Authentication & Security
*   **jose / cryptography**: JWT and secure encryption.
*   **bcrypt / passlib**: Password hashing.

### 8. Computer Vision / Media
*   **opencv-python**: Computer vision toolkit (UI detection).
*   **Pillow / pytesseract**: Image processing and OCR.
*   **av**: Video processing.

### 9. Speech & Audio AI
*   **faster-whisper**: High-speed Speech-to-Text.
*   **piper-tts**: Near-instant Text-to-Speech.

### 10. OS Automation
*   **pywinauto / uiautomation**: Windows UI and accessibility control.
*   **python-xlib**: Linux GUI interaction.

### 11. CLI / Developer Tools
*   **typer / click**: CLI framework for agent interaction.
*   **rich**: Enhanced terminal visualization.

### 12. Performance & Infrastructure
*   **uvloop**: Optimized async event loop.
*   **websockets**: Low-latency communication.
*   **watchfiles**: Reactive file monitoring.

---

## 🏗️ The Big Picture

```mermaid
graph TD
    A[Vision + Speech] --> B[LLM / Agent Layer - LangGraph]
    B --> C[Memory Layer]
    C --> D[Redis - Short-term]
    C --> E[Qdrant - Semantic]
    C --> F[PostgreSQL - Long-term]
    B --> G[Automation Layer]
    G --> H[FastAPI Backend]
    H --> I[Celery Workers]
```

---

## 5. Setup and Running

### Prerequisites
- **Docker & Docker Compose**
- **NVIDIA GPU** (Recommended 6GB+ VRAM)

### Step-by-Step Installation
1.  **Clone the Repo**:
    ```bash
    git clone <repo_url>
    cd Kimiko
    ```
2.  **Configure Environment**:
    - Copy `.env.example` to `.env`.
    - Edit `.env` to set passwords and API keys (if using remote providers).
### Option 1: The Complete App (Docker - Recommended)
This starts all services (PostgreSQL, Qdrant, Redis, Ollama, Backend, and Frontend) in a single command.

1.  **Launch Infrastructure**:
    ```powershell
    docker-compose up -d --build
    ```
2.  **Prepare Models**:
    Pull the required local models into Ollama:
    ```bash
    docker exec -it kimiko-ollama ollama pull qwen2.5
    docker exec -it kimiko-ollama ollama pull qwen2-vl
    docker exec -it kimiko-ollama ollama pull nomic-embed-text
    ```
3.  **Access the Dashboard**:
    - **Backend API**: `http://localhost:8000/docs` (Swagger)
    - **Frontend UI**: `http://localhost:3000`

### Option 2: Manual Component Startup (Local Development)
If you want to run components separately for development:

#### A. Backend API (FastAPI)
```powershell
# From the project root
pip install -e .
uvicorn kimiko.main:app --reload --port 8000
```

#### B. Frontend Dashboard (Next.js)
```powershell
cd web
npm install
npm run dev
```

#### C. OS Assistant Overlay (Electron)
To use the Ctrl+Space overlay, you need both the background service and the UI:
1.  **Terminal 1 (Backend Service)**:
    ```powershell
    python -m kimiko.os.assistant
    ```
2.  **Terminal 2 (Electron UI)**:
    ```powershell
    cd src/kimiko/os/ui-electron
    npm install
    npm start
    ```

#### D. Running the CLI Tool
To use the `kimiko` command from your terminal, verify it's installed in editable mode:
```powershell
# Run once from project root
pip install -e .

# Then use the tool:
kimiko status
kimiko chat
```

---

## 6. Development Workflow
- **Adding a Plugin**: Create a new module in `src/kimiko/plugins/installed/` following the `base.py` interface.
- **Database Changes**: Modify models in `src/kimiko/db/models/` and run `alembic revision --autogenerate`.
- **Testing**: Run `pytest` from the root directory to execute the automated test suite.
