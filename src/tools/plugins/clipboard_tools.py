"""
Clipboard Automation Tools
"""

import asyncio
from typing import Dict, Any, Tuple
from pydantic import BaseModel, Field
import pyperclip

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel


class ReadClipboardInput(BaseModel):
    pass


class ReadClipboardTool(BaseTool):
    name = "read_clipboard"
    description = "Reads current text contents from the Windows clipboard."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = ReadClipboardInput

    async def execute(self, params: ReadClipboardInput) -> Dict[str, Any]:
        text = await asyncio.to_thread(pyperclip.paste)
        return {"content": text, "length": len(text)}

    async def verify(self, params: ReadClipboardInput, result: Any) -> Tuple[bool, str]:
        return True, f"Retrieved {result['length']} characters from clipboard."


class WriteClipboardInput(BaseModel):
    text: str = Field(description="Text to copy to the clipboard")


class WriteClipboardTool(BaseTool):
    name = "write_clipboard"
    description = "Copies text string into the Windows clipboard."
    risk_level = RiskLevel.MODERATE
    parameters_schema = WriteClipboardInput

    async def execute(self, params: WriteClipboardInput) -> Dict[str, Any]:
        await asyncio.to_thread(pyperclip.copy, params.text)
        return {"copied_length": len(params.text)}

    async def verify(self, params: WriteClipboardInput, result: Any) -> Tuple[bool, str]:
        current = await asyncio.to_thread(pyperclip.paste)
        if current == params.text:
            return True, "Verified: Clipboard content matches expected text."
        return False, "Verification failed: Clipboard content did not match."
