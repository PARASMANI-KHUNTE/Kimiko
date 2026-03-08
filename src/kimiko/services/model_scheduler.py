"""Model Scheduler — Manages VRAM allocation for robust multimodal interactions."""

import httpx
import structlog

from kimiko.config import get_settings

logger = structlog.get_logger(__name__)


class ModelScheduler:
    """Manages Ollama model lifecycles to prevent VRAM overflow on constrained hardware.

    Specifically handles the transient lifetimes of perception models (Vision, Whisper)
    while keeping the primary Agent reasoning model (Chat) persistent in memory.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.ollama_base_url
        if not self.base_url.endswith("/api/generate"):
            self.api_url = f"{self.base_url}/api/generate"
        else:
            self.api_url = self.base_url

        # Configured lifecycles. Perception models unload quickly to free VRAM.
        self.schedules = {
            "chat": "5m",       # Chat stays hot for fluid conversation.
            "vision": "30s",    # Unload immediately after processing image.
            "whisper": "30s"    # Unload immediately after transcribing audio.
        }

    async def _configure_keep_alive(self, model_name: str, keep_alive: str) -> None:
        """Sends a dummy completion to Ollama solely to trigger the keep_alive timer."""
        payload = {
            "model": model_name,
            "prompt": "",
            "keep_alive": keep_alive
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(self.api_url, json=payload)
                res.raise_for_status()
                logger.debug("model_keep_alive_set", model=model_name, keep_alive=keep_alive)
        except Exception as e:
            logger.warning("failed_to_set_keep_alive", model=model_name, error=str(e))

    async def schedule_chat(self, model_name: str) -> None:
        """Prioritize the main LLM to keep reasoning quick."""
        await self._configure_keep_alive(model_name, self.schedules["chat"])

    async def schedule_vision(self, vision_model: str) -> None:
        """Warm up the vision model for brief multimodal parsing."""
        await self._configure_keep_alive(vision_model, self.schedules["vision"])

    async def schedule_stt(self, stt_model: str) -> None:
        """Warm up the STT model for transcription."""
        await self._configure_keep_alive(stt_model, self.schedules["whisper"])

    async def release_model(self, model_name: str) -> None:
        """Immediately flush a model from GPU memory."""
        await self._configure_keep_alive(model_name, "0s")
        logger.info("model_unloaded", model=model_name)
