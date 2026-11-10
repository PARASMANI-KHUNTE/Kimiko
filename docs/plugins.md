# 🔌 Developer Guide: Plugins

Kimiko is designed to be extensible. You can add new capabilities without touching the core engine.

## 🏗️ Plugin Structure

Plugins live in `src/kimiko/plugins/installed/`. Each plugin consists of:
1. **The Plugin Class**: Extends `PluginBase` and provides metadata.
2. **Tools**: One or more classes extending `BaseTool`.

### Example Plugin
```python
from kimiko.plugins.base import PluginBase
from kimiko.tools.base import BaseTool

class SampleTool(BaseTool):
    def __init__(self):
        super().__init__(name="my_tool", description="Does something cool")

    async def run(self, **kwargs):
        return "Tool result here"

class MyPlugin(PluginBase):
    name: str = "custom"
    author: str = "DevName"
    
    def get_tools(self):
        return [SampleTool()]
```

---

## 🛡️ Namespacing & Safety

- **Automatic Namespacing**: The Plugin Manager automatically prefixes every tool with the plugin name. If your plugin is named `weather` and your tool is `get_forecast`, the agent sees it as `weather.get_forecast`.
- **Dependency Isolation**: Plugins can bring their own pip dependencies; just ensure they are available in the runtime environment.
- **Lifecycle Hooks**: Use `initialize()` to setup API clients and `shutdown()` to release resources.

---

## 🚀 How to Add a Plugin

1. Create a new `.py` file in `src/kimiko/plugins/installed/`.
2. Implement your logic extending `PluginBase`.
3. Restart the Kimiko API container.
4. The Agent will automatically discover the new tools in its next reasoning loop.
