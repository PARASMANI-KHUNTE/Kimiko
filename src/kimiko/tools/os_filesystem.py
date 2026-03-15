"""OS File System tool for host-level access — communicates with host bridge."""

import httpx
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from kimiko.tools.base import BaseTool

class FileArgs(BaseModel):
    path: str = Field(..., description="The host-level path of the file/directory.")
    content: Optional[str] = Field(None, description="The content to write to the file (for write actions).")

class OSFileSystem:
    """Utility class for host-level file operations used by the bridge."""
    @staticmethod
    def write_file(path: str, content: str) -> bool:
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Error writing file: {e}")
            return False
import os

class OSFileSystemTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="os_filesystem",
            description="Perform file operations (read, write, list) on the host OS. REQUIRES USER APPROVAL FOR WRITES.",
            capabilities=["os_filesystem"],
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return FileArgs

    async def run(self, action: str, path: str, content: Optional[str] = None) -> Any:
        from kimiko.config import get_settings
        os_bridge_url = get_settings().os_bridge_url
        base_url = f"{os_bridge_url}/files"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            if action == "list":
                resp = await client.get(f"{base_url}/list", params={"path": path})
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    return "\n".join([f"[{'DIR' if i['is_dir'] else 'FILE'}] {i['name']}" for i in items])
                return f"Error listing directory: {resp.text}"
            
            elif action == "read":
                resp = await client.get(f"{base_url}/read", params={"path": path})
                if resp.status_code == 200:
                    return resp.json().get("content", "")
                return f"Error reading file: {resp.text}"
            
            elif action == "write":
                resp = await client.post(f"{base_url}/write", json={"path": path, "content": content})
                if resp.status_code == 200:
                    action_id = resp.json().get("action_id")
                    # Poll for completion
                    import asyncio
                    for _ in range(60):
                        await asyncio.sleep(2)
                        check = await client.get(f"{os_bridge_url}/approval/pending")
                        if not check.json().get("pending"):
                            # Check result
                            res_resp = await client.get(f"{os_bridge_url}/approval/result/{action_id}")
                            if res_resp.status_code == 200:
                                return "File write successful." if res_resp.json().get("success") else "File write denied or failed."
                            return f"Action {action_id} completed."
                    return f"Action {action_id} timed out."
                return f"Error: {resp.text}"

        return "Action not supported."
