"""Audio API endpoints — speech-to-text (STT) and text-to-speech (TTS)."""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, Response, HTTPException
from fastapi.responses import StreamingResponse
import io

from kimiko.services.voice_engine import VoiceEngine

router = APIRouter(prefix="/audio", tags=["multimodal"])
voice_engine = VoiceEngine()


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, str]:
    """Transcribe an uploaded audio file to text using Whisper."""
    if not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be an audio file.")
    
    try:
        content = await file.read()
        audio_stream = io.BytesIO(content)
        text = await voice_engine.transcribe(audio_stream)
        return {"text": text, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/synthesize")
async def synthesize_speech(text: str) -> StreamingResponse:
    """Synthesize text to speech using Piper (WAV stream)."""
    try:
        audio_iterator = voice_engine.synthesize(text)
        return StreamingResponse(audio_iterator, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")
