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

        # 1. Screenshot (English & Hindi)
        if any(term in lower for term in [
            "screenshot", "screen capture", "capture screen",
            "screenshot lo", "photo lo", "screen capture karo", "screenshot kheencho"
        ]):
            return PlannedStep(
                description="Capture desktop screenshot / स्क्रीनशॉट लें",
                tool_name="take_screenshot",
                arguments={"include_base64": False}
            )

        # 2. System info / specs / battery (English & Hindi)
        if any(term in lower for term in [
            "system info", "system status", "battery", "cpu", "memory usage",
            "system info batao", "system status batao", "battery kitni hai", "cpu kitna hai", "ram kitni hai"
        ]):
            return PlannedStep(
                description="Query system hardware statistics / सिस्टम जानकारी प्राप्त करें",
                tool_name="get_system_info",
                arguments={"detailed": False}
            )

        # 3. Volume controls (English & Hindi)
        if any(term in lower for term in ["volume up", "increase volume", "volume badhao", "aawaz badhao", "awaz badhao"]):
            return PlannedStep(description="Increase system volume / आवाज़ बढ़ाएं", tool_name="control_system_volume", arguments={"action": "up", "steps": 3})
        if any(term in lower for term in ["volume down", "lower volume", "volume kam karo", "aawaz kam karo", "awaz kam karo"]):
            return PlannedStep(description="Decrease system volume / आवाज़ कम करें", tool_name="control_system_volume", arguments={"action": "down", "steps": 3})
        if any(term in lower for term in ["mute", "mute karo", "aawaz band karo", "awaz band karo"]):
            return PlannedStep(description="Toggle audio mute / म्यूट करें", tool_name="control_system_volume", arguments={"action": "mute", "steps": 1})

        # 4. Lock workstation (English & Hindi)
        if any(term in lower for term in ["lock screen", "lock computer", "lock workstation", "screen lock karo", "computer lock karo", "pc lock karo"]):
            return PlannedStep(description="Lock workstation / कंप्यूटर लॉक करें", tool_name="lock_workstation", arguments={"confirm_lock": True})

        # 5. Open / Launch application (English: "open <app>", Hindi: "<app> kholo" or "kholo <app>")
        # Check Hindi suffix pattern first (e.g. "calculator kholo", "notepad chalao", "youtube open karo")
        hindi_open_suffix = re.match(r"(.+?)\s+(?:kholo|chalao|start karo|open karo|shuru karo)$", lower)
        # English or Hindi prefix pattern (e.g. "open <app>", "kholo <app>", "chalao <app>", "go to <app>")
        open_match = re.match(r"(?:open|launch|start|go to|kholo|chalao)\s+(?:application\s+|app\s+)?(.+)", lower)

        target_candidate = None
        if hindi_open_suffix:
            target_candidate = hindi_open_suffix.group(1).strip().rstrip(".")
        elif open_match:
            target_candidate = open_match.group(1).strip().rstrip(".")

        if target_candidate:
            app_target = target_candidate
            # If youtube
            if "youtube" in app_target:
                return PlannedStep(description="Open YouTube / यूट्यूब खोलें", tool_name="open_browser_url", arguments={"url": "https://www.youtube.com"})
            # If web url or domain
            if app_target.startswith("http") or app_target.endswith(".com") or app_target.endswith(".org") or app_target.endswith(".net"):
                return PlannedStep(description=f"Open URL {app_target}", tool_name="open_browser_url", arguments={"url": app_target})
            # If project
            if "project" in app_target or "workspace" in app_target:
                path = re.sub(r"(?:project|workspace|in vscode|in code)\s*", "", app_target).strip()
                path = path if path else "."
                return PlannedStep(description=f"Open project {path} in VS Code", tool_name="open_project_in_vscode", arguments={"project_path": path})

            return PlannedStep(description=f"Launch application '{app_target}' / '{app_target}' शुरू करें", tool_name="launch_application", arguments={"app_name": app_target})

        # 6. Close / Kill application (English & Hindi: "<app> band karo", "close <app>")
        hindi_close_suffix = re.match(r"(.+?)\s+(?:band karo|close karo|hatao)$", lower)
        close_match = re.match(r"(?:close|kill|terminate|stop|band karo)\s+(?:application\s+|app\s+)?(.+)", lower)
        close_target = None
        if hindi_close_suffix:
            close_target = hindi_close_suffix.group(1).strip()
        elif close_match:
            close_target = close_match.group(1).strip()

        if close_target:
            return PlannedStep(description=f"Close application '{close_target}' / '{close_target}' बंद करें", tool_name="close_application", arguments={"app_name": close_target})

        # 7. Focus window
        focus_match = re.match(r"(?:focus|switch to|bring up)\s+(?:window\s+)?(.+)", lower)
        if focus_match:
            win_target = focus_match.group(1).strip()
            return PlannedStep(description=f"Focus window '{win_target}'", tool_name="focus_application", arguments={"window_title_keyword": win_target})

        # 8. Web search & YouTube play
        youtube_play_match = re.match(r"(?:play|search)\s+(.+?)\s+(?:on\s+youtube|in\s+youtube|youtube\s+par)$", lower)
        hindi_youtube_match = re.match(r"(?:youtube\s+par\s+)?(.+?)\s+(?:chalao|play\s+karo|bajao)$", lower)
        if youtube_play_match:
            song_or_video = youtube_play_match.group(1).strip()
            return PlannedStep(description=f"Play '{song_or_video}' on YouTube", tool_name="web_search", arguments={"query": song_or_video, "engine": "youtube"})
        elif hindi_youtube_match and "youtube" in lower:
            song_or_video = hindi_youtube_match.group(1).replace("youtube par", "").strip()
            return PlannedStep(description=f"Play '{song_or_video}' on YouTube", tool_name="web_search", arguments={"query": song_or_video, "engine": "youtube"})

        search_match = re.match(r"(?:search|google|look up)\s+(?:for\s+)?(.+)", lower)
        if search_match:
            query = search_match.group(1).strip()
            return PlannedStep(description=f"Search Google for '{query}'", tool_name="web_search", arguments={"query": query, "engine": "google"})

        # 9. Browser Tab Controls (English & Hindi)
        if any(term in lower for term in ["new tab", "open tab", "naya tab", "create tab"]):
            return PlannedStep(description="Open new browser tab (Ctrl+T)", tool_name="browser_tab_control", arguments={"action": "new_tab"})
        if any(term in lower for term in ["close tab", "tab band karo", "tab close karo"]):
            return PlannedStep(description="Close current browser tab (Ctrl+W)", tool_name="browser_tab_control", arguments={"action": "close_tab"})
        if any(term in lower for term in ["next tab", "switch tab", "agla tab", "change tab"]):
            return PlannedStep(description="Switch to next browser tab (Ctrl+Tab)", tool_name="browser_tab_control", arguments={"action": "next_tab"})
        if any(term in lower for term in ["prev tab", "previous tab", "pichla tab"]):
            return PlannedStep(description="Switch to previous browser tab (Ctrl+Shift+Tab)", tool_name="browser_tab_control", arguments={"action": "prev_tab"})
        if any(term in lower for term in ["refresh", "reload", "refresh page", "reload karo"]):
            return PlannedStep(description="Refresh current page (Ctrl+R)", tool_name="browser_tab_control", arguments={"action": "refresh"})
        if any(term in lower for term in ["browser back", "go back", "back jao", "piche jao"]):
            return PlannedStep(description="Navigate browser back (Alt+Left)", tool_name="browser_tab_control", arguments={"action": "back"})

        # 10. Browser Scrolling (English & Hindi)
        if any(term in lower for term in ["scroll down", "niche scroll", "page down", "scroll karo"]):
            return PlannedStep(description="Scroll webpage down", tool_name="browser_scroll", arguments={"direction": "down", "amount": 5})
        if any(term in lower for term in ["scroll up", "upar scroll", "page up"]):
            return PlannedStep(description="Scroll webpage up", tool_name="browser_scroll", arguments={"direction": "up", "amount": 5})

        # 11. Keyboard type
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
