# 🎙️ Multimodal Senses

Kimiko is not just a text assistant; it perceives the world through integrated Vision and Voice processing.

## 👁️ Vision Engine

Kimiko uses the **Qwen2-VL** (Vision-Language Model) to understand visual inputs.

- **Request Format**: Images are accepted as Base64 encoded strings in the standard message payload.
- **Agent Integration**: The agent can "look" at an image, reason about its content, and then decide to use a tool (e.g., "See a circuit board" → "Search for component part numbers").
- **Adaptive Token Budgeting**: Visual data is token-heavy. Kimiko uses a ratio-based scaling formula to dynamically shrink conversation history when an image is processed, ensuring the context window is never exceeded.

---

## 🔊 Voice Layer

Kimiko provides high-performance, local-first audio processing.

### 1. Speech-to-Text (STT)
- **Engine**: **Whisper** (faster-whisper implementation).
- **Endpoint**: `POST /v1/audio/transcribe`.
- **Latency**: Sub-second transcription on modern GPUs.

### 2. Text-to-Speech (TTS)
- **Engine**: **Piper TTS**.
- **Endpoint**: `POST /v1/audio/synthesize`.
- **Why Piper?**: It produces high-quality, natural voice synthesis with extremely low CPU/GPU overhead, making it ideal for real-time interaction.

---

## ⚡ VRAM Optimization (The Model Scheduler)

Since Vision and Voice models compete for GPU memory with the core reasoning LLM, Kimiko employs a `ModelScheduler`:
- **Chat Models**: kept alive for 5 minutes of inactivity.
- **Vision/STT Models**: kept alive for only 30-60 seconds after use.
- **Automatic Offloading**: Models are swapped out of VRAM automatically when the task completes to maintain system stability on cards with limited memory (e.g., RTX 4050).
