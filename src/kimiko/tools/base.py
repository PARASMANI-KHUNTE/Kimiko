"""Base tool abstraction for Kimiko AI agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class BaseTool(ABC):
    """Abstract base class for all tools in the Kimiko ecosystem.
    
    Tools define their capabilities, input schemas, and execution logic.
    """

    def __init__(
        self,
        name: str,
        description: str,
        capabilities: List[str] | None = None,
        max_output_tokens: int = 2000,
    ) -> None:
        self.name = name
        self.description = description
        self.capabilities = capabilities or []
        self.max_output_tokens = max_output_tokens

    @property
    @abstractmethod
    def args_schema(self) -> type[BaseModel] | None:
        """Pydantic model for tool input validation."""
        return None

    @abstractmethod
    async def run(self, **kwargs: Any) -> str:
        """Excute the tool logic asynchronously.
        
        Args:
            **kwargs: Tool inputs matching args_schema.
            
        Returns:
            String representation of the tool output (Observation).
        """
        pass

    def to_llm_schema(self) -> Dict[str, Any]:
        """Convert tool definition to standard OpenAI/Ollama tool calling format."""
        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
            },
        }
        
        if self.args_schema:
            schema["function"]["parameters"] = self.args_schema.model_json_schema()
            
        return schema
