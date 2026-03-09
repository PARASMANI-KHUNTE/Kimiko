"""Automation Executor — controls Windows applications via pywinauto."""

import os
import time
import structlog
from typing import Dict, Any, Optional

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    Application, Desktop, send_keys = None, None, None

logger = structlog.get_logger(__name__)


class AutomationExecutor:
    """Safely executes UI automation tasks on Windows."""

    def __init__(self):
        self.app = None
        if not Application:
            logger.warning("pywinauto_not_installed", os="windows")

    def execute(self, action: str, params: Dict[str, Any]) -> str:
        """Execute an automation command."""
        if not Application:
            return "Error: pywinauto is not supported or installed in this environment."

        try:
            if action == "app_open":
                return self._app_open(params.get("path", ""), params.get("args", ""))
            elif action == "app_focus":
                return self._app_focus(params.get("title", ""))
            elif action == "app_type":
                return self._app_type(params.get("keys", ""))
            elif action == "app_click":
                return self._app_click(params.get("title", ""), params.get("control_type", ""), params.get("title_re", ""))
            else:
                return f"Error: Unsupported automation action '{action}'"
        except Exception as e:
            logger.exception("automation_failed", action=action, error=str(e))
            return f"Error executing {action}: {str(e)}"

    def _app_open(self, path: str, args: str) -> str:
        """Open an executable."""
        if not path:
            return "Error: App path is required."
        
        # We don't connect immediately because it might take time to load
        if args:
            Application(backend="uia").start(f'"{path}" {args}')
        else:
            Application(backend="uia").start(path)
        
        # Small delay to let the app window initialize
        time.sleep(2)
        return f"Successfully started '{path}'."

    def _app_focus(self, title: str) -> str:
        """Focus an application window by title."""
        if not title:
            return "Error: Window title is required."
        
        desktop = Desktop(backend="uia")
        # Find window containing the title (case insensitive regex roughly)
        windows = desktop.windows(title_re=f".*{title}.*", visible_only=True)
        
        if not windows:
            return f"Error: No visible window found matching '{title}'."
            
        win = windows[0]
        win.set_focus()
        return f"Successfully focused window '{win.window_text()}'."

    def _app_type(self, keys: str) -> str:
        """Type keys using pywinauto keyboard module (active window)."""
        if not keys:
            return "Error: Keys are required."
        
        # pywinauto uses Special keys like {ENTER}, {TAB}.
        send_keys(keys, with_spaces=True)
        return f"Successfully typed '{keys}' into the active window."

    def _app_click(self, title: str, control_type: str = "", title_re: str = "") -> str:
        """Click a UI element within a specified window."""
        if not title:
            return "Error: Parent window title is required for targeting."
            
        desktop = Desktop(backend="uia")
        windows = desktop.windows(title_re=f".*{title}.*", visible_only=True)
        
        if not windows:
            return f"Error: Target window matching '{title}' not found."
            
        win = windows[0]
        win.set_focus()
        
        # Attempt to click based on element title/regex and control type
        try:
            if title_re and control_type:
                elem = win.child_window(title_re=title_re, control_type=control_type)
            elif title_re:
                elem = win.child_window(title_re=title_re)
            elif control_type:
                elem = win.child_window(control_type=control_type)
            else:
                return "Error: Must provide either control_type or element title_re to click."
                
            elem.click_input()
            return f"Successfully clicked element in '{win.window_text()}'."
        except Exception as e:
            return f"Error finding or clicking element: {str(e)}"
