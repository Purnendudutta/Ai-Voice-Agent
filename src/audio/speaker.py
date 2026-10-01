import queue
import logging
import sounddevice as sd
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

class SpeakerOutput:
    """
    Plays raw PCM audio using sounddevice.
    """
    
    def __init__(
        self,
        sample_rate: int = 24000,
        channels: int = 1,
        chunk_size: int = 1024
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._stream: Optional[sd.OutputStream] = None
        self._is_playing = False
        # Buffer for partial chunks if needed
        self._buffer = bytearray()

    @property
    def is_playing(self) -> bool:
        """Returns True if the speaker is currently playing audio."""
        return self._is_playing and (not self._queue.empty() or len(self._buffer) > 0)

    def _audio_callback(self, outdata: np.ndarray, frames: int, time, status: sd.CallbackFlags):
        """Callback for sounddevice to request audio for playback."""
        if status:
            logger.warning(f"Speaker status: {status}")

        bytes_needed = frames * self.channels * 2  # 2 bytes for int16
        
        # Fill buffer until we have enough bytes or queue is empty
        while len(self._buffer) < bytes_needed:
            try:
                chunk = self._queue.get_nowait()
                self._buffer.extend(chunk)
            except queue.Empty:
                break
                
        if len(self._buffer) >= bytes_needed:
            # We have enough data
            chunk_bytes = bytes(self._buffer[:bytes_needed])
            del self._buffer[:bytes_needed]
            
            # Convert bytes to numpy array
            data = np.frombuffer(chunk_bytes, dtype=np.int16).reshape(-1, self.channels)
            outdata[:] = data
        else:
            # Not enough data, pad with zeros
            if len(self._buffer) > 0:
                chunk_bytes = bytes(self._buffer)
                del self._buffer[:]
                data = np.frombuffer(chunk_bytes, dtype=np.int16).reshape(-1, self.channels)
                outdata[:data.shape[0]] = data
                outdata[data.shape[0]:] = 0
            else:
                outdata[:] = 0

    def start(self):
        """Starts the audio output stream."""
        if self._is_playing:
            return
            
        try:
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                blocksize=self.chunk_size,
                callback=self._audio_callback
            )
            self._stream.start()
            self._is_playing = True
        except Exception as e:
            logger.info(f"Physical speaker not attached ({e}). In-browser audio streaming active.")
            self._is_playing = False

    def stop(self):
        """Stops the audio output stream."""
        if not self._is_playing:
            return
            
        self._is_playing = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.clear_queue()
        logger.info("Stopped speaker output")

    def play_chunk(self, data: bytes):
        """Queues a raw PCM chunk for playback."""
        if self._is_playing:
            self._queue.put(data)

    def clear_queue(self):
        """Immediately empties the audio queue and buffer (for barge-in/interruption)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._buffer.clear()
        logger.debug("Cleared speaker audio queue")
