"""Plugin Runner — sandboxed execution wrapper for plugin tools (Phase 5).

Wraps plugin tool calls with timeout enforcement and exception isolation
to prevent a single misbehaving plugin from crashing the agent loop.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from kimiko.core.observability import TOOL_EXECUTION_DURATION, AGENT_STEPS_TOTAL
from kimiko.tools.base import BaseTool

logger = structlog.get_logger(__name__)

# Default timeout for plugin tool execution
DEFAULT_PLUGIN_TIMEOUT = 30.0  # seconds


class PluginRunner:
    """Executes plugin tools with timeout and exception isolation.

    Architecture:
        Agent → Tool Executor → PluginRunner → Plugin Tool

    Future: This wrapper can be extended to run plugins in a separate
    process (multiprocessing) or container (Docker/WASM) for full isolation.
    """

    def __init__(self, timeout: float = DEFAULT_PLUGIN_TIMEOUT) -> None:
        self.timeout = timeout

    async def execute(self, tool: BaseTool, **kwargs: Any) -> str:
        """Execute a tool with timeout and exception isolation.

        Args:
            tool: The BaseTool instance to execute.
            **kwargs: Arguments to pass to the tool's run method.

        Returns:
            The string result from the tool, or an error message on failure.
        """
        tool_name = tool.name
        start_time = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                tool.run(**kwargs),
                timeout=self.timeout,
            )

            elapsed = time.perf_counter() - start_time
            TOOL_EXECUTION_DURATION.labels(tool_name=tool_name).observe(elapsed)
            AGENT_STEPS_TOTAL.labels(status="success").inc()

            logger.info(
                "plugin_tool_executed",
                tool=tool_name,
                duration=round(elapsed, 3),
            )
            return result

        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - start_time
            TOOL_EXECUTION_DURATION.labels(tool_name=tool_name).observe(elapsed)
            AGENT_STEPS_TOTAL.labels(status="timeout").inc()

            logger.error(
                "plugin_tool_timeout",
                tool=tool_name,
                timeout=self.timeout,
            )
            return f"[ERROR] Tool '{tool_name}' timed out after {self.timeout}s."

        except Exception as e:
            elapsed = time.perf_counter() - start_time
            TOOL_EXECUTION_DURATION.labels(tool_name=tool_name).observe(elapsed)
            AGENT_STEPS_TOTAL.labels(status="failed").inc()

            logger.error(
                "plugin_tool_error",
                tool=tool_name,
                error=str(e),
                duration=round(elapsed, 3),
            )
            return f"[ERROR] Tool '{tool_name}' failed: {str(e)}"
