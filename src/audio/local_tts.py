"""
Local Text-to-Speech Engine
Uses native Windows SAPI5 (via win32com) or pyttsx3 fallback to speak responses
when offline or in degraded mode with zero latency and full thread safety.
"""

import logging
import asyncio
import threading
from typing import Optional

logger = logging.getLogger("LocalTTS")


class LocalTTS:
    """Offline Text-to-Speech synthesizer using Windows SAPI5."""

    def __init__(self, rate: int = 1, volume: int = 90):
        self.rate = rate  # SAPI5 rate is -10 to +10 (0 or 1 is natural speed)
        self.volume = volume  # 0 to 100
        self._lock = threading.Lock()

    async def speak(self, text: str) -> None:
        """Speaks the text string asynchronously in a worker thread."""
        if not text:
            return
        await asyncio.to_thread(self._sync_speak, text)

    def _sync_speak(self, text: str) -> None:
        with self._lock:
            # 1. Native Windows SAPI.SpVoice via COM
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Rate = self.rate
                speaker.Volume = self.volume
                speaker.Speak(text)
                pythoncom.CoUninitialize()
                return
            except Exception as e:
                logger.debug(f"SAPI.SpVoice speak error: {e}")

            # 2. Fallback to pyttsx3 fresh instance
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                return
            except Exception as e:
                logger.error(f"TTS playback fallback error: {e}")


local_tts = LocalTTS()
