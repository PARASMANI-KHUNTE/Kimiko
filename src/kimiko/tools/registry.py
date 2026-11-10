"""Tool registry — manages tool discovery and role-based access control."""

from __future__ import annotations

from typing import Dict, List, Optional, Type

import structlog

from kimiko.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Central registry for all agent tools.
    
    Supports:
    1. Static registration of tool instances
    2. Role-based filtering (Admin vs User vs Guest)
    3. Capability-based discovery
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        # Map tool name to required roles (default: ["user", "admin"])
        self._role_map: Dict[str, List[str]] = {}

    def register(
        self, 
        tool: BaseTool, 
        roles: Optional[List[str]] = None
    ) -> None:
        """Register a tool instance with optional role restrictions."""
        if tool.name in self._tools:
            logger.warning("tool_already_registered", name=tool.name)
            
        self._tools[tool.name] = tool
        self._role_map[tool.name] = roles or ["user", "admin"]
        
        logger.info(
            "tool_registered", 
            name=tool.name, 
            roles=self._role_map[tool.name],
            capabilities=tool.capabilities
        )

    def get_tool(self, name: str, user_role: str = "user") -> Optional[BaseTool]:
        """Fetch a tool by name, verifying user role access."""
        tool = self._tools.get(name)
        if not tool:
            return None
            
        allowed_roles = self._role_map.get(name, [])
        if user_role not in allowed_roles:
            logger.warning(
                "tool_access_denied", 
                tool=name, 
                user_role=user_role, 
                required=allowed_roles
            )
            return None
            
        return tool

    def list_tools(
        self, 
        user_role: str = "user", 
        capability: Optional[str] = None
    ) -> List[BaseTool]:
        """List all tools accessible to a specific role/capability."""
        results = []
        for name, tool in self._tools.items():
            if user_role in self._role_map.get(name, []):
                if not capability or capability in tool.capabilities:
                    results.append(tool)
        return results

    def get_llm_schemas(self, user_role: str = "user") -> List[Dict]:
        """Get tool schemas for LLM system prompt / tool calling."""
        return [t.to_llm_schema() for t in self.list_tools(user_role)]
