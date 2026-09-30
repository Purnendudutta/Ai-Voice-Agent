import pytest
import numpy as np
from src.audio.vad import VoiceActivityDetector, VADEvent
from src.audio.wake_word import WakeWordDetector
from src.audio.microphone import MicrophoneStream
from src.audio.speaker import SpeakerOutput


def test_vad_silence():
    vad = VoiceActivityDetector()
    silence_pcm = np.zeros(1024, dtype=np.int16).tobytes()
    event = vad.process_chunk(silence_pcm)
    assert event == VADEvent.SILENCE


def test_vad_speech():
    vad = VoiceActivityDetector(energy_threshold=0.015)
    # Generate high amplitude sine wave (simulating loud speech)
    t = np.linspace(0, 1, 1024)
    loud_pcm = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16).tobytes()
    event1 = vad.process_chunk(loud_pcm)
    assert event1 == VADEvent.SPEECH_START
    event2 = vad.process_chunk(loud_pcm)
    assert event2 == VADEvent.SPEECH_CONTINUE


def test_wake_word_detector():
    ww = WakeWordDetector()
    assert isinstance(ww.enabled, bool)


def test_microphone_instantiation():
    mic = MicrophoneStream()
    assert mic is not None
    assert mic.sample_rate == 16000
    assert mic.is_active is False


def test_speaker_instantiation():
    speaker = SpeakerOutput()
    assert speaker is not None
    assert speaker.sample_rate == 24000
    assert speaker.is_playing is False


def test_local_tts_callback():
    from src.audio.local_tts import LocalTTS
    tts = LocalTTS()
    received_chunks = []

    def mock_cb(chunk: bytes, rate: int):
        received_chunks.append((chunk, rate))

    tts.set_audio_callback(mock_cb)
    assert tts.on_audio_data is mock_cb
