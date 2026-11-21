"""Core tools for Kimiko AI agents — Calculator, FileSystem, etc."""

from __future__ import annotations

import ast
import operator
import os
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

from kimiko.tools.base import BaseTool


# ── Calculator ──

class CalculatorInput(BaseModel):
    expression: str = Field(..., description="The mathematical expression to evaluate (e.g., '2 + 2 * 3').")


_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}

def _safe_eval_ast(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp):
        left = _safe_eval_ast(node.left)
        right = _safe_eval_ast(node.right)
        op_type = type(node.op)
        if op_type in _SAFE_OPS:
            return _SAFE_OPS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _safe_eval_ast(node.operand)
        op_type = type(node.op)
        if op_type in _SAFE_OPS:
            return _SAFE_OPS[op_type](operand)
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
            args = [_safe_eval_ast(arg) for arg in node.args]
            return _SAFE_FUNCS[node.func.id](*args)
    raise ValueError(f"Unsupported or restricted expression component: {ast.dump(node)}")


class CalculatorTool(BaseTool):
    """Deterministic and safe arithmetic calculator using AST parsing (no eval)."""

    def __init__(self) -> None:
        super().__init__(
            name="calculator",
            description="Evaluate mathematical expressions safely. Supports +, -, *, /, **, and parentheses.",
            capabilities=["math"],
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return CalculatorInput

    async def run(self, expression: str) -> str:
        """Evaluate the expression safely without executing arbitrary Python bytecode."""
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            result = _safe_eval_ast(tree.body)
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
