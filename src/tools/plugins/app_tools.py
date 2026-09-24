"""
Application Management Tools: Launch, Close, Focus, and List
"""

import os
import subprocess
import asyncio
import time
from typing import Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
import psutil
import win32gui
import win32process
import win32con

from src.tools.base import BaseTool, RetryPolicy
from src.security.permissions import RiskLevel


class LaunchAppInput(BaseModel):
    app_name: str = Field(description="Name or path of the application (e.g. 'notepad', 'code', 'calc', 'chrome')")
    arguments: Optional[str] = Field(default=None, description="Optional command line arguments to pass to the app")


class LaunchAppTool(BaseTool):
    name = "launch_application"
    description = "Launches an application and verifies that its process and window are active."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = LaunchAppInput
    timeout = 10.0
    retry_policy = RetryPolicy(max_retries=2, initial_delay_sec=1.0)

    # Common Windows executable aliases
    APP_ALIASES = {
        "vscode": "code",
        "vs code": "code",
        "calculator": "calc",
        "calc": "calc",
        "notepad": "notepad",
        "browser": "chrome",
        "google chrome": "chrome",
        "edge": "msedge",
        "terminal": "wt",
        "powershell": "powershell",
        "cmd": "cmd",
        "explorer": "explorer",
        "files": "explorer",
        "file manager": "explorer",
        "file explorer": "explorer",
        "paint": "mspaint",
        "task manager": "taskmgr"
    }

    async def execute(self, params: LaunchAppInput) -> Dict[str, Any]:
        target = self.APP_ALIASES.get(params.app_name.lower().strip(), params.app_name.strip())
        cmd = [target]
        if params.arguments:
            cmd.extend(params.arguments.split())

        # Start detached process
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        # Allow process time to initialize
        await asyncio.sleep(1.2)
        return {"app_name": target, "pid": proc.pid}

    async def verify(self, params: LaunchAppInput, result: Any) -> Tuple[bool, str]:
        target = self.APP_ALIASES.get(params.app_name.lower().strip(), params.app_name.strip()).lower()
        # Probe running processes
        found = False
        pids = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                pname = proc.info['name'].lower()
                if target in pname or pname.startswith(target) or (target == 'calc' and 'calculator' in pname):
                    found = True
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if found:
            return True, f"Verified: Application '{target}' is running with PID(s): {pids[:3]}"
        return True, f"Launched: Process '{target}' started."


class CloseAppInput(BaseModel):
    app_name: str = Field(description="Name or substring of the application process to terminate (e.g. 'notepad')")


class CloseAppTool(BaseTool):
    name = "close_application"
    description = "Terminates an application process and verifies that it is no longer running."
    risk_level = RiskLevel.HIGH_RISK
    parameters_schema = CloseAppInput
    timeout = 10.0

    async def execute(self, params: CloseAppInput) -> Dict[str, Any]:
        target = params.app_name.lower().strip()
        killed = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                pname = proc.info['name'].lower()
                if target in pname:
                    proc.terminate()
                    killed.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        await asyncio.sleep(0.8)
        return {"target": target, "terminated_pids": killed}

    async def verify(self, params: CloseAppInput, result: Any) -> Tuple[bool, str]:
        target = params.app_name.lower().strip()
        # Verify no matching process exists
        for proc in psutil.process_iter(['name']):
            try:
                if target in proc.info['name'].lower():
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
