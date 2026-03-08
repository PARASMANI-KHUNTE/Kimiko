# 📖 API Reference

Kimiko exposes a standard REST API for integration with web, mobile, or CLI clients.

## 💬 Chat Endpoints

### `POST /v1/chat`
The main entry point for conversation.
- **Payload**: `ChatRequest` (message, session_id, user_id, model, stream, images).
- **Behavior**: Orchestrates memory retrieval, intent classification, and LLM generation.

---

## 🤖 Agent Endpoints

### `POST /v1/agent/run`
Triggers the LangGraph agent for complex, multi-step tasks.
- **Payload**: `AgentTaskRequest` (goal, max_steps, user_id, images).
- **Behavior**: Runs the ReAct loop using internal tools and external plugins.

---

## 🔊 Audio Endpoints

### `POST /v1/audio/transcribe`
Converts speech to text via Whisper.
- **Payload**: Multipart form with `audio` file.

### `POST /v1/audio/synthesize`
Converts text to speech via Piper.
- **Payload**: `TTSRequest` (text, voice_id).

---

## 📂 Memory & Documents

### `POST /v1/documents/ingest`
Indexes a local file or directory into the semantic memory.
- **Payload**: `IngestRequest` (path, user_id).

### `GET /v1/memory/facts`
Retrieves the structured "extracted facts" for a specific user.
- **Query Params**: `user_id`.
