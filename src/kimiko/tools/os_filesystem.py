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
                resp = await client.get(f"http://127.0.0.1:8001/files/list", params={"path": path})
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    return "\n".join([f"[{'DIR' if i['is_dir'] else 'FILE'}] {i['name']}" for i in items])
                return f"Error listing directory: {resp.text}"
            
            elif action == "read":
                resp = await client.get(f"http://127.0.0.1:8001/files/read", params={"path": path})
                if resp.status_code == 200:
                    return resp.json().get("content", "")
                return f"Error reading file: {resp.text}"
            
            elif action == "write":
                resp = await client.post(f"http://127.0.0.1:8001/files/write", json={"path": path, "content": content})
                if resp.status_code == 200:
                    action_id = resp.json().get("action_id")
                    # Poll for completion
                    import asyncio
                    for _ in range(60):
                        await asyncio.sleep(2)
                        check = await client.get("http://127.0.0.1:8001/approval/pending")
                        if not check.json().get("pending"):
                            # Check result
                            res_resp = await client.get(f"http://127.0.0.1:8001/approval/result/{action_id}")
                            if res_resp.status_code == 200:
                                return "File write successful." if res_resp.json().get("success") else "File write denied or failed."
                            return f"Action {action_id} completed."
                    return f"Action {action_id} timed out."
                return f"Error: {resp.text}"

        return "Action not supported."
