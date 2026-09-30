"""
Plugin Auto-Registration & Discovery
"""

import src.tools.gui_compat  # Safe headless display initialization
from src.tools.registry import tool_registry

# Import all built-in plugins
from src.tools.plugins.app_tools import (
    LaunchAppTool,
    CloseAppTool,
    FocusAppTool,
    ListRunningAppsTool
)
from src.tools.plugins.window_tools import (
    MinimizeWindowTool,
    MaximizeWindowTool
)
from src.tools.plugins.input_tools import (
    KeyboardTypeTool,
    KeyboardHotkeyTool,
    MouseClickTool,
    MouseScrollTool,
    MouseMoveTool,
    MouseDragTool,
    GetCursorPositionTool
)
from src.tools.plugins.file_tools import (
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
    DeleteFileTool
)
from src.tools.plugins.browser_tools import (
    OpenUrlTool,
    WebSearchTool,
    BrowserTabControlTool,
    BrowserScrollTool,
    BrowserNavigateTool
)
from src.tools.plugins.system_tools import (
    TakeScreenshotTool,
    SystemInfoTool,
    SystemAudioVolumeTool,
    LockWorkstationTool
)
from src.tools.plugins.clipboard_tools import (
    ReadClipboardTool,
    WriteClipboardTool
)
from src.tools.plugins.dev_tools import (
    OpenProjectTool,
    OpenProjectInCursorTool,
    RunSafeCommandTool
)
from src.tools.plugins.custom_plugin import (
    CustomEchoTool
)


def register_default_tools() -> None:
    """Registers all built-in tool plugins into the central tool registry."""
    tools = [
        # App management
        LaunchAppTool(),
        CloseAppTool(),
        FocusAppTool(),
        ListRunningAppsTool(),

        # Windows
        MinimizeWindowTool(),
        MaximizeWindowTool(),

        # Inputs & Cursor
        KeyboardTypeTool(),
        KeyboardHotkeyTool(),
        MouseClickTool(),
        MouseScrollTool(),
        MouseMoveTool(),
        MouseDragTool(),
        GetCursorPositionTool(),

        # Files
        ListDirectoryTool(),
        ReadFileTool(),
        WriteFileTool(),
        DeleteFileTool(),

        # Browser & Web Controls
        OpenUrlTool(),
        WebSearchTool(),
        BrowserTabControlTool(),
        BrowserScrollTool(),
        BrowserNavigateTool(),

        # System
        TakeScreenshotTool(),
        SystemInfoTool(),
        SystemAudioVolumeTool(),
        LockWorkstationTool(),

        # Clipboard
        ReadClipboardTool(),
        WriteClipboardTool(),

        # Dev
        OpenProjectTool(),
        OpenProjectInCursorTool(),
        RunSafeCommandTool(),

        # Custom / Plugin
        CustomEchoTool()
    ]

    for tool in tools:
        tool_registry.register(tool)


register_default_tools()
