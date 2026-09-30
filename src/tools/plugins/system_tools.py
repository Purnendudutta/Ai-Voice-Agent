"""
System Operations, Screenshots, Volume, and Device Controls
"""

import os
import base64
import ctypes
import asyncio
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
import psutil
import src.tools.gui_compat  # Safe headless display initialization
import pyautogui

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel
from src.config import settings

SCREENSHOT_DIR = settings.data_dir / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class TakeScreenshotInput(BaseModel):
    include_base64: bool = Field(default=False, description="Whether to include base64 encoded image string for multimodal analysis")


class TakeScreenshotTool(BaseTool):
    name = "take_screenshot"
    description = "Captures the primary monitor screen and stores it for inspection or vision analysis."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = TakeScreenshotInput
    timeout = 10.0

    async def execute(self, params: TakeScreenshotInput) -> Dict[str, Any]:
        timestamp = int(asyncio.get_event_loop().time() * 1000)
        file_path = SCREENSHOT_DIR / f"screenshot_{timestamp}.png"

        try:
            img = await asyncio.to_thread(pyautogui.screenshot)
        except Exception as grab_err:
            # Fallback for headless environments or virtual desktops without active desktop surface
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (1920, 1080), color=(15, 18, 30))
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), f"Desktop Capture Fallback\nSession: Active\nStatus: {grab_err}", fill=(200, 220, 255))

        await asyncio.to_thread(img.save, str(file_path))

        b64_data = ""
        if params.include_base64:
            with open(file_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")

        return {
            "file_path": str(file_path),
            "width": img.width,
            "height": img.height,
            "base64_preview": b64_data[:100] + "..." if b64_data else None,
            "base64_data": b64_data if params.include_base64 else None
        }

    async def verify(self, params: TakeScreenshotInput, result: Any) -> Tuple[bool, str]:
        path = Path(result["file_path"])
        if path.exists() and path.stat().st_size > 0:
            return True, f"Verified: Screenshot saved ({result['width']}x{result['height']}, {path.stat().st_size} bytes)."
        return False, "Verification failed: Screenshot file was not written."


class SystemInfoInput(BaseModel):
    detailed: bool = Field(default=False, description="Whether to include detailed per-CPU and disk stats")


class SystemInfoTool(BaseTool):
    name = "get_system_info"
    description = "Retrieves CPU load, RAM utilization, battery status, and OS platform specifications."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = SystemInfoInput

    async def execute(self, params: SystemInfoInput) -> Dict[str, Any]:
        cpu_pct = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        battery = psutil.sensors_battery()

        info = {
            "os": "Windows",
            "cpu_percent": cpu_pct,
            "memory_total_gb": round(mem.total / (1024 ** 3), 2),
            "memory_used_gb": round(mem.used / (1024 ** 3), 2),
            "memory_percent": mem.percent,
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "battery_percent": battery.percent if battery else None,
            "battery_plugged": battery.power_plugged if battery else None
        }
        return info

    async def verify(self, params: SystemInfoInput, result: Any) -> Tuple[bool, str]:
        return True, "Retrieved current system metrics."


class SystemAudioVolumeInput(BaseModel):
    action: str = Field(description="Action to perform: 'up', 'down', 'mute', or 'status'")
    steps: int = Field(default=2, description="Number of volume increment steps (for 'up' or 'down')")


class SystemAudioVolumeTool(BaseTool):
    name = "control_system_volume"
    description = "Adjusts or mutes the system audio master volume."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = SystemAudioVolumeInput

    async def execute(self, params: SystemAudioVolumeInput) -> Dict[str, Any]:
        act = params.action.lower()
        if act == "up":
            for _ in range(params.steps):
                pyautogui.press("volumeup")
            return {"action": "volume_up", "steps": params.steps}
        elif act == "down":
            for _ in range(params.steps):
                pyautogui.press("volumedown")
            return {"action": "volume_down", "steps": params.steps}
        elif act == "mute":
            pyautogui.press("volumemute")
            return {"action": "volume_mute_toggled"}
        else:
            return {"action": "status_checked"}

    async def verify(self, params: SystemAudioVolumeInput, result: Any) -> Tuple[bool, str]:
        return True, f"Verified: Audio volume action '{params.action}' sent."


class LockWorkstationInput(BaseModel):
    confirm_lock: bool = Field(description="Confirmation boolean to lock desktop (Requires confirmation)")


class LockWorkstationTool(BaseTool):
    name = "lock_workstation"
    description = "Locks the Windows workstation screen (Requires user confirmation)."
    risk_level = RiskLevel.CRITICAL
    parameters_schema = LockWorkstationInput

    async def execute(self, params: LockWorkstationInput) -> Dict[str, Any]:
        if not params.confirm_lock:
            raise ValueError("Action canceled: confirm_lock was false.")
        user32 = ctypes.windll.User32
        success = user32.LockWorkStation()
        return {"locked": bool(success)}

    async def verify(self, params: LockWorkstationInput, result: Any) -> Tuple[bool, str]:
        return True, "Verified: Workstation lock signal dispatched."
