import asyncio
import logging
import sounddevice as sd
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

class MicrophoneStream:
    """
    Captures raw PCM audio from the default input device using sounddevice.
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_active = False

    @property
    def is_active(self) -> bool:
        """Returns True if the microphone is currently capturing audio."""
        return self._is_active

    def _audio_callback(self, indata: np.ndarray, frames: int, time, status: sd.CallbackFlags):
        """Callback for sounddevice to process incoming audio chunks."""
        if status:
            logger.warning(f"Microphone status: {status}")
        
        if self._is_active and self._loop:
            # Convert to raw bytes (int16 little endian)
            raw_bytes = indata.tobytes()
            self._loop.call_soon_threadsafe(self.queue.put_nowait, raw_bytes)

    def start(self):
        """Starts capturing audio from the microphone."""
        if self._is_active:
            return

        self._loop = asyncio.get_running_loop()
        
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                blocksize=self.chunk_size,
                callback=self._audio_callback
            )
            self._stream.start()
            self._is_active = True
            logger.info(f"Started microphone capture (sr={self.sample_rate}, channels={self.channels})")
        except Exception as e:
            logger.error(f"Failed to start microphone: {e}")
            raise

    def stop(self):
        """Stops capturing audio."""
        if not self._is_active:
            return
            
        self._is_active = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Stopped microphone capture")
