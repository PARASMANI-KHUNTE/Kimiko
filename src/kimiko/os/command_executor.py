"""Kimiko Command Executor (Safety Layer).

Handles:
  - Whitelisted terminal execution
  - Manual approval flow
  - Error reporting
"""

import subprocess
import shlex
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Strictly whitelisted commands
ALLOWED_BASE_COMMANDS = {
    "git", "python", "pip", "npm", "ls", "dir", "cat", "echo", "mkdir", "cd", 
    "ipconfig", "systeminfo", "tasklist", "ping", "tree", "type", "where"
}

# Dangerous patterns to block even if base is allowed
BLOCKED_PATTERNS = ["rm -rf", "format", "del /s", "shutdown", "wget", "curl"]

class CommandExecutor:
    """Safely executes whitelisted terminal commands on the host."""

    @staticmethod
    def is_safe(command: str) -> Tuple[bool, str]:
        """Check if a command is in the whitelist and doesn't contain dangerous patterns."""
        cmd_parts = shlex.split(command)
        if not cmd_parts:
            return False, "Empty command"

        base_cmd = cmd_parts[0].lower()
        if base_cmd not in ALLOWED_BASE_COMMANDS:
            return False, f"Command '{base_cmd}' is not in the whitelist."

        for pattern in BLOCKED_PATTERNS:
            if pattern in command.lower():
                return False, f"Command contains forbidden pattern: '{pattern}'"

        return True, ""

    @staticmethod
    def execute(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Execute a command and return stdout/stderr/exit_code."""
        is_safe, reason = CommandExecutor.is_safe(command)
        if not is_safe:
            return {
                "success": False,
                "error": f"Safety Violation: {reason}",
                "stdout": "",
                "stderr": reason,
                "exit_code": 1
            }

        try:
            # Use shell=True cautiouslly on Windows for 'dir', 'type', etc.
            # but using subprocess.run with list is safer for most.
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30 # 30s timeout for safety
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Execution timed out (30s)",
                "stdout": "",
                "stderr": "Timeout",
                "exit_code": 124
            }
        except Exception as e:
            logger.error(f"Execution Error: {e}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1
            }

if __name__ == "__main__":
    # Test
    print("Testing Command Executor...")
    print(CommandExecutor.execute("ls"))
    print(CommandExecutor.execute("rm -rf /")) # Should fail
