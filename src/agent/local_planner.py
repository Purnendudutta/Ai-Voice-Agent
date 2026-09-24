"""
Local / Degraded Mode Task Planner & Intent Matcher
Enables the voice agent to understand natural language commands, break requests
into multi-step tasks, execute them with verification, and provide voice response
even when offline or without a Gemini API key.
"""

import re
import shlex
import logging
from typing import Dict, Any, List, Optional, Tuple
from src.tools.registry import tool_registry

logger = logging.getLogger("LocalPlanner")


class PlannedStep:
    def __init__(self, description: str, tool_name: str, arguments: Dict[str, Any]):
        self.description = description
        self.tool_name = tool_name
        self.arguments = arguments


class LocalPlanner:
    """Rule-based intent parser and workflow decomposer for local degraded mode."""

    def __init__(self):
        pass

    def plan_request(self, user_text: str) -> List[PlannedStep]:
        """
        Decomposes natural language commands into a sequence of actionable tool steps.
        Supports compound commands joined by 'and', 'then', or commas.
        """
        clean_text = user_text.strip()
        if not clean_text:
            return []

        # Split multi-step sentences if joined by ' then ' or ' and then '
        sub_commands = re.split(r"\b(?:and\s+then|then|after\s+that)\b", clean_text, flags=re.IGNORECASE)
        # Further split by ' and ' if each side looks like a distinct verb command
        expanded_commands = []
        for cmd in sub_commands:
            parts = re.split(r"\band\b", cmd, flags=re.IGNORECASE)
            # If part starts with a known verb action, keep separate, else combine
            buffer = ""
            for part in parts:
                p = part.strip()
                if self._starts_with_action_verb(p) and buffer:
                    expanded_commands.append(buffer.strip())
                    buffer = p
                else:
                    buffer = f"{buffer} and {p}" if buffer else p
            if buffer:
                expanded_commands.append(buffer.strip())

        steps: List[PlannedStep] = []
        for cmd in expanded_commands:
            step = self._parse_single_command(cmd.strip())
            if step:
                steps.append(step)

        return steps

    def _starts_with_action_verb(self, text: str) -> bool:
        lower = text.lower()
        verbs = ["open", "launch", "start", "close", "kill", "terminate", "focus",
                 "type", "write", "click", "search", "google", "take", "capture",
                 "volume", "mute", "lock", "run", "list", "read", "show"]
        return any(lower.startswith(v) for v in verbs)

    def _parse_single_command(self, text: str) -> Optional[PlannedStep]:
        lower = text.lower().strip()

        # 1. Screenshot
        if any(term in lower for term in ["screenshot", "screen capture", "capture screen"]):
            return PlannedStep(
                description="Capture desktop screenshot",
                tool_name="take_screenshot",
                arguments={"include_base64": False}
            )

        # 2. System info / specs / battery
        if any(term in lower for term in ["system info", "system status", "battery", "cpu", "memory usage"]):
            return PlannedStep(
                description="Query system hardware statistics",
                tool_name="get_system_info",
                arguments={"detailed": False}
            )

        # 3. Volume controls
        if "volume up" in lower or "increase volume" in lower:
            return PlannedStep(description="Increase system volume", tool_name="control_system_volume", arguments={"action": "up", "steps": 3})
        if "volume down" in lower or "lower volume" in lower:
            return PlannedStep(description="Decrease system volume", tool_name="control_system_volume", arguments={"action": "down", "steps": 3})
        if "mute" in lower:
            return PlannedStep(description="Toggle audio mute", tool_name="control_system_volume", arguments={"action": "mute", "steps": 1})

        # 4. Lock workstation
        if "lock screen" in lower or "lock computer" in lower or "lock workstation" in lower:
            return PlannedStep(description="Lock workstation", tool_name="lock_workstation", arguments={"confirm_lock": True})

        # 5. Open / Launch application
        open_match = re.match(r"(?:open|launch|start)\s+(?:application\s+|app\s+)?(.+)", lower)
        if open_match:
            app_target = open_match.group(1).strip()
            # If web url or domain
            if app_target.startswith("http") or app_target.endswith(".com") or app_target.endswith(".org"):
                return PlannedStep(description=f"Open URL {app_target}", tool_name="open_browser_url", arguments={"url": app_target})
            # If project
            if "project" in app_target or "workspace" in app_target:
                path = re.sub(r"(?:project|workspace|in vscode|in code)\s*", "", app_target).strip()
                path = path if path else "."
                return PlannedStep(description=f"Open project {path} in VS Code", tool_name="open_project_in_vscode", arguments={"project_path": path})

            return PlannedStep(description=f"Launch application '{app_target}'", tool_name="launch_application", arguments={"app_name": app_target})

        # 6. Close / Kill application
        close_match = re.match(r"(?:close|kill|terminate|stop)\s+(?:application\s+|app\s+)?(.+)", lower)
        if close_match:
            app_target = close_match.group(1).strip()
            return PlannedStep(description=f"Close application '{app_target}'", tool_name="close_application", arguments={"app_name": app_target})

        # 7. Focus window
        focus_match = re.match(r"(?:focus|switch to|bring up)\s+(?:window\s+)?(.+)", lower)
        if focus_match:
            win_target = focus_match.group(1).strip()
            return PlannedStep(description=f"Focus window '{win_target}'", tool_name="focus_application", arguments={"window_title_keyword": win_target})

        # 8. Web search
        search_match = re.match(r"(?:search|google|look up)\s+(?:for\s+)?(.+)", lower)
        if search_match:
            query = search_match.group(1).strip()
            return PlannedStep(description=f"Search Google for '{query}'", tool_name="web_search", arguments={"query": query})

        # 9. Keyboard type
        type_match = re.match(r"(?:type|write|input)\s+['\"]?(.+?)['\"]?$", lower)
        if type_match:
            text_to_type = type_match.group(1).strip()
            return PlannedStep(description=f"Type text: '{text_to_type}'", tool_name="keyboard_type", arguments={"text": text_to_type, "press_enter": True})

        # 10. List running applications
        if "list apps" in lower or "what is running" in lower or "running applications" in lower:
            return PlannedStep(description="List running GUI applications", tool_name="list_running_applications", arguments={"include_system": False})

        # 11. Run safe command
        run_match = re.match(r"(?:run|execute)\s+(?:command\s+)?['\"]?(.+?)['\"]?$", lower)
        if run_match:
            cmd = run_match.group(1).strip()
            return PlannedStep(description=f"Run command: {cmd}", tool_name="run_safe_terminal_command", arguments={"command": cmd})

        # 12. Read or Write clipboard
        if "read clipboard" in lower or "paste" in lower:
            return PlannedStep(description="Read clipboard content", tool_name="read_clipboard", arguments={})

        return None


local_planner = LocalPlanner()
