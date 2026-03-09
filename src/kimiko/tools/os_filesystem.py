"""OS File System tool for host-level access — communicates with host bridge."""

import httpx
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from kimiko.tools.base import BaseTool

class FileArgs(BaseModel):
    path: str = Field(..., description="The host-level path of the file/directory.")
    content: Optional[str] = Field(None, description="The content to write to the file (for write actions).")

class OSFileSystemTool(BaseTool):
    name: str = "os_filesystem"
    description: str = "Perform file operations (read, write, list) on the host OS. REQUIRES USER APPROVAL FOR WRITES."
    args_schema: type[BaseModel] = FileArgs

    async def execute(self, action: str, path: str, content: Optional[str] = None) -> Any:
        # Communicate with the Host Bridge on 127.0.0.1:8001
        base_url = "http://127.0.0.1:8001/files"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            if action == "list":
                # For now, using terminal 'ls' or 'dir' is easier, but let's implement this later
                # Bridge currently supports basic list if we implement it.
                return "List action in progress..."
            
            elif action == "read":
                # Proxies reading. For now, we can use terminal 'type' or 'cat' as a shortcut
                # but let's prioritize TerminalTool for now since it's more flexible.
                return "Read action in progress..."
            
            elif action == "write":
                resp = await client.post(f"{base_url}/write", json={"path": path, "content": content})
                if resp.status_code == 200:
                    data = resp.json()
                    action_id = data.get("action_id")
                    return f"Action {action_id} sent for user approval. Please check the Kimiko UI."
                return f"Error: {resp.text}"

        return "Action not supported."
 Riverside, CA
