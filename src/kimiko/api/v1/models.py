"""Models endpoint — list and inspect available AI models."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from kimiko.api.middleware.auth import verify_api_key
from kimiko.core.model_router import AVAILABLE_MODELS
from kimiko.models.schemas import ModelInfo, ModelListResponse
from kimiko.services.llm import ModelNotAvailableError, get_llm_service

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelListResponse)
async def list_models(
    _auth: dict = Depends(verify_api_key),
) -> ModelListResponse:
    """List all available models from the LLM runtime."""
    llm = get_llm_service()
    models = await llm.list_models()

    return ModelListResponse(
        models=[
            ModelInfo(
                name=m.get("name", "unknown"),
                size=_format_size(m.get("size", 0)),
                modified_at=m.get("modified_at"),
                details=m.get("details"),
            )
            for m in models
        ]
    )


@router.get("/catalog")
async def get_model_catalog(
    _auth: dict = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return the curated list of supported models with their pull status in Ollama."""
    llm = get_llm_service()
    try:
        pulled = await llm.list_models()
        pulled_ids = {m.get("name", "").split(":")[0] for m in pulled}
        pulled_full = {m.get("name", "") for m in pulled}
    except Exception:
        pulled_ids = set()
        pulled_full = set()

    catalog = []
    for m in AVAILABLE_MODELS:
        mid = m["id"]
        base_id = mid.split(":")[0]
        available = base_id in pulled_ids or mid in pulled_full
        catalog.append({**m, "available": available})

    return {"models": catalog}


@router.get("/{model_name}")
async def get_model_info(
    model_name: str,
    _auth: dict = Depends(verify_api_key),
) -> dict:
    """Get detailed information about a specific model."""
    try:
        llm = get_llm_service()
        info = await llm.model_info(model_name)
        return info
    except ModelNotAvailableError:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")


def _format_size(size_bytes: int) -> str:
    """Format byte count to human-readable size."""
    if size_bytes == 0:
        return "unknown"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
