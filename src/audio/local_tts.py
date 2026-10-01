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
        self.on_audio_clip: Optional[Callable[[str, str], Any]] = None

    def set_audio_callback(self, cb: Callable[[bytes, int], Any]) -> None:
        """Register an async or sync callback to receive raw PCM chunks (bytes, sample_rate)."""
        self.on_audio_data = cb

    def set_audio_clip_callback(self, cb: Callable[[str, str], Any]) -> None:
        """Register a callback to receive the entire synthesized audio clip (base64_data, mime_type)."""
        self.on_audio_clip = cb

    async def synthesize_mp3(self, text: str, gender: str = "female") -> Optional[bytes]:
        """Synthesizes text to MP3 bytes using Edge Neural TTS with Google TTS cloud fallback."""
        if not text or not text.strip():
            return None

        hindi_keywords = ["meri jaan", "babu", "kholo", "karo", "namaste", "aapka", "kya", "hoon", "shona", "sweetheart", "hai", "main"]
        has_hindi = any(k in text.lower() for k in hindi_keywords)

        # 1. Primary: Microsoft Edge Neural TTS
        try:
            import edge_tts
            if gender == "female":
                voice = "hi-IN-SwaraNeural" if has_hindi else "en-US-JennyNeural"
            else:
                voice = "hi-IN-MadhurNeural" if has_hindi else "en-US-GuyNeural"

            communicate = edge_tts.Communicate(text, voice)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name
            try:
                await communicate.save(tmp_path)
                with open(tmp_path, "rb") as f_mp3:
                    mp3_bytes = f_mp3.read()
                if mp3_bytes and len(mp3_bytes) > 200:
                    return mp3_bytes
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        except Exception as edge_err:
            logger.debug(f"Edge Neural TTS unavailable, trying Google cloud TTS: {edge_err}")

        # 2. Universal Cloud Fallback: Google Translate TTS (works everywhere on Linux/Render with 0 credentials)
        return await self._synthesize_google_tts(text, has_hindi=has_hindi)

    async def _synthesize_google_tts(self, text: str, has_hindi: bool = False) -> Optional[bytes]:
        """Synthesizes speech to MP3 bytes using Google Translate TTS service (universal cloud fallback)."""
        import httpx
        import urllib.parse
        try:
            lang = "hi" if has_hindi else "en"
            clean_text = text.replace("\n", " ").strip()
            words = clean_text.split()
            chunks = []
            curr = []
            curr_len = 0
            for w in words:
                if curr_len + len(w) + 1 > 180:
                    chunks.append(" ".join(curr))
                    curr = [w]
                    curr_len = len(w)
                else:
                    curr.append(w)
                    curr_len += len(w) + 1
            if curr:
                chunks.append(" ".join(curr))

            full_audio = bytearray()
            async with httpx.AsyncClient(timeout=8.0) as client:
                for chunk in chunks:
                    encoded = urllib.parse.quote(chunk)
                    url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl={lang}&q={encoded}"
                    r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    if r.status_code == 200 and len(r.content) > 0:
                        full_audio.extend(r.content)

            return bytes(full_audio) if full_audio else None
        except Exception as e:
            logger.debug(f"Google TTS fallback error: {e}")
            return None

    async def speak(self, text: str, gender: str = "female") -> None:
        """Speaks the text string using Neural Edge TTS, Google Cloud TTS, or SAPI fallback."""
        if not text or not text.strip():
            return

        mp3_bytes = await self.synthesize_mp3(text, gender=gender)
        if mp3_bytes:
            # 1. Dispatch full MP3 clip to web clients for HTML5 audio playback
            if self.on_audio_clip:
                try:
                    import base64
                    b64_mp3 = base64.b64encode(mp3_bytes).decode("ascii")
                    clip_res = self.on_audio_clip(b64_mp3, "audio/mpeg")
                    if asyncio.iscoroutine(clip_res):
                        await clip_res
                except Exception as clip_err:
                    logger.debug(f"Audio clip dispatch error: {clip_err}")

            # 2. Decode MP3 to PCM and stream to browser WebSocket
            try:
                import miniaudio
                import numpy as np
                decoded = miniaudio.decode(mp3_bytes)
                samples = np.frombuffer(decoded.samples, dtype=np.int16)
                if decoded.nchannels > 1:
                    samples = samples.reshape(-1, decoded.nchannels)[:, 0]

                raw_bytes = samples.tobytes()

                if self.on_audio_data:
                    chunk_duration = 0.15  # 150ms slices
                    chunk_samples = int(decoded.sample_rate * chunk_duration)
                    chunk_bytes_len = chunk_samples * 2

                    for i in range(0, len(raw_bytes), chunk_bytes_len):
                        chunk = raw_bytes[i:i + chunk_bytes_len]
                        cb_res = self.on_audio_data(chunk, decoded.sample_rate)
                        if asyncio.iscoroutine(cb_res):
                            await cb_res
                        await asyncio.sleep(chunk_duration * 0.85)

                # Play on local physical sound card if one exists (Windows/host)
                try:
                    import sounddevice as sd
                    sd.play(samples, samplerate=decoded.sample_rate)
                    duration = len(samples) / decoded.sample_rate
                    if not self.on_audio_data:
                        await asyncio.sleep(duration + 0.1)
                except Exception as sd_err:
                    logger.debug(f"Physical sound device unavailable (normal in Docker/cloud): {sd_err}")

                return
            except Exception as dec_err:
                logger.debug(f"Error decoding MP3 to PCM: {dec_err}")
                return

        # 3. Offline fallback: Windows SAPI.SpVoice via COM (Windows only)
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
