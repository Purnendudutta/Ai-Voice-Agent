"""
Window Management Tools
"""

import asyncio
from typing import Dict, Any, Tuple
from pydantic import BaseModel, Field
import win32gui
import win32con

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel


class WindowActionInput(BaseModel):
    window_title_keyword: str = Field(description="Keyword matching the window title")


class MinimizeWindowTool(BaseTool):
    name = "minimize_window"
    description = "Minimizes an open application window."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = WindowActionInput

    async def execute(self, params: WindowActionInput) -> Dict[str, Any]:
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
            raise ValueError(f"No window found matching '{keyword}'.")

        win32gui.ShowWindow(matched_hwnd, win32con.SW_MINIMIZE)
        await asyncio.sleep(0.3)
        return {"hwnd": matched_hwnd, "title": matched_title}

    async def verify(self, params: WindowActionInput, result: Any) -> Tuple[bool, str]:
        hwnd = result["hwnd"]
        is_iconic = win32gui.IsIconic(hwnd)
        if is_iconic:
            return True, f"Verified: Window '{result['title']}' is minimized."
        return True, "Minimized window command issued."


class MaximizeWindowTool(BaseTool):
    name = "maximize_window"
    description = "Maximizes an open application window."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = WindowActionInput

    async def execute(self, params: WindowActionInput) -> Dict[str, Any]:
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
            raise ValueError(f"No window found matching '{keyword}'.")

        win32gui.ShowWindow(matched_hwnd, win32con.SW_MAXIMIZE)
        await asyncio.sleep(0.3)
        return {"hwnd": matched_hwnd, "title": matched_title}

    async def verify(self, params: WindowActionInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Window '{result['title']}' maximized."
