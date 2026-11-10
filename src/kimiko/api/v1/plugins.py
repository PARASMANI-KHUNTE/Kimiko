"""Plugins endpoint — list dynamically loaded plugins.

The CLI (``kimiko plugins``) and the web dashboard both read this route, so it
must return a mapping with a ``plugins`` key:

    {"plugins": [{"name": ..., "version": ..., "author": ..., ...}]}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from kimiko.api.deps import get_orchestrator
from kimiko.api.middleware.auth import verify_api_key
from kimiko.core.orchestrator import RequestOrchestrator

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    _auth: dict = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return metadata for every loaded plugin."""
    return {"plugins": orchestrator.plugin_manager.list_plugins()}


@router.get("/{name}")
async def get_plugin(
    name: str,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    _auth: dict = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return metadata for a single loaded plugin."""
    from fastapi import HTTPException, status

    for plugin in orchestrator.plugin_manager.list_plugins():
        if plugin.get("name") == name:
            return plugin
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Plugin '{name}' not found",
    )
