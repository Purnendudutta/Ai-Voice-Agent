import logging
from typing import Optional
from src.config import settings
import numpy as np

logger = logging.getLogger(__name__)

class WakeWordDetector:
    """
    Detects wake words in streaming audio.
    Uses openwakeword if available, otherwise falls back to a stub.
    """
    
    def __init__(self, sensitivity: float = 0.65):
        self.sensitivity = sensitivity
        self._model = None
        self._enabled = False
        
        try:
            import openwakeword
            from openwakeword.model import Model
            
            # Load default models
            self._model = Model()
            self._enabled = True
            logger.info("Successfully loaded openwakeword models.")
        except ImportError as e:
            logger.warning(f"Failed to import openwakeword ({e}). Wake word detection will be disabled.")
        except Exception as e:
            logger.warning(f"Error initializing openwakeword ({e}). Wake word detection will be disabled.")

    @property
    def enabled(self) -> bool:
        """Returns True if the neural wake word detector is successfully loaded."""
        return self._enabled

    def process_chunk(self, audio_bytes: bytes) -> Optional[str]:
        """
        Processes a raw PCM audio chunk for wake word detection.
        Returns the name of the wake word if detected, otherwise None.
        Expects 16000Hz, mono, 16-bit PCM audio.
        """
        if not self._enabled or not self._model:
            return None
            
        try:
            # Convert raw bytes to int16 numpy array as expected by openwakeword
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
            
            # Predict
            prediction = self._model.predict(audio_data)
            
            # Check scores
            for mdl_name, scores in prediction.items():
                if scores > self.sensitivity:
                    logger.info(f"Wake word detected: {mdl_name} (score: {scores:.2f})")
                    return mdl_name
                    
            return None
            
        except Exception as e:
            logger.error(f"Error during wake word processing: {e}")
            return None
