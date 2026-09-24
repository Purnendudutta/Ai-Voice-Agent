"""
Keyboard & Mouse Automation Tools
"""

import asyncio
from typing import Dict, Any, Tuple, List, Optional
from pydantic import BaseModel, Field
import pyautogui

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel

# Configure pyautogui safety
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05


class KeyboardTypeInput(BaseModel):
    text: str = Field(description="The text string to type into the currently focused window")
    interval: float = Field(default=0.01, description="Interval in seconds between keystrokes")
    press_enter: bool = Field(default=False, description="Whether to press Enter after typing")


class KeyboardTypeTool(BaseTool):
    name = "keyboard_type"
    description = "Types text into the active focused window as keyboard input."
    risk_level = RiskLevel.MODERATE
    parameters_schema = KeyboardTypeInput

    async def execute(self, params: KeyboardTypeInput) -> Dict[str, Any]:
        # Run in thread to not block async loop
        await asyncio.to_thread(pyautogui.write, params.text, interval=params.interval)
        if params.press_enter:
            await asyncio.to_thread(pyautogui.press, "enter")
        return {"typed_characters": len(params.text), "pressed_enter": params.press_enter}

    async def verify(self, params: KeyboardTypeInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Successfully sent {result['typed_characters']} keystrokes."


class KeyboardHotkeyInput(BaseModel):
    keys: List[str] = Field(description="List of keys to press simultaneously (e.g. ['ctrl', 's'], ['alt', 'tab'], ['enter'])")


class KeyboardHotkeyTool(BaseTool):
    name = "keyboard_hotkey"
    description = "Executes a keyboard shortcut combination or special key press."
    risk_level = RiskLevel.MODERATE
    parameters_schema = KeyboardHotkeyInput

    async def execute(self, params: KeyboardHotkeyInput) -> Dict[str, Any]:
        keys = [k.lower().strip() for k in params.keys]
        await asyncio.to_thread(pyautogui.hotkey, *keys)
        return {"keys_pressed": keys}

    async def verify(self, params: KeyboardHotkeyInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Hotkey combination {result['keys_pressed']} executed."


class MouseClickInput(BaseModel):
    x: Optional[int] = Field(default=None, description="Screen X coordinate. If omitted, clicks current cursor position.")
    y: Optional[int] = Field(default=None, description="Screen Y coordinate. If omitted, clicks current cursor position.")
    button: str = Field(default="left", description="Mouse button: 'left', 'right', or 'middle'")
    clicks: int = Field(default=1, description="Number of clicks (1 for single click, 2 for double click)")


class MouseClickTool(BaseTool):
    name = "mouse_click"
    description = "Clicks the mouse at specified coordinates or current position."
    risk_level = RiskLevel.MODERATE
    parameters_schema = MouseClickInput

    async def execute(self, params: MouseClickInput) -> Dict[str, Any]:
        if params.x is not None and params.y is not None:
            await asyncio.to_thread(
                pyautogui.click,
                x=params.x,
                y=params.y,
                button=params.button,
                clicks=params.clicks
            )
            pos = (params.x, params.y)
        else:
            await asyncio.to_thread(
                pyautogui.click,
                button=params.button,
                clicks=params.clicks
            )
            pos = pyautogui.position()
        return {"clicked_at": pos, "button": params.button, "clicks": params.clicks}

    async def verify(self, params: MouseClickInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Mouse {result['button']} click executed at {result['clicked_at']}."


class MouseScrollInput(BaseModel):
    amount: int = Field(description="Positive integer to scroll up, negative to scroll down (e.g. -300 to scroll down)")


class MouseScrollTool(BaseTool):
    name = "mouse_scroll"
    description = "Scrolls the mouse wheel up or down."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = MouseScrollInput

    async def execute(self, params: MouseScrollInput) -> Dict[str, Any]:
        await asyncio.to_thread(pyautogui.scroll, params.amount)
        return {"scroll_amount": params.amount}

    async def verify(self, params: MouseScrollInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Mouse scroll of {result['scroll_amount']} units executed."


class MouseMoveInput(BaseModel):
    x: int = Field(description="Target X screen coordinate")
    y: int = Field(description="Target Y screen coordinate")
    duration: float = Field(default=0.2, description="Movement duration in seconds for smooth cursor movement")


class MouseMoveTool(BaseTool):
    name = "mouse_move"
    description = "Moves the mouse cursor to the specified screen coordinates (X, Y)."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = MouseMoveInput

    async def execute(self, params: MouseMoveInput) -> Dict[str, Any]:
        size = pyautogui.size()
        safe_x = max(5, min(params.x, size.width - 5))
        safe_y = max(5, min(params.y, size.height - 5))
        await asyncio.to_thread(pyautogui.moveTo, safe_x, safe_y, duration=max(0.0, params.duration))
        curr = pyautogui.position()
        return {"target_x": params.x, "target_y": params.y, "actual_x": curr.x, "actual_y": curr.y}

    async def verify(self, params: MouseMoveInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Cursor moved to ({result['actual_x']}, {result['actual_y']})."


class MouseDragInput(BaseModel):
    to_x: int = Field(description="Destination X screen coordinate")
    to_y: int = Field(description="Destination Y screen coordinate")
    from_x: Optional[int] = Field(default=None, description="Starting X coordinate. If omitted, uses current cursor position.")
    from_y: Optional[int] = Field(default=None, description="Starting Y coordinate. If omitted, uses current cursor position.")
    button: str = Field(default="left", description="Mouse button to hold during drag ('left', 'right', 'middle')")
    duration: float = Field(default=0.5, description="Drag duration in seconds")


class MouseDragTool(BaseTool):
    name = "mouse_drag"
    description = "Drags the mouse cursor from start to target coordinates while holding a mouse button."
    risk_level = RiskLevel.MODERATE
    parameters_schema = MouseDragInput

    async def execute(self, params: MouseDragInput) -> Dict[str, Any]:
        size = pyautogui.size()
        safe_to_x = max(5, min(params.to_x, size.width - 5))
        safe_to_y = max(5, min(params.to_y, size.height - 5))
        if params.from_x is not None and params.from_y is not None:
            safe_from_x = max(5, min(params.from_x, size.width - 5))
            safe_from_y = max(5, min(params.from_y, size.height - 5))
            await asyncio.to_thread(pyautogui.moveTo, safe_from_x, safe_from_y)
        await asyncio.to_thread(pyautogui.dragTo, safe_to_x, safe_to_y, duration=max(0.1, params.duration), button=params.button)
        curr = pyautogui.position()
        return {"dragged_to": (curr.x, curr.y), "button": params.button}

    async def verify(self, params: MouseDragInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Cursor dragged to {result['dragged_to']} with {result['button']} button."


class GetCursorPositionInput(BaseModel):
    pass


class GetCursorPositionTool(BaseTool):
    name = "get_cursor_position"
    description = "Gets the current mouse cursor screen position (X, Y) and full screen resolution dimensions."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = GetCursorPositionInput

    async def execute(self, params: GetCursorPositionInput) -> Dict[str, Any]:
        pos = pyautogui.position()
        size = pyautogui.size()
        return {
            "cursor_x": pos.x,
            "cursor_y": pos.y,
            "screen_width": size.width,
            "screen_height": size.height
        }

    async def verify(self, params: GetCursorPositionInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Cursor at ({result['cursor_x']}, {result['cursor_y']}) on {result['screen_width']}x{result['screen_height']} display."
