"""
SHRUTI - Intelligent Voice Desktop Agent
==========================================
Main entry point that wires all subsystems together and launches the assistant.

Usage:
    python main.py

Requires:
    - GEMINI_API_KEY set in .env file or environment
    - Microphone and speakers connected
    - Windows OS
"""

import asyncio
import logging
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Logging setup ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet down noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

logger = logging.getLogger("shruti.main")


def print_banner() -> None:
    """Print the startup banner with system information."""
    from src.config import settings
    from src.tools.registry import tool_registry

    banner = r"""
    +--------------------------------------------------+
    |   _____  _   _ ______  _   _  _____  _____       |
    |  /  ___|| | | || ___ \| | | ||_   _||_   _|      |
    |  \ `--. | |_| || |_/ /| | | |  | |    | |        |
    |   `--. \|  _  ||    / | | | |  | |    | |        |
    |  /\__/ /| | | || |\ \ | |_| |  | |   _| |_       |
    |  \____/ \_| |_/\_| \_| \___/   \_/   \___/       |
    |                                                  |
    |      SHRUTI AI - Intelligent Voice Assistant     |
    +--------------------------------------------------+
    """
    print(banner)

    # API Key status
    key = settings.gemini_api_key
    if key and len(key) > 8:
        masked = f"{key[:4]}...{key[-4:]}"
    elif key:
        masked = "****"
    else:
        masked = "[NOT CONFIGURED - DEGRADED MODE]"
    print(f"  * Agent Name:       {settings.agent_name}")
    print(f"  * Language:         {settings.language_preference}")
    print(f"  * API Key:          {masked}")
    print(f"  * Model:            {settings.gemini_live_model}")
    print(f"  * Voice:            {settings.voice_name}")
    print(f"  * Registered Tools: {len(tool_registry.list_tools())}")
    print(f"  * Web UI:           http://localhost:{settings.web_ui_port}")
    print(f"  * Data Directory:   {settings.data_dir}")
    print("  " + "-" * 50)


async def main() -> None:
    """Initialize all subsystems and run the assistant."""
    from src.config import settings
    from src.audio.microphone import MicrophoneStream
    from src.audio.speaker import SpeakerOutput
    from src.audio.vad import VoiceActivityDetector
    from src.audio.wake_word import WakeWordDetector
    from src.gemini.live_client import GeminiLiveClient
    from src.agent.context import ContextManager
    from src.agent.orchestrator import AgentOrchestrator
    from src.ipc.server import IPCServer
    from src.security.permissions import permission_manager

    print_banner()

    # ── Validate API Key ──
    has_api_key = bool(settings.gemini_api_key and settings.gemini_api_key != "your_gemini_api_key_here")
    if not has_api_key:
        logger.warning(
            "GEMINI_API_KEY is not configured.\n"
            "  -> SHRUTI is starting in LOCAL DEGRADED MODE (Offline Task Execution & Local TTS).\n"
            "  -> Set GEMINI_API_KEY in .env to activate live cloud streaming at any time."
        )
    else:
        logger.info("GEMINI_API_KEY detected. Gemini Live bidirectional streaming enabled.")

    # ── Initialize Audio Subsystems ──
    logger.info("Initializing audio subsystems...")
    microphone = MicrophoneStream(
        sample_rate=settings.audio_input_sample_rate,
        channels=settings.audio_channels,
        chunk_size=settings.audio_chunk_size,
    )
    speaker = SpeakerOutput(
        sample_rate=settings.audio_output_sample_rate,
        channels=settings.audio_channels,
    )
    vad = VoiceActivityDetector(
        energy_threshold=settings.vad_energy_threshold,
        silence_duration=settings.vad_silence_duration,
        sample_rate=settings.audio_input_sample_rate,
        chunk_size=settings.audio_chunk_size,
    )
    wake_word = WakeWordDetector(sensitivity=settings.wake_word_sensitivity)
    if wake_word.enabled:
        logger.info("✅ Neural wake word detection active")
    else:
        logger.info("⚠️  Wake word detection unavailable — using VAD-based activation")

    # ── Initialize Gemini Live Client ──
    logger.info("Initializing Gemini Live client...")
    gemini_client = GeminiLiveClient(max_retries=settings.max_execution_retries)

    # ── Initialize Context & Agent ──
    context_manager = ContextManager()
    orchestrator = AgentOrchestrator(
        microphone=microphone,
        speaker=speaker,
        vad=vad,
        wake_word=wake_word,
        gemini=gemini_client,
        context=context_manager,
    )

    # ── Initialize IPC Server ──
    ipc_server = IPCServer()
    ipc_server.set_orchestrator(orchestrator)

    # ── Wire event callbacks ──
    async def on_orchestrator_event(event: dict) -> None:
        """Forward orchestrator events to all connected WebSocket clients."""
        await ipc_server.broadcast(event)

    orchestrator.on_event = on_orchestrator_event

    # Wire permission confirmation requests to IPC broadcast
    async def on_confirmation_requested(req) -> None:
        """Broadcast confirmation requests to UI."""
        await ipc_server.broadcast_event("confirmation_request", {
            "request_id": req.request_id,
            "tool_name": req.tool_name,
            "risk_level": req.risk_level.value,
            "description": req.action_description,
            "parameters": req.parameters,
            "expires_at": req.expires_at,
        })

    permission_manager.on_confirmation_requested = on_confirmation_requested

    # ── Launch Desktop App Window ──
    async def open_app_window(port: int, delay_sec: float = 1.2) -> None:
        """Auto-opens the desktop UI in Chrome/Edge app window mode or default browser."""
        await asyncio.sleep(delay_sec)
        import shutil
        import subprocess
        import webbrowser
        from pathlib import Path

        url = f"http://localhost:{port}"

        # Try launching Edge or Chrome in standalone app mode (native frameless window)
        app_candidates = [
            shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            shutil.which("chrome"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]

        for exe in app_candidates:
            if exe and Path(exe).exists():
                try:
                    subprocess.Popen([exe, f"--app={url}", "--window-size=1260,820"])
                    logger.info(f"Launched SHRUTI desktop window via {Path(exe).name}")
                    return
                except Exception:
                    pass

        try:
            webbrowser.open(url)
        except Exception as err:
            logger.debug(f"Failed to auto-open browser: {err}")

    # ── Launch ──
    logger.info("Starting SHRUTI...")
    print(f"\n  >> Open http://localhost:{settings.web_ui_port} in your browser <<\n")
    asyncio.create_task(open_app_window(settings.web_ui_port))

    try:
        await asyncio.gather(
            ipc_server.start_async(),
            orchestrator.start(),
        )
    except asyncio.CancelledError:
        logger.info("Main loop cancelled.")
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        logger.info("Shutting down SHRUTI...")
        await orchestrator.stop()
        await ipc_server.stop()
        context_manager.save_preferences()
        logger.info("SHRUTI stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Shutdown requested (Ctrl+C). Goodbye! 👋")
        sys.exit(0)
