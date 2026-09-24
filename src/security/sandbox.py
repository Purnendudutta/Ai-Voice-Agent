"""
Sandbox & Execution Safety Guard Module
"""

import os
import re
import shlex
from pathlib import Path
from typing import Tuple, List, Optional
from src.config import settings


class SandboxViolationError(Exception):
    """Raised when an operation violates security sandbox boundaries."""
    pass


class ExecutionSandbox:
    """Enforces execution boundaries, path traversal protection, and command whitelisting."""

    # Whitelist of safe commands that can be invoked via terminal tool if approved
    SAFE_COMMAND_PREFIXES = [
        "git", "npm", "node", "python", "pytest", "docker", "dir", "echo",
        "type", "find", "code", "cargo", "dotnet", "pip", "cat", "ls", "grep"
    ]

    # Strictly forbidden system-level destruction commands
    PROHIBITED_COMMAND_PATTERNS = [
        r"\bformat\b",
        r"\bdiskpart\b",
        r"\bbcdedit\b",
        r"\breg\s+delete\b",
        r"del\s+/[sS]\s+/[qQ]\s+[cC]:",
        r"rmdir\s+/[sS]\s+/[qQ]\s+[cC]:",
        r"shutdown\s+/[sS]",
        r"powershell.*remove-item.*-recurse.*[cC]:\\",
        r":\(\)\s*\{\s*:\|:&\s*\};:",  # Fork bomb
        r">\s*\\\\.\\",                 # Raw disk device write
    ]

    @classmethod
    def validate_command(cls, command: str) -> Tuple[bool, str]:
        """
        Validates whether a shell command is permissible.
        Returns (is_valid, reason).
        """
        clean_cmd = command.strip()
        if not clean_cmd:
            return False, "Command cannot be empty."

        # Check prohibited destructive patterns
        for pattern in cls.PROHIBITED_COMMAND_PATTERNS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                return False, f"Command contains prohibited destructive pattern matching '{pattern}'."

        # Check against configured prohibited commands
        for forbidden in settings.prohibited_commands:
            if forbidden.lower() in clean_cmd.lower():
                return False, f"Command contains forbidden keyword '{forbidden}'."

        # Parse command binary
        try:
            parts = shlex.split(clean_cmd, posix=False)
            if not parts:
                return False, "Failed to parse command arguments."
            binary = os.path.basename(parts[0]).lower().replace(".exe", "").replace(".cmd", "").replace(".bat", "")

            # Check if binary is in safe prefix list
            if binary not in [p.lower() for p in cls.SAFE_COMMAND_PREFIXES]:
                return False, f"Binary '{binary}' is not in the approved safe tool list."

        except Exception as e:
            return False, f"Command syntax parsing error: {e}"

        return True, "Command passed sandbox validation."

    @classmethod
    def sanitize_path(cls, path_str: str, base_allowed_dir: Optional[Path] = None) -> Path:
        """
        Validates that a path is safe and does not traverse restricted system locations.
        """
        resolved = Path(path_str).resolve()

        # Prohibit root windows directories directly
        restricted_roots = ["C:\\Windows", "C:\\Windows\\System32", "C:\\Recovery"]
        for restricted in restricted_roots:
            try:
                if resolved == Path(restricted) or Path(restricted) in resolved.parents:
                    raise SandboxViolationError(f"Access to sensitive system path '{restricted}' is prohibited.")
            except Exception:
                pass

        if base_allowed_dir:
            base_resolved = base_allowed_dir.resolve()
            if base_resolved not in resolved.parents and resolved != base_resolved:
                raise SandboxViolationError(f"Path '{path_str}' attempts to escape base directory '{base_allowed_dir}'.")

        return resolved


execution_sandbox = ExecutionSandbox()
