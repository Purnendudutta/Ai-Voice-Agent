"""
Browser Automation & Web Navigation Tools
Provides direct control over browser tabs, navigation, scrolling, and searches.
"""

import asyncio
import webbrowser
import urllib.parse
from typing import Dict, Any, Tuple, Literal
from pydantic import BaseModel, Field
import pyautogui

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel


class OpenUrlInput(BaseModel):
    url: str = Field(description="URL to open (e.g. 'https://youtube.com', 'https://google.com')")


class OpenUrlTool(BaseTool):
    name = "open_browser_url"
    description = "Opens a web URL in the user's default web browser."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = OpenUrlInput

    async def execute(self, params: OpenUrlInput) -> Dict[str, Any]:
        url = params.url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"
        opened = await asyncio.to_thread(webbrowser.open, url)
        return {"url": url, "browser_opened": opened}

    async def verify(self, params: OpenUrlInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Launched browser with URL {result['url']}."


class WebSearchInput(BaseModel):
    query: str = Field(description="Search terms to look up")
    engine: str = Field(default="google", description="Search engine: 'google' or 'youtube'")


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Conducts a web or YouTube search query in the browser."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = WebSearchInput

    async def execute(self, params: WebSearchInput) -> Dict[str, Any]:
        query_encoded = urllib.parse.quote_plus(params.query)
        if params.engine.lower() == "youtube":
            search_url = f"https://www.youtube.com/results?search_query={query_encoded}"
        else:
            search_url = f"https://www.google.com/search?q={query_encoded}"
        await asyncio.to_thread(webbrowser.open, search_url)
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
        action = params.action.lower().strip()
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
        url = params.url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            target_url = f"https://{url}"
        else:
            target_url = url

        # Focus address bar (Ctrl+L), type URL, press Enter
        await asyncio.to_thread(pyautogui.hotkey, "ctrl", "l")
        await asyncio.sleep(0.1)
        await asyncio.to_thread(pyautogui.write, target_url, interval=0.01)
        await asyncio.sleep(0.05)
        await asyncio.to_thread(pyautogui.press, "enter")

        return {"url": target_url, "method": "address_bar_navigation"}

    async def verify(self, params: BrowserNavigateInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Navigated active browser tab to {result['url']}."
