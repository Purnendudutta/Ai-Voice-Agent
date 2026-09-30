"""
AI Voice Desktop Assistant - System Configuration Module
"""

import os
import secrets
from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Strongly typed application configuration."""
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Base Paths
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR

    # Gemini API & Live Model
    agent_name: str = Field(default="Shruti", validation_alias="AGENT_NAME")
    persona_mode: str = Field(default="romantic_girlfriend", validation_alias="PERSONA_MODE")
    language_preference: str = Field(default="auto", validation_alias="LANGUAGE_PREFERENCE")  # auto, hindi, english
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_live_model: str = Field(
        default="gemini-3.1-flash-live-preview",
        validation_alias="GEMINI_LIVE_MODEL"
    )
    voice_name: str = Field(default="Aoede", validation_alias="VOICE_NAME")  # Aoede, Charon, Fenrir, Kore, Puck

    # Audio & Streaming
    audio_input_sample_rate: int = 16000
    audio_output_sample_rate: int = 24000
    audio_channels: int = 1
    audio_chunk_size: int = 1024
    vad_energy_threshold: float = 0.015
    vad_silence_duration: float = 0.8

    # Wake Word Engine
    wake_word_enabled: bool = True
    wake_words: List[str] = Field(
        default_factory=lambda: ["hello", "hi", "hey", "shruti", "jarvis", "gemini", "computer", "assistant"]
    )
    wake_word_sensitivity: float = 0.65

    # Security & IPC Layer
    ipc_secret_key: str = Field(
        default_factory=lambda: secrets.token_hex(32),
        validation_alias="IPC_SECRET_KEY"
    )
    ipc_host: str = "127.0.0.1"
    ipc_port: int = 8765
    web_ui_port: int = 8000
    allow_critical_operations_with_confirmation: bool = True
    max_execution_retries: int = 3
    tool_timeout_seconds: float = 15.0
    rate_limit_calls_per_minute: int = 60

    # Persistence & Audit
    audit_log_file: Path = DATA_DIR / "audit.jsonl"
    memory_db_file: Path = DATA_DIR / "agent_memory.db"
    degraded_mode_enabled: bool = True

    # Desktop Permissions & Full Computer Access
    full_computer_access: bool = Field(
        default=True,
        validation_alias="FULL_COMPUTER_ACCESS"
    )
    require_confirmation_for_high_risk: bool = Field(
        default=False,
        validation_alias="REQUIRE_CONFIRMATION_FOR_HIGH_RISK"
    )
    cursor_speed: float = 0.2
    prohibited_commands: List[str] = Field(
        default_factory=lambda: [
            "format", "del /s /q c:\\", "rmdir /s /q c:\\",
            "diskpart", "reg delete hklm", "bcdedit"
        ]
    )

    def model_post_init(self, __context):
        """Loads API key from fallback file if not provided in environment."""
        if not self.gemini_api_key or self.gemini_api_key == "your_gemini_api_key_here":
            key_file = self.data_dir / "api_key.txt"
            if key_file.exists():
                try:
                    loaded = key_file.read_text(encoding="utf-8").strip()
                    if loaded and loaded != "your_gemini_api_key_here":
                        self.gemini_api_key = loaded
                except Exception:
                    pass


settings = Settings()


def save_api_key(new_key: str) -> None:
    """Persists the Gemini API key in settings, data/api_key.txt, and .env."""
    key = new_key.strip()
    settings.gemini_api_key = key
    os.environ["GEMINI_API_KEY"] = key

    # Save to data_dir/api_key.txt
    try:
        key_file = settings.data_dir / "api_key.txt"
        key_file.write_text(key, encoding="utf-8")
    except Exception:
        pass

    # Save to .env
    try:
        env_file = settings.base_dir / ".env"
        lines = []
        found = False
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("GEMINI_API_KEY="):
                    lines.append(f"GEMINI_API_KEY={key}")
                    found = True
                else:
                    lines.append(line)
        if not found:
            lines.append(f"GEMINI_API_KEY={key}")
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass

