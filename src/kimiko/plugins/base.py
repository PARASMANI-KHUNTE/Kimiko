"""Base Plugin Interface — Defines the contract for all external Kimiko capabilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from kimiko.tools.base import BaseTool


class PluginBase(ABC):
    """Abstract base class for all Kimiko plugins.
    
    Plugins are dynamically loaded and injected into the Agent ToolRegistry.
    Tools returned by the plugin will automatically be namespaced (e.g. `plugin_name.tool_name`)
    to prevent collisions with core API tools.
    """
    
    # Required Metadata
    name: str = "base_plugin"
    version: str = "1.0.0"
    author: str = "unknown"
    description: str = "A base plugin"
    capabilities: List[str] = []

    def initialize(self) -> None:
        """Called immediately after the plugin is instantiated."""
        pass
        
    def shutdown(self) -> None:
        """Called when the system unloads the plugin."""
        pass

    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """Return a list of BaseTool instances to register with the Agent."""
        pass
