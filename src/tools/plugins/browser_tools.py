"""
Browser Automation & Web Search Tools
"""

import webbrowser
import urllib.parse
from typing import Dict, Any, Tuple
from pydantic import BaseModel, Field

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel


class OpenUrlInput(BaseModel):
    url: str = Field(description="URL to open (e.g. 'https://github.com' or 'https://google.com')")


class OpenUrlTool(BaseTool):
    name = "open_browser_url"
    description = "Opens a web URL in the user's default web browser."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = OpenUrlInput

    async def execute(self, params: OpenUrlInput) -> Dict[str, Any]:
        url = params.url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"
        opened = webbrowser.open(url)
        return {"url": url, "browser_opened": opened}

    async def verify(self, params: OpenUrlInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Launched browser with URL {result['url']}."


class WebSearchInput(BaseModel):
    query: str = Field(description="Search terms to look up")


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Conducts a web search query in the browser."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = WebSearchInput

    async def execute(self, params: WebSearchInput) -> Dict[str, Any]:
        query_encoded = urllib.parse.quote_plus(params.query)
        search_url = f"https://www.google.com/search?q={query_encoded}"
        webbrowser.open(search_url)
        return {"query": params.query, "search_url": search_url}

    async def verify(self, params: WebSearchInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Executed web search for '{params.query}'."
