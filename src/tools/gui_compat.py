"""
GUI & Display Compatibility Layer for Headless / Cloud Environments.
Ensures pyautogui and desktop UI tools load safely without raising KeyError: 'DISPLAY'
or display connection errors when deployed in headless Docker / Linux environments.
"""

import collections
import logging
import os
import sys

logger = logging.getLogger("shruti.gui_compat")

Point = collections.namedtuple("Point", ["x", "y"])
Size = collections.namedtuple("Size", ["width", "height"])


class HeadlessPyAutoGUI:
    """Mock/fallback pyautogui implementation for headless container environments."""
    FAILSAFE = False
    PAUSE = 0.05
    Point = Point
    Size = Size

    @staticmethod
    def position():
        return Point(x=0, y=0)

    @staticmethod
    def size():
        return Size(width=1920, height=1080)

    @staticmethod
    def moveTo(x, y, duration=0.0):
        pass

    @staticmethod
    def dragTo(x, y, duration=0.0, button="left"):
        pass

    @staticmethod
    def click(x=None, y=None, clicks=1, interval=0.0, button="left"):
        pass

    @staticmethod
    def scroll(clicks, x=None, y=None):
        pass

    @staticmethod
    def write(message, interval=0.0):
        pass

    @staticmethod
    def press(keys, presses=1, interval=0.0):
        pass

    @staticmethod
    def hotkey(*args, **kwargs):
        pass

    @staticmethod
    def keyUp(key):
        pass

    @staticmethod
    def keyDown(key):
        pass

    @staticmethod
    def screenshot(imageFilename=None, region=None):
        from PIL import Image
        img = Image.new("RGB", (1920, 1080), color=(15, 18, 30))
        if imageFilename:
            img.save(imageFilename)
        return img


def setup_gui_compatibility():
    """
    Ensure pyautogui can be imported safely.
    Sets DISPLAY fallback on Linux and provides HeadlessPyAutoGUI if no display server is reachable.
    """
    if "pyautogui" in sys.modules and not isinstance(sys.modules["pyautogui"], HeadlessPyAutoGUI):
        return sys.modules["pyautogui"]

    # Provide fallback DISPLAY environment variable if missing on Linux
    if sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":99"

    try:
        import pyautogui
        return pyautogui
    except Exception as e:
        logger.warning(
            "Display/GUI automation library (pyautogui) could not be initialized (%s). "
            "Activating HeadlessPyAutoGUI fallback for headless cloud environment.",
            e
        )
        headless = HeadlessPyAutoGUI()
        sys.modules["pyautogui"] = headless
        return headless


# Auto-run setup when this module is imported
setup_gui_compatibility()
