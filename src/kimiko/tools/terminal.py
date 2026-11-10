"""Terminal tool for OS Agent — communicates with host bridge."""

import httpx
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from kimiko.tools.base import BaseTool

class TerminalArgs(BaseModel):
    command: str = Field(..., description="The terminal command to execute on the host.")
    cwd: Optional[str] = Field(None, description="The directory to run the command in.")

class TerminalTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="terminal_run",
            description="Safely execute terminal commands (git, ls, python, etc.) on the host OS. REQUIRES USER APPROVAL.",
            capabilities=["os_terminal"],
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return TerminalArgs

    async def run(self, command: str, cwd: Optional[str] = None) -> str:
        from kimiko.config import get_settings
        os_bridge_url = get_settings().os_bridge_url
        bridge_url = f"{os_bridge_url}/terminal/run"
        
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
                    check_resp = await client.get(f"{os_bridge_url}/approval/pending")
                    pending = check_resp.json().get("pending")
                    if not pending:
                        # Success! Now retrieve the result
                        result_resp = await client.get(f"{os_bridge_url}/approval/result/{action_id}")
                        if result_resp.status_code == 200:
                            res = result_resp.json()
                            return f"STDOUT:\n{res.get('stdout')}\nSTDERR:\n{res.get('stderr')}\nExit Code: {res.get('exit_code')}"
                        return f"Action {action_id} completed, but result could not be retrieved."
            
            return f"Action {action_id} timed out waiting for user approval."
        except Exception as e:
            return f"Terminal execution failed: {str(e)}"
