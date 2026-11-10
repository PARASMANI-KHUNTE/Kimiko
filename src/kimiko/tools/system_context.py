"""System Context tool for OS Agent — retrieves screen OCR and UI tree."""

import httpx
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from kimiko.tools.base import BaseTool

class ContextArgs(BaseModel):
    detailed: bool = Field(True, description="Whether to include full OCR and UI element tree.")

class SystemContextTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="get_system_context",
            description="Get the current screen state, including OCR text, active window, and UI elements. Use this to 'see' what is happening on the screen.",
            capabilities=["os_context"],
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return ContextArgs

    async def run(self, detailed: bool = True) -> Dict[str, Any]:
        from kimiko.config import get_settings
        os_bridge_url = get_settings().os_bridge_url
        url = f"{os_bridge_url}/context/full" if detailed else f"{os_bridge_url}/context"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"Bridge returned {resp.status_code}"}
        except Exception as e:
            return {"error": f"Failed to reach system bridge: {str(e)}"}
