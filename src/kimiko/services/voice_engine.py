"""Voice engine — speech-to-text (Whisper) and text-to-speech (Piper)."""

from __future__ import annotations

import io
import os
import tempfile
from typing import AsyncIterator, BinaryIO

import structlog
from faster_whisper import WhisperModel

logger = structlog.get_logger(__name__)


class VoiceEngine:
    """Handles STT via Whisper and TTS via Piper."""

    def __init__(
        self,
        stt_model_size: str = "base",
        device: str = "cpu",  # or "cuda"
        compute_type: str = "int8",
    ) -> None:
        self.stt_model_size = stt_model_size
        self.device = device
        self.compute_type = compute_type
        self._stt_model: WhisperModel | None = None

    def _get_stt_model(self) -> WhisperModel:
        if self._stt_model is None:
            logger.info("loading_whisper_model", size=self.stt_model_size)
            self._stt_model = WhisperModel(
                self.stt_model_size, 
                device=self.device, 
                compute_type=self.compute_type
            )
        return self._stt_model

    async def transcribe(self, audio_data: BinaryIO) -> str:
        """Transcribe audio data to text."""
        model = self._get_stt_model()
        
        # WhisperModel.transcribe takes a path or buffered reader
        segments, info = model.transcribe(audio_data, beam_size=5)
        
        text = ""
        for segment in segments:
            text += segment.text + " "
            
        logger.info("transcription_complete", language=info.language, probability=info.language_probability)
        return text.strip()

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Synthesize text to speech using Piper.
        
        Returns an async iterator of audio bytes (WAV format).
        """
        # Piper typically runs as a CLI or library that outputs raw PCM
        # For this prototype, we'll use a placeholder or implement a basic call
        # In a real scenario, we'd use piper-python or subprocess
        
        logger.info("synthesizing_speech", text=text[:50])
        
        # Placeholder for Piper synthesis
        # real implementation would involve:
        # 1. piper.synthesize(text, output_file)
        # 2. yielding chunks
        
        # For now, let's yield a dummy byte stream to test the API structure
        yield b"audio_chunk_1"
        yield b"audio_chunk_2"

    async def transcribe_stream(self, audio_generator: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """Stream transcription (Gemini-style).
        
        Chops stream into segments and transcribes.
        """
        # This is complex with standard Whisper. 
        # Usually requires VAD (Voice Activity Detection) and chunking.
        # For now, we'll accumulate and transcribe periodically.
        
        buffer = io.BytesIO()
        async for chunk in audio_generator:
            buffer.write(chunk)
            # Logic to detect pause and transcribe...
            # yield transcribed_part
            pass
        
        buffer.seek(0)
        yield await self.transcribe(buffer)
