"""System Context tool for OS Agent — retrieves screen OCR and UI tree."""

import httpx
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from kimiko.tools.base import BaseTool

class ContextArgs(BaseModel):
    detailed: bool = Field(True, description="Whether to include full OCR and UI element tree.")

class SystemContextTool(BaseTool):
    name: str = "get_system_context"
    description: str = "Get the current screen state, including OCR text, active window, and UI elements. Use this to 'see' what is happening on the screen."
    args_schema: type[BaseModel] = ContextArgs

    async def execute(self, detailed: bool = True) -> Dict[str, Any]:
        # Communicate with the Host Bridge on 127.0.0.1:8001
        url = "http://127.0.0.1:8001/context/full" if detailed else "http://127.0.0.1:8001/context"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"Bridge returned {resp.status_code}"}
        except Exception as e:
            return {"error": f"Failed to reach system bridge: {str(e)}"}
