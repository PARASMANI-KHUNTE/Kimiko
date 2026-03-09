"""Terminal tool for OS Agent — communicates with host bridge."""

import httpx
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from kimiko.tools.base import BaseTool

class TerminalArgs(BaseModel):
    command: str = Field(..., description="The terminal command to execute on the host.")
    cwd: Optional[str] = Field(None, description="The directory to run the command in.")

class TerminalTool(BaseTool):
    name: str = "terminal_run"
    description: str = "Safely execute terminal commands (git, ls, python, etc.) on the host OS. REQUIRES USER APPROVAL."
    args_schema: type[BaseModel] = TerminalArgs

    async def execute(self, command: str, cwd: Optional[str] = None) -> str:
        # Communicate with the Host Bridge (usually http://host.docker.internal:8001 or 127.0.0.1:8001)
        # Assuming Docker-to-Host networking is set up or we're running locally.
        # Since the assistant is on 127.0.0.1:8001, we use that.
        bridge_url = "http://127.0.0.1:8001/terminal/run"
        
        try:
            async with httpx.AsyncClient(timeout=130.0) as client:
                # 1. Propose command
                resp = await client.post(bridge_url, json={"command": command, "cwd": cwd})
                if resp.status_code != 200:
                    return f"Error: Host bridge returned {resp.status_code}"
                
                data = resp.json()
                action_id = data.get("action_id")
                
                # 2. Wait for approval (Polling until confirmed/denied)
                # In a real agentic loop, the LLM waiting might be tricky,
                # but for simplicity, we poll or just inform the user.
                # Let's poll for up to 60 seconds.
                import asyncio
                for _ in range(60):
                    await asyncio.sleep(2)
                    # Check if action is still pending. If not, it means confirmed or denied.
                    # We need a status endpoint.
                    check_resp = await client.get("http://127.0.0.1:8001/approval/pending")
                    pending = check_resp.json().get("pending")
                    if not pending:
                        # Success! The bridge clears pending on confirm/deny.
                        # Now WE need to get the result of the LAST action.
                        return f"Action {action_id} completed or denied by user. Check host for results."
            
            return f"Action {action_id} timed out waiting for user approval."
        except Exception as e:
            return f"Terminal execution failed: {str(e)}"
