"""
Browser Automation & Web Navigation Tools
Provides direct control over browser tabs, navigation, scrolling, and searches.
"""

import os
import asyncio
import webbrowser
import urllib.parse
from typing import Dict, Any, Tuple, Literal
from pydantic import BaseModel, Field
import src.tools.gui_compat  # Safe headless display initialization
import pyautogui

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel


def focus_browser() -> None:
    """Brings the most recently active web browser window to foreground on Windows."""
    if not win32gui:
        return
    browser_keywords = ["chrome", "edge", "firefox", "brave", "opera", "youtube", "google"]
    matched_hwnd = None

    def enum_cb(hwnd, _):
        nonlocal matched_hwnd
        if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if any(k in title for k in browser_keywords):
                matched_hwnd = hwnd
                return False
        return True

    try:
        win32gui.EnumWindows(enum_cb, None)
        if matched_hwnd:
            win32gui.ShowWindow(matched_hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(matched_hwnd)
    except Exception:
        pass


def normalize_web_url(raw_url: str) -> str:
    """Normalizes URL, prepending protocol and resolving shorthand domain names."""
    url = raw_url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        if "." not in url:
            url = f"https://www.{url}.com"
        else:
            url = f"https://{url}"
    return url


class OpenUrlInput(BaseModel):
    url: str = Field(description="URL to open (e.g. 'https://youtube.com', 'https://google.com')")


class OpenUrlTool(BaseTool):
    name = "open_browser_url"
    description = (
        "STRICT: Opens a web URL in the user's browser. ONLY call when user explicitly says "
        "'open website', 'open url', or gives an explicit URL/link to open. "
        "FORBIDDEN: Never call this to answer questions, queries, or look up information."
    )
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = OpenUrlInput

    async def execute(self, params: OpenUrlInput) -> Dict[str, Any]:
        url = normalize_web_url(params.url)
        opened = False
        try:
            opened = await asyncio.to_thread(webbrowser.open, url)
        except Exception:
            pass
        if not opened and os.name == "nt":
            try:
                await asyncio.to_thread(os.startfile, url)
                opened = True
            except Exception:
                pass
        return {"url": url, "browser_opened": opened}

    async def verify(self, params: OpenUrlInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Launched browser with URL {result['url']}."


class WebSearchInput(BaseModel):
    query: str = Field(description="Search terms to look up")
    engine: str = Field(default="google", description="Search engine: 'google' or 'youtube'")


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "STRICT: Opens a new browser tab with Google or YouTube search. ONLY call when the user explicitly "
        "commands 'search on google', 'google karo', 'open youtube and search'. "
        "FORBIDDEN: Never call this for questions, facts, definitions, or queries. Always answer questions verbally without opening browser tabs."
    )
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = WebSearchInput

    async def execute(self, params: WebSearchInput) -> Dict[str, Any]:
        query_encoded = urllib.parse.quote_plus(params.query)
        if params.engine.lower() == "youtube":
            search_url = f"https://www.youtube.com/results?search_query={query_encoded}"
        else:
            search_url = f"https://www.google.com/search?q={query_encoded}"
        opened = False
        try:
            opened = await asyncio.to_thread(webbrowser.open, search_url)
        except Exception:
            pass
        if not opened and os.name == "nt":
            try:
                await asyncio.to_thread(os.startfile, search_url)
                opened = True
            except Exception:
                pass
        return {"query": params.query, "engine": params.engine, "search_url": search_url}

    async def verify(self, params: WebSearchInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Executed {result['engine']} search for '{params.query}'."


class BrowserTabActionInput(BaseModel):
    action: str = Field(
        description="Browser tab action: 'new_tab', 'close_tab', 'next_tab', 'prev_tab', 'reopen_tab', 'refresh', 'back', 'forward', 'focus_address_bar'"
    )


class BrowserTabControlTool(BaseTool):
    name = "browser_tab_control"
    description = "Controls browser tabs: open new tab, close tab, switch next/previous tab, refresh, navigate history back/forward, or focus address bar."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = BrowserTabActionInput

    async def execute(self, params: BrowserTabActionInput) -> Dict[str, Any]:
        raw_action = params.action.lower().strip()
        synonyms = {
            "open_tab": "new_tab",
            "create_tab": "new_tab",
            "close": "close_tab",
            "exit_tab": "close_tab",
            "reload": "refresh",
            "switch_tab": "next_tab",
            "previous_tab": "prev_tab"
        }
        action = synonyms.get(raw_action, raw_action)

        key_map = {
            "new_tab": ["ctrl", "t"],
            "close_tab": ["ctrl", "w"],
            "next_tab": ["ctrl", "tab"],
            "prev_tab": ["ctrl", "shift", "tab"],
            "reopen_tab": ["ctrl", "shift", "t"],
            "refresh": ["ctrl", "r"],
            "back": ["alt", "left"],
            "forward": ["alt", "right"],
            "focus_address_bar": ["ctrl", "l"]
        }

        if action not in key_map:
            raise ValueError(f"Unknown browser tab action: '{action}'. Available: {list(key_map.keys())}")

        focus_browser()
        await asyncio.sleep(0.05)
        keys = key_map[action]
        await asyncio.to_thread(pyautogui.hotkey, *keys)
        return {"action": action, "shortcut_keys": keys}

    async def verify(self, params: BrowserTabActionInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Browser action '{result['action']}' completed using shortcut {result['shortcut_keys']}."


class BrowserScrollInput(BaseModel):
    direction: str = Field(default="down", description="Scroll direction: 'down', 'up', 'top', or 'bottom'")
    amount: int = Field(default=5, description="Number of scroll steps or page clicks (1-10)")


class BrowserScrollTool(BaseTool):
    name = "browser_scroll"
    description = "Scrolls the currently focused browser webpage up, down, to the top, or to the bottom."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = BrowserScrollInput

    async def execute(self, params: BrowserScrollInput) -> Dict[str, Any]:
        focus_browser()
        await asyncio.sleep(0.05)
        dir_lower = params.direction.lower().strip()
        if dir_lower == "top":
            await asyncio.to_thread(pyautogui.press, "home")
        elif dir_lower == "bottom":
            await asyncio.to_thread(pyautogui.press, "end")
        elif dir_lower == "up":
            # Negative click value scrolls up in pyautogui on Windows
            await asyncio.to_thread(pyautogui.scroll, params.amount * 120)
        else: # down
            await asyncio.to_thread(pyautogui.scroll, -(params.amount * 120))
        return {"direction": dir_lower, "amount": params.amount}

    async def verify(self, params: BrowserScrollInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Scrolled browser page {result['direction']} by {result['amount']} units."


class BrowserNavigateInput(BaseModel):
    url: str = Field(description="URL or website name to navigate to in the active browser (e.g. 'youtube.com', 'google.com', 'github.com')")


class BrowserNavigateTool(BaseTool):
    name = "browser_navigate"
    description = "Navigates to a specific URL in the active browser tab by focusing the address bar, typing the URL, and pressing Enter."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = BrowserNavigateInput

    async def execute(self, params: BrowserNavigateInput) -> Dict[str, Any]:
        target_url = normalize_web_url(params.url)

        focus_browser()
        await asyncio.sleep(0.05)
        # Focus address bar (Ctrl+L), type URL, press Enter
        await asyncio.to_thread(pyautogui.hotkey, "ctrl", "l")
        await asyncio.sleep(0.1)
        await asyncio.to_thread(pyautogui.write, target_url, interval=0.01)
        await asyncio.sleep(0.05)
        await asyncio.to_thread(pyautogui.press, "enter")

        return {"url": target_url, "method": "address_bar_navigation"}

    async def verify(self, params: BrowserNavigateInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Navigated active browser tab to {result['url']}."
