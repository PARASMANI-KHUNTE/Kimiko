"""App Automation Tool — allows Kimiko to interact with applications via the OS Bridge."""

import httpx
from pydantic import BaseModel, Field
from typing import Dict, Any
from kimiko.tools.base import BaseTool

class AutomationArgs(BaseModel):
    action: str = Field(..., description="The automation action to perform: 'app_open', 'app_focus', 'app_type', 'app_click'.")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the action. Example for app_open: {'path': 'notepad.exe', 'args': ''}. For app_type: {'keys': 'hello world'}. For app_click: {'title': 'Window Title', 'title_re': 'Button Text'}.")

class AppAutomationTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="app_automation",
            description="Perform UI automation on Windows (open apps, type text, click elements, focus windows). REQUIRES USER APPROVAL.",
            capabilities=["os_automation"],
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AutomationArgs

    async def run(self, action: str, params: Dict[str, Any]) -> str:
        # Communicate with the Host Bridge on 127.0.0.1:8001
        bridge_url = "http://127.0.0.1:8001/automation/run"
        
        try:
            async with httpx.AsyncClient(timeout=130.0) as client:
                # 1. Propose action
                resp = await client.post(bridge_url, json={"action": action, "params": params})
                if resp.status_code != 200:
                    return f"Error: Host bridge returned {resp.status_code}"
                
                data = resp.json()
                action_id = data.get("action_id")
                
                # 2. Wait for approval
                import asyncio
                for _ in range(60):
                    await asyncio.sleep(2)
                    check_resp = await client.get("http://127.0.0.1:8001/approval/pending")
                    pending = check_resp.json().get("pending")
                    if not pending:
                        # Once cleared, the action was either executed or denied.
                        return f"Action {action_id} completed or denied by user. Observe the screen or UI to confirm results."
            
            return f"Action {action_id} timed out waiting for user approval."
        except Exception as e:
            return f"Automation execution failed: {str(e)}"

    async def execute(self, action: str, params: Dict[str, Any]) -> str:
        """Backward-compatible alias for legacy call sites."""
        return await self.run(action=action, params=params)
