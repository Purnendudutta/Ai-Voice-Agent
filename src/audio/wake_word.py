"""
Neural Wake Word Detection Module
Uses OpenWakeWord with native ONNX Runtime for low-latency neural keyword spotting.
"""

import logging
from typing import Optional
import numpy as np
from src.config import settings

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """
    Detects wake words (e.g. 'Hey Jarvis') in streaming 16kHz PCM audio
    using OpenWakeWord models on ONNX Runtime.
    """

    def __init__(self, sensitivity: float = 0.65):
        self.sensitivity = sensitivity
        self._model = None
        self._enabled = False

        try:
            import openwakeword
            from openwakeword.model import Model
            import openwakeword.utils

            # Load ONNX-based wake word model
            try:
                self._model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            except Exception:
                # If model files not yet downloaded, download and initialize
                logger.info("Downloading neural wake word models (hey_jarvis)...")
                openwakeword.utils.download_models(model_names=["hey_jarvis"])
                self._model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

            self._enabled = True
            logger.info("Neural wake word detection active (model: 'Hey Jarvis' on ONNX Runtime).")
        except ImportError:
            logger.info("Neural wake word library not installed. Using VAD voice activity detection.")
        except Exception as e:
            logger.info(f"Wake word detector inactive ({e}). Using VAD voice activity detection.")

    @property
    def enabled(self) -> bool:
        """Returns True if the neural wake word detector is successfully loaded."""
        return self._enabled

    def reset(self) -> None:
        """Resets the internal buffer of the wake word model."""
        if self._model and hasattr(self._model, "reset"):
            try:
                self._model.reset()
            except Exception as e:
                logger.debug(f"Wake word reset error: {e}")

    def process_chunk(self, audio_bytes: bytes) -> Optional[str]:
        """
        Processes a raw PCM audio chunk for wake word detection.
        Returns the name of the wake word if detected, otherwise None.
        Expects 16000Hz, mono, 16-bit signed integer PCM audio.
        """
        if not self._enabled or not self._model:
            return None

        try:
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
            prediction = self._model.predict(audio_data)

            for mdl_name, score in prediction.items():
                if score > self.sensitivity:
                    logger.info(f"Wake word detected: {mdl_name} (confidence: {score:.2f})")
                    return mdl_name

            return None

        except Exception as e:
            logger.error(f"Error during wake word processing: {e}")
            return None
