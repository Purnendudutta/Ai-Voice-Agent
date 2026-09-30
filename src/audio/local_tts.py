"""
Local Text-to-Speech Engine
Uses Microsoft Edge Natural Neural TTS (edge-tts) for studio-grade human speech,
with fallback to Windows SAPI5 (Microsoft Zira/David) only when offline.
"""

import logging
import asyncio
import tempfile
import os
import threading
from typing import Optional, Callable, Any

logger = logging.getLogger("LocalTTS")


class LocalTTS:
    """High-fidelity Text-to-Speech synthesizer using Microsoft Natural Neural Voices."""

    def __init__(self, rate: str = "+0%", volume: str = "+0%"):
        self.rate = rate
        self.volume = volume
        self._lock = threading.Lock()
        self.on_audio_data: Optional[Callable[[bytes, int], Any]] = None

    def set_audio_callback(self, cb: Callable[[bytes, int], Any]) -> None:
        """Register an async or sync callback to receive raw PCM chunks (bytes, sample_rate)."""
        self.on_audio_data = cb

    async def speak(self, text: str, gender: str = "female") -> None:
        """Speaks the text string using Neural Edge TTS or SAPI fallback."""
        if not text or not text.strip():
            return

        # 1. Try Microsoft Edge Natural Neural TTS (crystal clear human voice)
        try:
            import edge_tts
            import miniaudio
            import sounddevice as sd
            import numpy as np

            # Select high-quality natural neural voice
            hindi_keywords = ["meri jaan", "babu", "kholo", "karo", "namaste", "aapka", "kya", "hoon", "shona", "sweetheart", "hai", "main"]
            has_hindi = any(k in text.lower() for k in hindi_keywords)

            if gender == "female":
                voice = "hi-IN-SwaraNeural" if has_hindi else "en-US-JennyNeural"
            else:
                voice = "hi-IN-MadhurNeural" if has_hindi else "en-US-GuyNeural"

            communicate = edge_tts.Communicate(text, voice)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            try:
                await communicate.save(tmp_path)
                decoded = miniaudio.decode_file(tmp_path)
                samples = np.frombuffer(decoded.samples, dtype=np.int16)
                if decoded.nchannels > 1:
                    samples = samples.reshape(-1, decoded.nchannels)[:, 0]

                raw_bytes = samples.tobytes()

                # Stream audio chunks directly to browser WebSocket clients
                if self.on_audio_data:
                    chunk_duration = 0.15  # 150ms slices for smooth browser playback
                    chunk_samples = int(decoded.sample_rate * chunk_duration)
                    chunk_bytes_len = chunk_samples * 2  # 2 bytes per int16 sample

                    for i in range(0, len(raw_bytes), chunk_bytes_len):
                        chunk = raw_bytes[i:i + chunk_bytes_len]
                        cb_res = self.on_audio_data(chunk, decoded.sample_rate)
                        if asyncio.iscoroutine(cb_res):
                            await cb_res
                        await asyncio.sleep(chunk_duration * 0.85)

                # Play on local physical sound card if one exists (Windows/host)
                try:
                    sd.play(samples, samplerate=decoded.sample_rate)
                    duration = len(samples) / decoded.sample_rate
                    if not self.on_audio_data:
                        await asyncio.sleep(duration + 0.1)
                except Exception as sd_err:
                    logger.debug(f"Physical sound device unavailable (normal in Docker/cloud): {sd_err}")

                return
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        except Exception as e:
            logger.debug(f"Edge Neural TTS playback unavailable, falling back: {e}")

        # 2. Offline fallback: Windows SAPI.SpVoice via COM (Windows only)
        if os.name == "nt":
            await asyncio.to_thread(self._sync_sapi_speak, text, gender)
        else:
            logger.debug("SAPI fallback skipped on non-Windows environment.")

    def _sync_sapi_speak(self, text: str, gender: str = "female") -> None:
        with self._lock:
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Rate = 0
                speaker.Volume = 90

                voices = speaker.GetVoices()
                target_voice = None
                for i in range(voices.Count):
                    v = voices.Item(i)
                    desc = v.GetDescription().lower()
                    if gender == "female" and ("zira" in desc or "female" in desc):
                        target_voice = v
                        break
                    elif gender == "male" and ("david" in desc or "male" in desc):
                        target_voice = v
                        break

                if target_voice:
                    speaker.Voice = target_voice

                speaker.Speak(text)
                pythoncom.CoUninitialize()
            except Exception as e:
                logger.error(f"SAPI speak error: {e}")


local_tts = LocalTTS()
