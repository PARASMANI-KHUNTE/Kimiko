"""Plugin Manager — dynamically loads and registers external capabilities (Phase 4)."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Dict, List

import structlog

from kimiko.plugins.base import PluginBase
from kimiko.tools.registry import ToolRegistry
from kimiko.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class PluginManager:
    """Discovers, loads, and manages lifecycle of external Kimiko plugins."""

    def __init__(self, registry: ToolRegistry, plugin_dir: str | Path | None = None) -> None:
        self.registry = registry
        if plugin_dir is None:
            # Default to src/kimiko/plugins/installed
            base_path = Path(__file__).resolve().parent
            self.plugin_dir = base_path / "installed"
        else:
            self.plugin_dir = Path(plugin_dir)
            
        self.plugins: Dict[str, PluginBase] = {}
        
        # Ensure directory exists
        self.plugin_dir.mkdir(parents=True, exist_ok=True)

    def load_plugins(self) -> int:
        """Scan the plugin directory and load all valid plugins.
        
        Returns the number of successfully loaded plugins.
        """
        loaded_count = 0
        
        if not self.plugin_dir.exists() or not self.plugin_dir.is_dir():
            logger.warning("plugin_directory_not_found", path=str(self.plugin_dir))
            return 0
            
        logger.info("scanning_for_plugins", path=str(self.plugin_dir))
        
        # Add plugin dir to sys.path temporarily to allow relative imports within plugins
        if str(self.plugin_dir) not in sys.path:
            sys.path.insert(0, str(self.plugin_dir))

        for item in self.plugin_dir.iterdir():
            try:
                if item.is_file() and item.suffix == ".py" and not item.name.startswith("__"):
                    self._load_plugin_file(item)
                    loaded_count += 1
                elif item.is_dir() and (item / "__init__.py").exists():
                    # Support module-directory plugins
                    self._load_plugin_file(item / "__init__.py", module_name=item.name)
                    loaded_count += 1
            except Exception as e:
                logger.error("plugin_scan_failed_entry", path=str(item), error=str(e))
                
        return len(self.plugins)

    def _load_plugin_file(self, file_path: Path, module_name: str | None = None) -> None:
        """Dynamically import a python file and instantiate PluginBase instances."""
        name = module_name or file_path.stem
        
        try:
            spec = importlib.util.spec_from_file_location(name, file_path)
            if not spec or not spec.loader:
                logger.error("plugin_load_failed_no_spec", file=str(file_path))
                return
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            
            # Find PluginBase subclasses
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if inspect.isclass(attr) and issubclass(attr, PluginBase) and attr is not PluginBase:
                    # Instantiate and initialize
                    plugin_instance = attr()
                    
                    try:
                        plugin_instance.initialize()
                        self.plugins[plugin_instance.name] = plugin_instance
                        
                        # Register namespaced tools
                        tools = plugin_instance.get_tools()
                        for tool in tools:
                            # Enforce namespace to prevent core collisions
                            namespaced_name = f"{plugin_instance.name}.{tool.name}"
                            tool.name = namespaced_name
                            self.registry.register(tool)
                            
                        logger.info(
                            "plugin_loaded", 
                            name=plugin_instance.name, 
                            version=plugin_instance.version,
                            tools_registered=len(tools)
                        )
                    except Exception as e:
                        logger.error(
                            "plugin_initialization_failed", 
                            plugin=plugin_instance.name, 
                            error=str(e)
                        )
                        
        except Exception as e:
            logger.error("plugin_import_error", file=str(file_path), error=str(e))

    def list_plugins(self) -> List[dict]:
        """Return metadata for all loaded plugins."""
        return [
            {
                "name": p.name,
                "version": p.version,
                "author": p.author,
                "description": p.description,
                "capabilities": p.capabilities
            }
            for p in self.plugins.values()
        ]
