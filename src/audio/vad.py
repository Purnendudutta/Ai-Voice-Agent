import numpy as np
import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)

class VADEvent(Enum):
    SPEECH_START = auto()
    SPEECH_CONTINUE = auto()
    SPEECH_END = auto()
    SILENCE = auto()

class VoiceActivityDetector:
    """
    A simple energy-based Voice Activity Detector (VAD).
    Calculates RMS energy of incoming audio chunks to detect speech.
    """
    
    def __init__(
        self, 
        energy_threshold: float = 0.006, 
        silence_duration: float = 0.8,
        sample_rate: int = 16000,
        chunk_size: int = 1024
    ):
        self.energy_threshold = energy_threshold
        self.silence_duration = silence_duration
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        
        # Calculate how many silent chunks we need to consider it "speech end"
        self.silence_frames_threshold = int((self.silence_duration * self.sample_rate) / self.chunk_size)
        
        self.is_speaking = False
        self.silence_frames_count = 0

    def reset(self):
        """Resets the VAD speaking state and counters."""
        self.is_speaking = False
        self.silence_frames_count = 0
        
    def process_chunk(self, audio_bytes: bytes) -> VADEvent:
        """
        Processes a raw PCM audio chunk and returns the current VAD state.
        Expects 16-bit signed integer PCM data.
        """
        if not audio_bytes:
            return VADEvent.SILENCE
            
        # Convert raw bytes to numpy array of int16
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # Calculate RMS energy
        # Normalize data to [-1.0, 1.0] before calculating RMS
        normalized_data = audio_data.astype(np.float32) / 32768.0
        rms_energy = np.sqrt(np.mean(normalized_data**2))
        
        is_above_threshold = rms_energy > self.energy_threshold
        
        if is_above_threshold:
            self.silence_frames_count = 0
            if not self.is_speaking:
                self.is_speaking = True
                return VADEvent.SPEECH_START
            else:
                return VADEvent.SPEECH_CONTINUE
        else:
            if self.is_speaking:
                self.silence_frames_count += 1
                if self.silence_frames_count >= self.silence_frames_threshold:
                    self.is_speaking = False
                    return VADEvent.SPEECH_END
                else:
                    return VADEvent.SPEECH_CONTINUE
            else:
                return VADEvent.SILENCE
