"""Example Weather Plugin — demonstrating dynamic tool loading via PluginBase."""

from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

from kimiko.plugins.base import PluginBase
from kimiko.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class WeatherArgs(BaseModel):
    """Input schema for the weather tool."""
    location: str = Field(description="The city and state/country, e.g. 'San Francisco, CA'")


class WeatherTool(BaseTool):
    """Retrieves current weather for a location (mock implementation)."""

    def __init__(self) -> None:
        super().__init__(
            name="get_current",
            description="Get the current weather conditions for a specified city or location.",
        )

    @property
    def args_schema(self) -> type[BaseModel] | None:
        return WeatherArgs

    async def run(self, **kwargs: Any) -> str:
        location = kwargs.get("location", "Unknown")
        logger.info("plugin_weather_request", location=location)

        loc_lower = location.lower()
        if "san francisco" in loc_lower:
            return f"The current weather in {location} is 58°F (14°C) with fog and light wind."
        elif "tokyo" in loc_lower:
            return f"The current weather in {location} is 72°F (22°C), partly cloudy."
        elif "london" in loc_lower:
            return f"The current weather in {location} is 50°F (10°C) with steady rain."

        return f"The current weather in {location} is 68°F (20°C) and sunny."


class WeatherPlugin(PluginBase):
    """A reference plugin providing weather capabilities to the Agent."""

    name: str = "weather"
    version: str = "1.0.0"
    author: str = "KimikoCore"
    description: str = "Provides real-time weather observation capabilities."
    capabilities: List[str] = ["weather", "environmental"]

    def initialize(self) -> None:
        logger.info("weather_plugin_initialized")

    def get_tools(self) -> List[BaseTool]:
        return [WeatherTool()]
