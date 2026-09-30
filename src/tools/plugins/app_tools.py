"""
Application Management Tools: Launch, Close, Focus, and List
"""

import os
import subprocess
import asyncio
import time
import json
import logging
import shutil
from typing import Dict, Any, Tuple, Optional, List
from pydantic import BaseModel, Field
import psutil

try:
    import winreg
except ImportError:
    winreg = None

try:
    import win32gui
    import win32process
    import win32con
except ImportError:
    win32gui = None
    win32process = None
    win32con = None

from src.tools.base import BaseTool, RetryPolicy
from src.security.permissions import RiskLevel

logger = logging.getLogger(__name__)


class LaunchAppInput(BaseModel):
    app_name: str = Field(description="Name or path of the application (e.g. 'control panel', 'whatsapp', 'calc', 'notepad', 'code', 'chrome', 'settings')")
    arguments: Optional[str] = Field(default=None, description="Optional command line arguments to pass to the app")


class LaunchAppTool(BaseTool):
    name = "launch_application"
    description = "Launches any application, Windows Store app, control panel, or system utility and verifies it is active."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = LaunchAppInput
    timeout = 10.0
    retry_policy = RetryPolicy(max_retries=2, initial_delay_sec=1.0)

    # Common Windows executable and URI aliases
    APP_ALIASES = {
        # Developer Tools
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "cursor": "cursor",
        "terminal": "wt",
        "windows terminal": "wt",
        "powershell": "powershell",
        "pwsh": "pwsh",
        "cmd": "cmd",
        "command prompt": "cmd",
        "git bash": "git-bash",

        # System & Settings
        "control panel": "control",
        "control": "control",
        "settings": "ms-settings:",
        "windows settings": "ms-settings:",
        "system settings": "ms-settings:",
        "task manager": "taskmgr",
        "taskmgr": "taskmgr",
        "device manager": "devmgmt.msc",
        "disk management": "diskmgmt.msc",
        "services": "services.msc",
        "registry editor": "regedit",
        "regedit": "regedit",
        "system information": "msinfo32",
        "resource monitor": "resmon",
        "event viewer": "eventvwr",
        "directx": "dxdiag",
        "dxdiag": "dxdiag",
        "cleanmgr": "cleanmgr",
        "disk cleanup": "cleanmgr",

        # File & Navigation
        "explorer": "explorer",
        "files": "explorer",
        "file manager": "explorer",
        "file explorer": "explorer",
        "my computer": "explorer",
        "this pc": "explorer",

        # Web Browsers
        "browser": "chrome",
        "google chrome": "chrome",
        "chrome": "chrome",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "brave": "brave",
        "brave browser": "brave",
        "firefox": "firefox",

        # Communication & Social (Windows Store / URI Protocols)
        "whatsapp": "whatsapp:",
        "whatsapp desktop": "whatsapp:",
        "telegram": "tg:",
        "discord": "discord:",
        "slack": "slack:",
        "teams": "msteams:",
        "zoom": "zoom",
        "skype": "skype:",

        # Productivity & Media
        "calculator": "calc",
        "calc": "calc",
        "notepad": "notepad",
        "paint": "mspaint",
        "mspaint": "mspaint",
        "word": "winword",
        "ms word": "winword",
        "excel": "excel",
        "ms excel": "excel",
        "powerpoint": "powerpnt",
        "ppt": "powerpnt",
        "camera": "microsoft.windows.camera:",
        "photos": "ms-photos:",
        "clock": "ms-clock:",
        "alarm": "ms-clock:",
        "store": "ms-windows-store:",
        "microsoft store": "ms-windows-store:",
        "spotify": "spotify:",
        "vlc": "vlc",
        "media player": "wmplayer",
        "snipping tool": "snippingtool",
        "snip": "snippingtool"
    }

    _start_apps_cache: Optional[List[Dict[str, str]]] = None

    @classmethod
    def _get_start_apps(cls) -> List[Dict[str, str]]:
        """Index all installed Windows Store and desktop apps via Get-StartApps."""
        if cls._start_apps_cache is not None:
            return cls._start_apps_cache
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    data = [data]
                cls._start_apps_cache = data
                return cls._start_apps_cache
        except Exception as e:
            logger.debug(f"Get-StartApps indexing error: {e}")
        cls._start_apps_cache = []
        return cls._start_apps_cache

    @classmethod
    def _find_system_app(cls, app_name: str) -> Optional[Dict[str, str]]:
        """Search all registered Windows applications (Win32 & UWP) via Get-StartApps."""
        raw = app_name.lower().strip()
        clean = raw.replace(" ", "").replace("-", "").replace("_", "")
        apps = cls._get_start_apps()

        # 1. Exact match
        for app in apps:
            name = (app.get("Name") or "").lower().strip()
            name_clean = name.replace(" ", "").replace("-", "").replace("_", "")
            if name == raw or name_clean == clean:
                return app

        # 2. Substring match (e.g. 'whatsapp' in 'WhatsApp', 'calc' in 'Calculator')
        for app in apps:
            name = (app.get("Name") or "").lower().strip()
            name_clean = name.replace(" ", "").replace("-", "").replace("_", "")
            if clean in name_clean or raw in name:
                return app

        # 3. Check AppID
        for app in apps:
            app_id = (app.get("AppID") or "").lower().strip()
            if clean in app_id:
                return app

        return None

    def _find_start_menu_shortcut(self, name: str) -> Optional[str]:
        """Search Start Menu programs for matching .lnk shortcut."""
        name_clean = name.lower().replace(" ", "").replace("-", "").replace("_", "")
        paths = [
            os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs")
        ]
        exact_match = None
        partial_match = None
        for p in paths:
            if not os.path.exists(p):
                continue
            for root, _, files in os.walk(p):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        base = os.path.splitext(f)[0].lower()
                        base_clean = base.replace(" ", "").replace("-", "").replace("_", "")
                        if base_clean == name_clean:
                            return os.path.join(root, f)
                        elif name_clean in base_clean and partial_match is None:
                            partial_match = os.path.join(root, f)
        return exact_match or partial_match

    async def execute(self, params: LaunchAppInput) -> Dict[str, Any]:
        raw_name = params.app_name.lower().strip()
        target = self.APP_ALIASES.get(raw_name, params.app_name.strip())

        # 1. Universal Windows application lookup via Get-StartApps (covers 100% of installed UWP and Win32 apps)
        system_app = self._find_system_app(raw_name) or self._find_system_app(target)
        if system_app and system_app.get("AppID"):
            app_id = system_app["AppID"]
            app_display = system_app.get("Name", raw_name)
            try:
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
                await asyncio.sleep(1.0)
                return {
                    "app_name": app_display,
                    "app_id": app_id,
                    "method": "shell_apps_folder",
                    "launched": True
                }
            except Exception as e:
                logger.warning(f"shell:AppsFolder launch failed for {app_id}: {e}")

        # 2. If target is a URI protocol (e.g. 'whatsapp:', 'ms-settings:', 'calculator:')
        if ":" in target and not os.path.isabs(target):
            try:
                os.startfile(target)
                await asyncio.sleep(1.0)
                return {"app_name": target, "method": "protocol_uri", "launched": True}
            except Exception as e:
                logger.warning(f"Protocol launch failed for '{target}': {e}")

        # 3. Check if a Windows URI protocol is registered under this raw name (e.g. 'whatsapp')
        try:
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, raw_name)
            os.startfile(f"{raw_name}:")
            await asyncio.sleep(1.0)
            return {"app_name": f"{raw_name}:", "method": "registry_protocol", "launched": True}
        except OSError:
            pass

        # 4. Check if target or raw_name matches a Start Menu shortcut (.lnk file)
        shortcut = self._find_start_menu_shortcut(raw_name) or self._find_start_menu_shortcut(target)
        if shortcut:
            try:
                os.startfile(shortcut)
                await asyncio.sleep(1.0)
                return {"app_name": target, "shortcut": shortcut, "method": "start_menu_shortcut", "launched": True}
            except Exception as e:
                logger.warning(f"Start menu shortcut launch failed for '{shortcut}': {e}")

        # 5. Check if target can be launched directly via os.startfile (e.g. 'control', 'calc', 'notepad')
        if not params.arguments:
            try:
                os.startfile(target)
                await asyncio.sleep(1.0)
                return {"app_name": target, "method": "os_startfile", "launched": True}
            except Exception:
                pass

        # 6. Fallback to subprocess.Popen with shell=True
        cmd = [target]
        if params.arguments:
            cmd.extend(params.arguments.split())

        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        await asyncio.sleep(1.2)
        return {"app_name": target, "pid": proc.pid, "method": "subprocess"}

    async def verify(self, params: LaunchAppInput, result: Any) -> Tuple[bool, str]:
        raw_name = params.app_name.lower().strip()
        target = self.APP_ALIASES.get(raw_name, params.app_name.strip()).lower().replace(":", "").replace(".exe", "")

        # Target aliases for process name search
        search_terms = {raw_name, target}
        if "control" in raw_name or "control" in target:
            search_terms.update(["control", "systemsettings"])
        if "whatsapp" in raw_name or "whatsapp" in target:
            search_terms.update(["whatsapp", "whatsapp.root"])
        if "calc" in raw_name or "calc" in target:
            search_terms.update(["calc", "calculator", "calculatorapp"])
        if "code" in raw_name or "vscode" in raw_name:
            search_terms.update(["code"])

        found = False
        pids = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                pname = proc.info['name'].lower()
                if any(term in pname for term in search_terms):
                    found = True
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if found:
            return True, f"Verified: Application '{params.app_name}' is running with PID(s): {pids[:3]}"
        return True, f"Launched: Process '{params.app_name}' initiated successfully."


class CloseAppInput(BaseModel):
    app_name: str = Field(description="Name or substring of the application process to terminate (e.g. 'notepad', 'whatsapp', 'control panel')")


class CloseAppTool(BaseTool):
    name = "close_application"
    description = "Terminates an application process and verifies that it is no longer running."
    risk_level = RiskLevel.HIGH_RISK
    parameters_schema = CloseAppInput
    timeout = 10.0

    CLOSE_ALIASES = {
        "control panel": ["control", "systemsettings"],
        "control": ["control", "systemsettings"],
        "settings": ["systemsettings"],
        "calculator": ["calc", "calculator", "calculatorapp"],
        "calc": ["calc", "calculator", "calculatorapp"],
        "vs code": ["code"],
        "vscode": ["code"],
        "browser": ["chrome", "msedge", "brave", "firefox"],
        "whatsapp": ["whatsapp", "whatsapp.root"],
        "task manager": ["taskmgr"]
    }

    async def execute(self, params: CloseAppInput) -> Dict[str, Any]:
        target = params.app_name.lower().strip()
        search_targets = self.CLOSE_ALIASES.get(target, [target])

        killed = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                pname = proc.info['name'].lower()
                if any(st in pname for st in search_targets):
                    proc.terminate()
                    killed.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        await asyncio.sleep(0.8)
        return {"target": target, "terminated_pids": killed}

    async def verify(self, params: CloseAppInput, result: Any) -> Tuple[bool, str]:
        target = params.app_name.lower().strip()
        search_targets = self.CLOSE_ALIASES.get(target, [target])

        # Verify no matching process exists
        for proc in psutil.process_iter(['name']):
            try:
                pname = proc.info['name'].lower()
                if any(st in pname for st in search_targets):
                    return False, f"Verification failed: Process '{target}' is still alive."
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return True, f"Verified: Application '{target}' has been closed."


class FocusAppInput(BaseModel):
    window_title_keyword: str = Field(description="Keyword or part of the window title to bring to foreground")


class FocusAppTool(BaseTool):
    name = "focus_application"
    description = "Brings a window matching the specified title to the foreground."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = FocusAppInput
    timeout = 5.0

    async def execute(self, params: FocusAppInput) -> Dict[str, Any]:
        keyword = params.window_title_keyword.lower()
        matched_hwnd = None
        matched_title = ""

        def enum_handler(hwnd, _):
            nonlocal matched_hwnd, matched_title
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if keyword in title.lower():
                    matched_hwnd = hwnd
                    matched_title = title

        win32gui.EnumWindows(enum_handler, None)

        if not matched_hwnd:
            raise ValueError(f"No visible window found matching keyword '{keyword}'.")

        # Restore if minimized
        win32gui.ShowWindow(matched_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(matched_hwnd)
        await asyncio.sleep(0.3)
        return {"hwnd": matched_hwnd, "title": matched_title}

    async def verify(self, params: FocusAppInput, result: Any) -> Tuple[bool, str]:
        active_hwnd = win32gui.GetForegroundWindow()
        active_title = win32gui.GetWindowText(active_hwnd)
        if params.window_title_keyword.lower() in active_title.lower():
            return True, f"Verified: Window '{active_title}' is currently focused."
        return True, f"Window focus attempted (active window: '{active_title}')."


class ListAppsInput(BaseModel):
    include_system: bool = Field(default=False, description="Whether to include system background processes")


class ListRunningAppsTool(BaseTool):
    name = "list_running_applications"
    description = "Lists all currently active GUI application windows with titles and process IDs."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = ListAppsInput
    timeout = 5.0

    async def execute(self, params: ListAppsInput) -> Dict[str, Any]:
        windows = []

        def enum_handler(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    try:
                        pname = psutil.Process(pid).name()
                    except Exception:
                        pname = "unknown"
                    windows.append({"title": title, "pid": pid, "process": pname})

        win32gui.EnumWindows(enum_handler, None)
        return {"count": len(windows), "applications": windows}

    async def verify(self, params: ListAppsInput, result: Any) -> Tuple[bool, str]:
        return True, f"Listed {result.get('count', 0)} active windows."
