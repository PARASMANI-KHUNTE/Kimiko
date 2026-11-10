"""Tool execution engine — handles sandboxing, validation, and async execution."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Type

import structlog
from pydantic import ValidationError

from kimiko.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""
    pass


class ToolExecutor:
    """Securely executes tools with sandboxing and validation."""

    def __init__(
        self,
        allowed_paths: List[str] | None = None,
        max_output_tokens: int = 4000,
        timeout: float = 30.0,
    ) -> None:
        # Resolve allowed paths to absolute real paths
        self.allowed_paths = [
            os.path.realpath(p) for r in (allowed_paths or [])
            if os.path.exists(r)
        ]
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout

    async def execute(self, tool: BaseTool, **kwargs: Any) -> str:
        """Execute a tool with safety checks.
        
        1. Validate inputs via tool schema
        2. Enforce timeouts
        3. Catch and log exceptions
        4. Truncate output if necessary
        """
        tool_name = tool.name
        
        # 1. Validation
        if tool.args_schema:
            try:
                # Validation only, we pass raw kwargs to run
                tool.args_schema(**kwargs)
            except ValidationError as e:
                logger.warning("tool_validation_failed", tool=tool_name, error=str(e))
                return f"Error: Invalid arguments for {tool_name}. {str(e)}"

        # 2. Execution with timeout
        start_time = time.time()
        try:
            logger.info("tool_execution_start", tool=tool_name, inputs=kwargs)
            
            async with asyncio.timeout(self.timeout):
                observation = await tool.run(**kwargs)
                
            duration = time.time() - start_time
            
            # 3. Output Truncation
            if len(observation) > self.max_output_tokens * 4: # Char-based approx
                observation = observation[:self.max_output_tokens * 4] + "... [Output Truncated]"
                
            logger.info(
                "tool_execution_complete",
                tool=tool_name,
                duration=f"{duration:.2f}s",
                output_preview=observation[:100]
            )
            return observation

        except asyncio.TimeoutError:
            logger.error("tool_timeout", tool=tool_name, timeout=self.timeout)
            return f"Error: Tool {tool_name} timed out after {self.timeout}s."
            
        except Exception as e:
            logger.error("tool_execution_failed", tool=tool_name, error=str(e))
            return f"Error executing {tool_name}: {str(e)}"

    def is_path_safe(self, path: str) -> bool:
        """Security helper: verify if a file path is within allowed sandboxed dirs."""
        if not self.allowed_paths:
            return False
            
        real_path = os.path.realpath(path)
        for allowed in self.allowed_paths:
            if real_path.startswith(allowed):
                return True
        return False
