"""Core tools for Kimiko AI agents — Calculator, FileSystem, etc."""

from __future__ import annotations

import os
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

from kimiko.tools.base import BaseTool


# ── Calculator ──

class CalculatorInput(BaseModel):
    expression: str = Field(..., description="The mathematical expression to evaluate (e.g., '2 + 2 * 3').")


class CalculatorTool(BaseTool):
    """Simple arithmetic calculator using Python's eval (restricted)."""

    def __init__(self) -> None:
        super().__init__(
            name="calculator",
            description="Evaluate mathematical expressions. Supports +, -, *, /, **, and parentheses.",
            capabilities=["math"],
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return CalculatorInput

    async def run(self, expression: str) -> str:
        """Evaluate the expression in a restricted environment."""
        try:
            # VERY RESTRICTED eval for safety
            # Only allow basic math
            allowed_names = {"abs": abs, "round": round, "max": max, "min": min}
            # Remove any potentially dangerous __builtins__
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return str(result)
        except Exception as e:
            return f"Error: Could not evaluate '{expression}'. {str(e)}"


# ── File System (Read-Only) ──

class FileReadInput(BaseModel):
    path: str = Field(..., description="Relative or absolute path to the file.")


class FileSystemTool(BaseTool):
    """Read-only file system access with path sandboxing."""

    def __init__(self, allowed_paths: List[str]) -> None:
        super().__init__(
            name="read_file",
            description="Read the contents of a file from the local system (Read-Only).",
            capabilities=["file_system"],
        )
        self.allowed_paths = [os.path.realpath(p) for p in allowed_paths]

    @property
    def args_schema(self) -> type[BaseModel]:
        return FileReadInput

    def _is_safe(self, path: str) -> bool:
        real_path = os.path.realpath(path)
        return any(real_path.startswith(allowed) for allowed in self.allowed_paths)

    async def run(self, path: str) -> str:
        if not self._is_safe(path):
            return f"Error: Access denied to path '{path}'. Outside of sandbox."
            
        if not os.path.exists(path):
            return f"Error: File '{path}' does not exist."
            
        if os.path.isdir(path):
            return f"Error: '{path}' is a directory. Use list_dir (not yet implemented)."

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"
