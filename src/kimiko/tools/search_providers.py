"""Search provider abstraction — decoupled from specific search engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class SearchResult(Dict[str, Any]):
    """Standardized search result format."""
    title: str
    link: str
    snippet: str
    source: str


class SearchProvider(ABC):
    """Abstract base class for search providers (DuckDuckGo, SerpAPI, etc.)."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Perform search and return standardized results."""
        pass


class DuckDuckGoProvider(SearchProvider):
    """Search provider using DuckDuckGo (no API key required)."""

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        from duckduckgo_search import DDGS
        
        try:
            logger.info("ddg_search_start", query=query, max_results=max_results)
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                
            formatted = []
            for r in results:
                formatted.append({
                    "title": r.get("title", ""),
                    "link": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "source": "DuckDuckGo",
                })
            
            logger.info("ddg_search_complete", results_count=len(formatted))
            return formatted
        except Exception as e:
            logger.error("ddg_search_failed", error=str(e))
            return []


class SerpApiProvider(SearchProvider):
    """Search provider using SerpAPI (requires API key)."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        # Implementation placeholder — would use requests to SerpAPI
        logger.warning("serp_api_not_implemented")
        return []
