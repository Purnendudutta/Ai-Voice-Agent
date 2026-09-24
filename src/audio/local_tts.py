"""
Local Text-to-Speech Engine
Uses pyttsx3 and Windows SAPI5 to speak responses when offline or in degraded mode.
"""

import logging
import asyncio
from typing import Optional
import pyttsx3

logger = logging.getLogger("LocalTTS")


class LocalTTS:
    """Offline Text-to-Speech synthesizer using Windows SAPI5."""

    def __init__(self, rate: int = 190, volume: float = 0.9):
        self.rate = rate
        self.volume = volume
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)
        except Exception as e:
            logger.warning(f"Failed to initialize pyttsx3: {e}")
            self._engine = None

    async def speak(self, text: str) -> None:
        """Speaks the text string asynchronously in a worker thread."""
        if not text:
            return
        await asyncio.to_thread(self._sync_speak, text)

    def _sync_speak(self, text: str) -> None:
        try:
            if not self._engine:
                self._init_engine()
            if self._engine:
                self._engine.say(text)
                self._engine.runAndWait()
        except Exception as e:
            logger.error(f"TTS playback error: {e}")


local_tts = LocalTTS()
