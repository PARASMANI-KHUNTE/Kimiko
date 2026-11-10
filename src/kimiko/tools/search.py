"""Web search tool for Kimiko AI agents."""

from __future__ import annotations

from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

from kimiko.tools.base import BaseTool
from kimiko.tools.search_providers import SearchProvider, DuckDuckGoProvider


class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query to look up on the internet.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of search results to return.")


class WebSearchTool(BaseTool):
    """General internet search tool with provider abstraction."""

    def __init__(self, provider: Optional[SearchProvider] = None) -> None:
        super().__init__(
            name="web_search",
            description="Search the internet for real-time information, news, and technical documentation.",
            capabilities=["internet_access"],
        )
        self.provider = provider or DuckDuckGoProvider()

    @property
    def args_schema(self) -> type[BaseModel]:
        return WebSearchInput

    async def run(self, query: str, max_results: int = 5) -> str:
        """Execute search using the configured provider."""
        results = await self.provider.search(query, max_results=max_results)
        
        if not results:
            return f"No search results found for '{query}'."
            
        formatted = [f"Search results for: {query}\n"]
        for i, res in enumerate(results, 1):
            formatted.append(
                f"[{i}] {res['title']}\n"
                f"URL: {res['link']}\n"
                f"Snippet: {res['snippet']}\n"
            )
            
        return "\n".join(formatted)
