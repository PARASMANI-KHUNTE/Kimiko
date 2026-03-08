# 🏯 Kimiko AI

**A local-first, multimodal, extensible AI agent platform.**

Kimiko is designed to be your private digital companion and agent, running primarily on your local hardware while maintaining sophisticated memory and a dynamic plugin ecosystem.

---

## 🌟 Key Features

### 🧠 Advanced Persistence
- **Three-Tier Memory**: Seamlessly blends short-term chat, semantic middle-term context (Retrieval Augmented Generation), and long-term structured facts.
- **Fact Extraction**: Automatically learns your preferences, habits, and identity from natural conversation.
- **Reinforcement & Decay**: Uses exponential decay to prioritize fresh, important memories while naturally forgetting trivial details.

### 👁️ Multimodal Sensing
- **Vision**: Understands images within conversation and agent reasoning loops via Qwen2-VL.
- **Voice**: Whisper-powered Speech-to-Text and Piper-powered Speech-to-Text for natural interaction.

### 🔌 Extensibility
- **Plugin System**: Dynamically add and namespace new capabilities (e.g., weather, search, file handling).
- **Agentic ReAct Pipeline**: powered by LangGraph to solve complex, multi-step tasks.

### 🔒 Privacy and Efficiency
- **Multi-User Isolation**: Strict data bounding between user sessions.
- **Smart Model Router**: Token-aware logic that keeps private tasks local while bursting heavy compute to remote providers when needed.
- **VRAM Scheduling**: Optimizes GPU usage to run large models on consumer hardware (e.g., RTX 4050 6GB).

---

## 🛠️ Getting Started

### Prerequisites
- Docker & Docker Compose
- NVIDIA GPU with 6GB+ VRAM (Recommended)

### Quick Launch
1. Clone the repository.
2. Create a `.env` file (see `docs/deployment.md`).
3. Run: `docker-compose up -d --build`.
4. Pull models: `docker exec -it ollama ollama pull qwen2.5 qwen2-vl`.

---

## 📖 Documentation

For detailed guides, explore our `docs/` folder:
- [🏗️ Architecture](docs/architecture.md): System design and request pipeline.
- [📊 Visuals & Diagrams](docs/visuals.md): Mind maps and flowcharts of internal logic.
- [🧠 Memory System](docs/memory_system.md): How Kimiko remembers and forgets.
- [🎙️ Multimodal Senses](docs/multimodal.md): Vision, Voice, and VRAM management.
- [🔌 Plugin Developer Guide](docs/plugins.md): Extending Kimiko's capabilities.
- [Docker & GPU Setup](docs/deployment.md): Deployment instructions.
- [API Reference](docs/api_reference.md): REST endpoints and schemas.

---

## ⚖️ License
MIT License. See `LICENSE` for details.
