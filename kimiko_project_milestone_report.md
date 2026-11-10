# 🏯 Kimiko AI: Project Milestone Report (Phases 1-4)

This report summarizes the evolution of **Kimiko**, from a single-file AI script to a sophisticated, multi-user, multimodal agent platform. It is designed to be accessible to both end-users and technical developers.

---

## 🌟 What is Kimiko?
**Kimiko** is a local-first, multimodal AI agent platform. Unlike generic chatbots, Kimiko:
- **Actually Remembers**: It builds a structured "long-term memory" of your preferences and facts.
- **Can See & Hear**: It processes voice and vision natively.
- **Extensible**: It uses a plugin system to learn new skills (like weather, file management, or web search).
- **Privacy First**: It runs primarily on your local hardware but smartly "bursts" to the cloud when needed.

---

## 🗺️ The Journey: Phase by Phase

### Phase 1: Core Foundation
*The goal was to create a reliable local chat engine.*
- **User Experience**: A basic chat interface that talks back using local AI.
- **Dev Deep Dive**: 
    - **Stack**: FastAPI (Web Engine) + PostgreSQL (Database).
    - **Inference**: Integrated with **Ollama** to run models like `Qwen2.5` locally.
    - **Result**: A stable REST API that can maintain simple conversation history.

### Phase 2: The "Brain" (Hybrid RAG)
*The goal was to give the AI memory and the ability to read documents.*
- **User Experience**: Kimiko can now "search" your past conversations and read PDF/Text documents you give it.
- **Dev Deep Dive**:
    - **Memory Manager**: Orchestrates between short-term (RAM), middle-term (Vector DB), and long-term (SQL).
    - **Vector Search**: Integrated **Qdrant** for semantic retrieval (understanding meaning, not just keywords).
    - **Retrieval Engine**: Implemented a "Retrieval → Ranking → Context Building" pipeline.

### Phase 3 & 3.5: Senses & Stability (Multimodal)
*The goal was to add eyes, ears, and smart resource management.*
- **User Experience**: You can talk to Kimiko via voice and show it images. It also got "smarter" at remembering facts about you (e.g., "I like Python").
- **Dev Deep Dive**:
    - **Voice Layer**: **Whisper** (faster-whisper) for Speech-to-Text; **Piper TTS** for fast, local Speech synthesis.
    - **Vision Engine**: Integrated `Qwen2-VL` for image understanding within the agent loop.
    - **VRAM Scheduling**: Created a `ModelScheduler` to swap models in/out of the GPU (vital for cards with limited VRAM like the RTX 4050).
    - **Memory Decay**: Implemented an exponential decay formula so the AI "forgets" trivial details but reinforces important facts.

### Phase 4: The Platform Layer (Scale)
*The goal was to transform from a personal script into a scalable platform.*
- **User Experience**: Multiple users can now use Kimiko without their data leaking to each other. Developers can write "Plugins" to add new tools.
- **Dev Deep Dive**:
    - **Plugin Manager**: A dynamic loader that detects Python scripts in a folder and injects them as "Agent Tools" with automatic namespacing (`weather.get_current`).
    - **Multi-User Isolation**: Strict UUID-based filtering across all database queries and vector searches.
    - **Smart Model Router**: A logic layer that decides if a task is too big for local hardware (routing to OpenAI/vLLM) while keeping private data local.

---

## 🛠️ Technology Stack

| Component | Technology | Why? |
|-----------|------------|------|
| **Back-end** | Python 3.11, FastAPI | Speed and async performance. |
| **Agent Logic** | LangGraph | State-of-the-art "Agentic" workflows and tool usage. |
| **Local LLM** | Ollama | Industry-standard local model serving. |
| **Vector DB** | Qdrant | High-performance semantic search. |
| **Relational DB** | PostgreSQL | Robust long-term memory and structured facts. |
| **Perception** | Whisper & Piper | The fastest local voice stack available. |
| **Orchestration** | Docker | Consistent deployment across Dev/Prod. |

---

## 🧠 Sophisticated Features (The "Secret Sauce")

1. **Exponential Fact Decay**: Kimiko doesn't just store text; it calculates a "confidence score" that fades over time unless the facts are reinforced.
2. **Ratio-Based Token Budgeting**: When you show an image, Kimiko automatically "shrinks" its memory history to make room for the visual data without crashing.
3. **Warm-Model Routing**: The router prefers models already loaded in GPU memory to minimize the "loading lag" for the user.
4. **Namespace Enforcement**: Plugin tools are automatically prefixed (e.g., `weather.`) to prevent third-party plugins from breaking core system tools.

---

## 🚀 Future Roadmap: Phase 5 & Beyond
- **Observability**: Dashboard to see GPU usage and tool latency in real-time.
- **Rate Limiting**: Protection for the local hardware against multi-user abuse.
- **Advanced Sandboxing**: Running plugins in isolated containers for maximum security.
- **Streaming Voice**: Real-time "always-listening" assistant mode.

**Kimiko is now a production-ready blueprint for a private, extensible AI Agent platform.**
