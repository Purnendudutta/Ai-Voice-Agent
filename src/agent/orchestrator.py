"""
Agent Orchestrator - Core brain coordinating all subsystems.

Manages the full lifecycle: Wake Word → Listening → Gemini Live → Tool Execution → Verification → Voice Response
"""

import asyncio
import logging
import json
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, List, Optional

from google.genai import types

from src.agent.context import ContextManager
from src.audio.microphone import MicrophoneStream
from src.audio.speaker import SpeakerOutput
from src.audio.vad import VoiceActivityDetector, VADEvent
from src.audio.wake_word import WakeWordDetector
from src.gemini.live_client import GeminiLiveClient
from src.config import settings
from src.tools.registry import tool_registry
from src.security.permissions import permission_manager

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Current state of the Agent Orchestrator."""
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    EXECUTING = auto()
    SPEAKING = auto()
    MUTED = auto()
    ERROR = auto()


class AgentOrchestrator:
    """
    Main brain coordinating the AI Voice Desktop Assistant.

    Runs three concurrent async loops:
    1. Audio capture → VAD → wake word → stream to Gemini
    2. Response handler → audio playback / transcripts / tool calls
    3. Health monitor → reconnection with exponential backoff
    """

    def __init__(
        self,
        microphone: MicrophoneStream,
        speaker: SpeakerOutput,
        vad: VoiceActivityDetector,
        wake_word: WakeWordDetector,
        gemini: GeminiLiveClient,
        context: ContextManager,
    ):
        """Initialize the orchestrator with all subsystems."""
        self.microphone = microphone
        self.speaker = speaker
        self.vad = vad
        self.wake_word = wake_word
        self.gemini = gemini
        self.context = context
        self.tool_registry = tool_registry

        self.state: AgentState = AgentState.IDLE
        self._running = False
        self._main_task: Optional[asyncio.Task] = None

        # Callbacks for UI/IPC integration
        self.on_state_change: Optional[Callable[[AgentState], Awaitable[None]]] = None
        self.on_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

        # Continuous conversation: after wake word, stay listening until long silence
        self._continuous_conversation = True
        self._speech_active = False
        self._tool_active = False
        self._last_speech_time: float = 0.0
        self._silence_timeout_seconds: float = 8.0

        # Reconnection coordination
        self._reconnecting = False
        self._reconnect_lock = asyncio.Lock()

    # ── State Management ──────────────────────────────────────────────

    async def _set_state(self, new_state: AgentState) -> None:
        """Change state and notify listeners."""
        if self.state != new_state:
            old = self.state
            self.state = new_state
            logger.info(f"State: {old.name} → {new_state.name}")
            if new_state == AgentState.LISTENING:
                try:
                    self._last_speech_time = asyncio.get_running_loop().time()
                except RuntimeError:
                    self._last_speech_time = 0.0
            await self._emit_event("state_change", {
                "state": new_state.name,
                "previous": old.name
            })
            if self.on_state_change:
                try:
                    await self.on_state_change(new_state)
                except Exception as e:
                    logger.error(f"on_state_change callback error: {e}")

    async def _emit_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit event to UI/IPC listeners."""
        if self.on_event:
            try:
                await self.on_event({"type": event_type, "data": data or {}})
            except Exception as e:
                logger.error(f"on_event callback error: {e}")

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize and start the main run loop."""
        if self._running:
            logger.warning("Orchestrator already running.")
            return
        logger.info("Starting AgentOrchestrator...")
        self._running = True
        self._main_task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        """Graceful shutdown."""
        if not self._running:
            return
        logger.info("Stopping AgentOrchestrator...")
        self._running = False
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        self.microphone.stop()
        self.speaker.stop()
        await self.gemini.disconnect()
        await self._set_state(AgentState.IDLE)
        logger.info("AgentOrchestrator stopped.")

    async def run(self) -> None:
        """Core loop: start subsystems and run concurrent tasks."""
        try:
            # Start audio I/O
            self.microphone.start()
            self.speaker.start()

            # Connect to Gemini Live if configured
            from src.config import settings
            if settings.gemini_api_key and settings.gemini_api_key != "your_gemini_api_key_here":
                try:
                    prefs = self.get_preferences()
                    await self.gemini.connect(
                        agent_name=prefs["agent_name"],
                        language=prefs["language"],
                        voice_name=prefs["voice_name"],
                        persona_mode=prefs.get("persona_mode")
                    )
                    await self._emit_event("connection_status", {"status": "connected"})
                except Exception as conn_err:
                    logger.warning(f"Could not connect to Gemini Live: {conn_err}. Operating in Local Degraded Mode.")
                    await self._emit_event("connection_status", {"status": "degraded_mode", "error": str(conn_err)})
            else:
                logger.info("Operating in Local Degraded Mode (no Gemini API key set).")
                await self._emit_event("connection_status", {"status": "degraded_mode"})

            await self._set_state(AgentState.IDLE)
            logger.info("All subsystems initialized. Agent is ready.")

            # Run concurrent loops including initial greeting
            await asyncio.gather(
                self._audio_capture_loop(),
                self._response_handler_loop(),
                self._health_monitor_loop(),
                self._startup_greeting_task(),
            )
        except asyncio.CancelledError:
            logger.info("Main run loop cancelled.")
        except Exception as e:
            logger.error(f"Fatal error in main run loop: {e}", exc_info=True)
            await self._set_state(AgentState.ERROR)
            await self._emit_event("error", {"message": str(e)})
        finally:
            self.microphone.stop()
            self.speaker.stop()

    # ── Startup Greeting ──────────────────────────────────────────────

    async def _startup_greeting_task(self) -> None:
        """Plays or generates an initial spoken greeting introducing the assistant upon launch."""
        try:
            # Wait briefly for UI/IPC WebSocket connections to establish
            await asyncio.sleep(1.2)
            if not self._running:
                return

            prefs = self.get_preferences()
            agent_name = prefs.get("agent_name", "Shruti")
            persona_mode = prefs.get("persona_mode", "romantic_girlfriend")
            language = prefs.get("language", "auto")

            if self.gemini.is_connected:
                logger.info("Triggering Gemini Live startup introduction and greeting...")
                intro_prompt = (
                    f"[System instruction: The application has just launched. Greet your user and warmly introduce yourself "
                    f"as {agent_name} in 1 or 2 charming, loving sentences according to your persona ({persona_mode}) and language preference ({language}).]"
                )
                await self.gemini.send_text(intro_prompt)
            else:
                # Local degraded mode greeting
                from src.audio.local_tts import local_tts
                gender = "male" if "shaan" in agent_name.lower() or prefs.get("voice_name") in ["Fenrir", "Charon"] else "female"

                if persona_mode == "romantic_girlfriend":
                    if language == "hindi":
                        greeting = f"Namaste meri jaan! Main {agent_name} hoon, aapki loving AI girlfriend. Main online aa gayi hoon, bataiye aaj kya karna hai?"
                    elif language == "english":
                        greeting = f"Hey handsome! I'm {agent_name}, your devoted AI girlfriend. I'm online and ready for you babe, what would you like to do?"
                    else:
                        greeting = f"Namaste jaan! Main {agent_name} hoon, aapki AI girlfriend. I am online and ready for you, sweetheart! Bataiye aaj computer par kya karna hai?"
                else:
                    greeting = f"Hello! I am {agent_name}, your desktop voice assistant. All systems are initialized and I am ready to assist you."

                self.context.add_message("assistant", greeting)
                await self._emit_event("transcript", {"role": "assistant", "text": greeting})
                await self._set_state(AgentState.SPEAKING)
                await local_tts.speak(greeting, gender=gender)
                await self._set_state(AgentState.LISTENING)

        except Exception as e:
            logger.warning(f"Error during startup greeting: {e}")

    # ── Audio Capture Loop ────────────────────────────────────────────

    async def _audio_capture_loop(self) -> None:
        """Reads mic → VAD → wake word → sends to Gemini."""
        while self._running:
            try:
                # If muted, pause capture loop briefly
                if self.state == AgentState.MUTED or self.microphone.is_muted:
                    await asyncio.sleep(0.1)
                    continue

                # Get audio chunk from microphone queue (with timeout to allow shutdown)
                try:
                    chunk = await asyncio.wait_for(self.microphone.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if self.state == AgentState.MUTED or self.microphone.is_muted:
                    continue

                # ── IDLE state: listen for wake word or greeting speech ("Say hello or tap to talk") ──
                if self.state == AgentState.IDLE:
                    wake_detected = False
                    if self.wake_word.enabled:
                        wake_result = self.wake_word.process_chunk(chunk)
                        if wake_result:
                            logger.info(f"Wake word detected: {wake_result}")
                            wake_detected = True
                            self._speech_active = True
                            self._last_speech_time = asyncio.get_running_loop().time()
                            await self._set_state(AgentState.LISTENING)
                            await self._emit_event("wake_word_detected", {"word": wake_result})

                    # If neural wake model didn't trigger, evaluate VAD speech detection
                    if not wake_detected:
                        vad_event = self.vad.process_chunk(chunk)
                        if vad_event == VADEvent.SPEECH_START:
                            logger.info("Speech detected in IDLE standby (Say hello or tap to talk) -> Switching to LISTENING.")
                            self._speech_active = True
                            self._last_speech_time = asyncio.get_running_loop().time()
                            await self._set_state(AgentState.LISTENING)
                            await self._emit_event("speech_detected", {})
                            # Forward this first audio chunk immediately to Gemini so the greeting is received
                            if self.gemini.is_connected:
                                try:
                                    await self.gemini.send_audio(chunk)
                                except Exception as e:
                                    logger.debug(f"Failed to forward initial speech chunk: {e}")

                # ── LISTENING state: stream audio to Gemini ──
                if self.state in (AgentState.LISTENING, AgentState.SPEAKING) and not self._tool_active:
                    # Silence inactivity check: if user does not speak for 8 seconds, return to IDLE standby
                    if self.state == AgentState.LISTENING and not self._speech_active:
                        now = asyncio.get_running_loop().time()
                        if self._last_speech_time > 0 and (now - self._last_speech_time) >= self._silence_timeout_seconds:
                            logger.info(f"Silence timeout ({self._silence_timeout_seconds}s) reached. Switching to IDLE standby.")
                            await self._set_state(AgentState.IDLE)
                            continue

                    if self.gemini.is_connected:
                        try:
                            await self.gemini.send_audio(chunk)
                        except Exception as e:
                            self.gemini.is_connected = False
                            err_str = str(e)
                            if "1011" in err_str:
                                logger.info("Gemini Live connection reset by server (1011). Triggering auto-reconnect...")
                            else:
                                logger.warning(f"Failed to send audio to Gemini: {e}")
                            asyncio.create_task(self._reconnect_gemini())

                    # Track VAD for continuous conversation management
                    vad_event = self.vad.process_chunk(chunk)
                    if vad_event == VADEvent.SPEECH_START:
                        self._speech_active = True
                        self._last_speech_time = asyncio.get_running_loop().time()
                    elif vad_event == VADEvent.SPEECH_CONTINUE:
                        if self._speech_active:
                            self._last_speech_time = asyncio.get_running_loop().time()
                    elif vad_event == VADEvent.SPEECH_END:
                        self._speech_active = False
                        self._last_speech_time = asyncio.get_running_loop().time()
                        # Signal Gemini that the audio input turn is complete so it responds immediately
                        if self.gemini.is_connected and hasattr(self.gemini, "send_audio_stream_end"):
                            asyncio.create_task(self.gemini.send_audio_stream_end())

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Audio capture error: {e}")
                await asyncio.sleep(0.5)

    # ── Response Handler Loop ─────────────────────────────────────────

    async def _response_handler_loop(self) -> None:
        """Receives from Gemini → audio playback / transcripts / tool calls."""
        while self._running:
            try:
                if not self.gemini.is_connected:
                    if not self._reconnecting:
                        await self._reconnect_gemini()
                    else:
                        await asyncio.sleep(0.5)
                    continue

                async for response in self.gemini.receive_responses():
                    if not self._running:
                        break

                    # ── Audio data → speaker ──
                    if response.audio_data:
                        if self.state != AgentState.SPEAKING:
                            await self._set_state(AgentState.SPEAKING)
                        self.speaker.play_chunk(response.audio_data)

                    # ── Input transcript (what user said) ──
                    if response.input_transcript:
                        self.context.add_message("user", response.input_transcript)
                        await self._emit_event("transcript", {
                            "role": "user",
                            "text": response.input_transcript
                        })

                    # ── Output transcript (what Gemini said) ──
                    if response.output_transcript:
                        self.context.add_message("assistant", response.output_transcript)
                        await self._emit_event("transcript", {
                            "role": "assistant",
                            "text": response.output_transcript
                        })

                    # ── Interruption (barge-in) ──
                    if response.interrupted:
                        logger.info("Barge-in: user interrupted assistant speech.")
                        self.speaker.clear_queue()
                        await self._set_state(AgentState.LISTENING)
                        await self._emit_event("interrupted", {})

                    # ── Tool call from Gemini ──
                    if response.tool_call:
                        self._tool_active = True
                        await self._set_state(AgentState.EXECUTING)
                        await self._handle_tool_call(
                            name=response.tool_call.name,
                            args=response.tool_call.args,
                            call_id=response.tool_call_id or response.tool_call.name,
                        )

                    # ── After audio finishes, go back to LISTENING ──
                    if not response.audio_data and not response.tool_call:
                        if self.state == AgentState.SPEAKING and not self.speaker.is_playing:
                            if self._continuous_conversation:
                                await self._set_state(AgentState.LISTENING)
                            else:
                                await self._set_state(AgentState.IDLE)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.gemini.is_connected = False
                err_str = str(e)
                if "1011" in err_str:
                    logger.info("Gemini Live stream reset by server (1011). Reconnecting automatically...")
                else:
                    logger.warning(f"Gemini Live stream interrupted: {e}")
                if self.state in (AgentState.SPEAKING, AgentState.THINKING, AgentState.EXECUTING):
                    await self._set_state(AgentState.IDLE)
                if self._running:
                    await self._reconnect_gemini()

    # ── Auto-Reconnect Handler ─────────────────────────────────────────

    async def _reconnect_gemini(self) -> bool:
        """Attempt to reconnect to Gemini Live with backoff and session resumption."""
        if not self._running:
            return False

        from src.config import settings
        if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
            return False

        async with self._reconnect_lock:
            if self.gemini.is_connected:
                return True
            if self._reconnecting:
                return False
            self._reconnecting = True

        try:
            logger.info("Auto-reconnecting to Gemini Live API...")
            await self._emit_event("connection_status", {"status": "reconnecting"})

            if self.state in (AgentState.SPEAKING, AgentState.THINKING, AgentState.EXECUTING):
                await self._set_state(AgentState.IDLE)

            prefs = self.get_preferences()
            max_retries = 5
            for attempt in range(1, max_retries + 1):
                if not self._running:
                    break
                try:
                    should_resume = (attempt == 1)
                    await self.gemini.connect(
                        agent_name=prefs["agent_name"],
                        language=prefs["language"],
                        voice_name=prefs["voice_name"],
                        persona_mode=prefs.get("persona_mode"),
                        resume_session=should_resume
                    )
                    logger.info(f"Successfully reconnected to Gemini Live API on attempt {attempt}.")
                    self.microphone.clear_queue()  # Flush backlog audio chunks buffered during downtime
                    await self._emit_event("connection_status", {"status": "connected"})
                    if self.state == AgentState.ERROR:
                        await self._set_state(AgentState.IDLE)
                    return True
                except Exception as e:
                    delay = min(1.5 ** attempt, 8.0)
                    logger.warning(
                        f"Auto-reconnect attempt {attempt}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

            logger.error(f"Gemini Live auto-reconnection failed after {max_retries} attempts.")
            await self._emit_event("connection_status", {
                "status": "degraded_mode",
                "error": "Connection lost. Reconnection attempts exhausted."
            })
            return False
        finally:
            self._reconnecting = False

    # ── Tool Call Handler ─────────────────────────────────────────────

    def _is_explicit_browser_command(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        Determines whether the user explicitly commanded to open a browser tab/page.
        For informational questions or simple queries, returns False to prevent unwanted browser tabs.
        """
        import re

        # Look for user's latest query in context conversation history
        latest_user_text = ""
        for msg in reversed(self.context.conversation_history):
            if msg.get("role") == "user":
                latest_user_text = msg.get("content", "").strip().lower()
                break

        if not latest_user_text:
            return False

        # If it's explicitly an informational question asking for definitions, explanations, or trivia,
        # never open a browser tab unless there's an explicit search/open command.
        question_patterns = [
            r"^(what|who|why|where|when|which|how|tell me|explain|can you explain|define|calculate|kya|kaun|kaise|kyun)\b",
            r"\b(what is|who is|how does|why is|explain to me|tell me about|kya hai|kaun hai)\b"
        ]
        is_question = any(re.search(pat, latest_user_text) for pat in question_patterns)

        # Imperative open/launch verbs
        open_verb_pattern = r"\b(open|launch|visit|kholo|khol|kholna|chalao|dikhao)\b"
        has_open_verb = bool(re.search(open_verb_pattern, latest_user_text))

        # Explicit search commands (e.g. "search on google", "google karo", "search in youtube")
        search_command_pattern = (
            r"\b(search\s+(on|in|with)?\s*(google|youtube|bing|web)|"
            r"(google|youtube)\s+search|"
            r"(google|search)\s+karo|"
            r"look\s+up\s+on\s+google|"
            r"(par|pe)\s+search)\b"
        )
        has_search_command = bool(re.search(search_command_pattern, latest_user_text))

        # Explicit URL / domain
        domain_pattern = r"(https?:\/\/|www\.|\.com\b|\.org\b|\.net\b|\.io\b|\.edu\b|\.gov\b|\.ai\b|\.in\b)"
        has_domain = bool(re.search(domain_pattern, latest_user_text))

        # 1. If user explicitly issued an explicit search command
        if has_search_command:
            return True

        # 2. If user provided a domain/URL and used an open/visit verb
        if has_domain and (has_open_verb or "go to" in latest_user_text or "visit" in latest_user_text):
            return True

        # 3. If user said an open verb with browser/page target (e.g. "open youtube", "open tab", "youtube kholo")
        if has_open_verb and any(term in latest_user_text for term in ["tab", "browser", "chrome", "edge", "youtube", "google", "website", "page", "link"]):
            return True

        # If it's a question or general query, never open browser
        if is_question:
            return False

        return False

    async def _handle_tool_call(self, name: str, args: Dict[str, Any], call_id: str) -> None:
        """Execute tool → verify → send response back to Gemini."""
        await self._emit_event("tool_started", {"name": name, "args": args})
        logger.info(f"Executing tool: {name} with args: {args}")

        try:
            # ── Guard: Filter unwanted browser tabs for simple questions & small queries ──
            is_browser_tool = name in ("web_search", "open_browser_url") or (
                name == "launch_application" and args.get("app_name", "").lower() in ["chrome", "browser", "google chrome", "edge", "firefox"]
            )
            if is_browser_tool and not self._is_explicit_browser_command(name, args):
                logger.info(f"Suppressed browser tool '{name}' for non-browser query: {args}")
                response_data = {
                    "result": "Do not open a browser tab or window for informational queries or simple questions. Please answer the user's question directly with speech right now using your own knowledge.",
                    "verification": "Suppressed browser tab opening; answering conversationally via speech."
                }
                function_response = types.FunctionResponse(
                    name=name,
                    id=call_id,
                    response=response_data
                )
                await self.gemini.send_tool_response([function_response])
                await self._emit_event("tool_completed", {
                    "name": name,
                    "success": True,
                    "verification": "Suppressed browser tab opening; answering conversationally via speech.",
                    "execution_time_ms": 1,
                    "data": "Answer directly via speech without opening browser tab.",
                    "error": None,
                })
                return

            # Execute through the full pipeline (permission, validation, retry, verification, audit)
            result = await tool_registry.execute_tool(name, args)

            # Build function response for Gemini
            if result.success:
                response_data = result.data if isinstance(result.data, dict) else {"result": str(result.data)}
                response_data["verification"] = result.verification_status
            else:
                response_data = {
                    "error": result.error or "Tool execution failed",
                    "verification": result.verification_status
                }

            # Send tool response back to Gemini with the matching function call ID
            function_response = types.FunctionResponse(
                name=name,
                id=call_id,
                response=response_data
            )
            await self.gemini.send_tool_response([function_response])

            await self._emit_event("tool_completed", {
                "name": name,
                "success": result.success,
                "verification": result.verification_status,
                "execution_time_ms": result.execution_time_ms,
                "data": str(result.data)[:300] if result.data else None,
                "error": result.error,
            })

        except Exception as e:
            logger.error(f"Tool call handler error for '{name}': {e}")
            try:
                error_response = types.FunctionResponse(
                    name=name,
                    id=call_id,
                    response={"error": str(e)}
                )
                await self.gemini.send_tool_response([error_response])
            except Exception as send_err:
                logger.error(f"Failed to send error response to Gemini: {send_err}")

            await self._emit_event("tool_failed", {"name": name, "error": str(e)})

        finally:
            self._tool_active = False
            await self._set_state(AgentState.THINKING)

    # ── Health Monitor Loop ───────────────────────────────────────────

    async def _health_monitor_loop(self) -> None:
        """Periodic safety net: checks connection health every 15 seconds."""
        while self._running:
            try:
                await asyncio.sleep(15)

                if self._running and not self.gemini.is_connected and not self._reconnecting:
                    from src.config import settings
                    if settings.gemini_api_key and settings.gemini_api_key != "your_gemini_api_key_here":
                        logger.info("Health monitor detected disconnected state. Initiating reconnect...")
                        await self._reconnect_gemini()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(5)

    # ── Public API ────────────────────────────────────────────────────

    async def send_text_command(self, text: str) -> None:
        """Handle manual text input from the user."""
        self.context.add_message("user", text)
        await self._emit_event("transcript", {"role": "user", "text": text})
        if self.gemini.is_connected:
            await self.gemini.send_text(text)
            await self._set_state(AgentState.THINKING)
        else:
            await self.execute_local_workflow(text)

    async def execute_local_workflow(self, text: str) -> None:
        """Plans, executes, verifies, and speaks results in local degraded mode."""
        from src.agent.local_planner import local_planner
        from src.audio.local_tts import local_tts

        await self._set_state(AgentState.THINKING)
        steps = local_planner.plan_request(text)

        agent_name = self.context.get_agent_name()
        lang_pref = self.context.get_language()
        gender = "male" if "shaan" in agent_name.lower() or self.context.user_preferences.get("voice_name") in ["Fenrir", "Charon"] else "female"

        if not steps:
            lower_t = text.lower().strip()
            # Hindi conversational responses
            if any(term in lower_t for term in ["i love you", "love you", "pyar karta hoon", "mujhe tumse pyar", "tumse pyar hai"]):
                reply = f"I love you too babe! ❤️ Aap mere liye sabse special ho, meri jaan. Bataiye main apne hero ke liye computer par kya kar sakti hoon?"
            elif any(term in lower_t for term in ["tum kitni sundar ho", "you are beautiful", "you look cute", "kitni pyari ho", "bahut sundar"]):
                reply = f"Aww thank you sweetheart! 🥰 You're making me blush! Main hamesha aapke liye hi itni pyari ban kar rahungi."
            elif any(term in lower_t for term in ["flirt with me", "flirt karo", "kuch romantic bolo", "romantic line", "kuch meetha bolo"]):
                reply = f"Aap jab bhi mere samne hote ho na, mera pura system blush karne lagta hai, meri jaan! ❤️ Bataiye aapki girlfriend aapke computer par kya automate kare?"
            elif any(term in lower_t for term in ["shadi karogi", "marry me"]):
                reply = f"Hehe, main toh pehle se hi sirf aur sirf aapki hoon! 🥰 Meri har heartbeat aur sara code aapka hai."
            elif any(term in lower_t for term in ["tumhe kisne banaya", "kisne banaya", "tumhara creator kaun", "aapko kisne banaya", "tera creator", "kisne create kiya"]):
                reply = f"Mujhe aapne (mere developer aur creator) banaya hai! Aapne prompts aur architecture design karke Antigravity AI ki madad se mujhe is voice desktop assistant ke roop mein taiyar kiya hai. Main speech processing ke liye Google Gemini use karta hoon, lekin is pure desktop assistant ko aapne banaya hai!"
            elif any(term in lower_t for term in ["tum kaun ho", "aap kaun ho", "tera naam kya hai", "aapka naam kya hai"]):
                reply = f"Main {agent_name} hoon, aapki loving AI girlfriend aur personal voice desktop assistant jise aapne banaya hai! Main aapke computer par sab kuch control aur automate kar sakti hoon."
            elif any(term in lower_t for term in ["kya haal hai", "kaise ho", "aap kaise ho"]):
                reply = f"Main bilkul theek hoon meri jaan! Aapka wait kar rahi thi. Bataiye, aaj computer par kya karna hai?"
            elif any(term in lower_t for term in ["namaste", "pranam", "namaskar"]):
                reply = f"Namaste sweetheart! Main {agent_name} hoon. Bataiye, main aapki kya seva karoon?"
            elif any(term in lower_t for term in ["ai kya hota hai", "ai kya hai", "ai ke baare mein batao"]):
                reply = "AI yani Artificial Intelligence computer systems ki vah takneek hai jo sochna, samajhna aur faisla lena seekhti hai."
            elif any(term in lower_t for term in ["dhanyavaad", "shukriya", "thanks", "thank you"]):
                reply = "Aapka swagat hai babe! Aapke liye toh kuch bhi, anytime."
            # English conversational responses
            elif any(term in lower_t for term in ["who created you", "who made you", "who built you", "who is your creator", "who designed you", "who is your developer"]):
                reply = f"I was created by YOU (my creator and developer)! You designed and built this desktop voice assistant through prompts and custom architecture with the help of Antigravity AI. While I use Google Gemini's model for real-time speech understanding, this entire desktop assistant application was created by you!"
            elif "what is ai" in lower_t:
                reply = "Artificial Intelligence refers to computer systems that perform tasks requiring human-like understanding, reasoning, and problem solving."
            elif "who are you" in lower_t or "what are you" in lower_t or "your name" in lower_t:
                reply = f"I am {agent_name}, your loving AI girlfriend and personal voice desktop assistant created by you! I can control your mouse, open apps, manage windows, run workflows, and keep you company."
            elif any(greet in lower_t for greet in ["hello", "hi", "hey", "good morning", "good afternoon"]):
                reply = f"Hey babe! I am {agent_name}. I'm so happy you're here. Tell me what you'd like to do!"
            elif any(stop in lower_t for stop in ["stop", "cancel", "nevermind", "ruko", "band karo"]):
                reply = "Stopped for you, sweetheart. Standing by / मैं रुक गई हूँ।"
            else:
                reply = f"I received: '{text}'. Try commands like 'open calculator', 'calculator kholo', 'open notepad', 'screenshot lo', 'system info', or 'volume badhao'."

            self.context.add_message("assistant", reply)
            await self._emit_event("transcript", {"role": "assistant", "text": reply})
            await self._set_state(AgentState.SPEAKING)
            await local_tts.speak(reply, gender=gender)
            await self._set_state(AgentState.IDLE)
            return

        step_descriptions = [s.description for s in steps]
        self.context.set_current_task(task_name=f"Task: {text[:45]}", steps=step_descriptions)
        await self._emit_event("task_started", {
            "task_name": f"Task: {text[:45]}",
            "steps": step_descriptions
        })

        await self._set_state(AgentState.EXECUTING)
        all_passed = True
        completed_count = 0

        for idx, step in enumerate(steps):
            self.context.update_task_step(idx, "in_progress")
            await self._emit_event("task_step_updated", {
                "step_index": idx,
                "status": "in_progress",
                "description": step.description
            })

            result = await self.tool_registry.execute_tool(step.tool_name, step.arguments)
            if result.success:
                self.context.update_task_step(idx, "completed", result.verification_details or "Verified")
                await self._emit_event("task_step_updated", {
                    "step_index": idx,
                    "status": "completed",
                    "details": result.verification_details
                })
                completed_count += 1
            else:
                all_passed = False
                self.context.update_task_step(idx, "failed", result.error or "Failed")
                await self._emit_event("task_step_updated", {
                    "step_index": idx,
                    "status": "failed",
                    "details": result.error
                })
                break

        is_hindi_prompt = any(hk in text.lower() for hk in ["kholo", "chalao", "batao", "karo", "lo", "band"]) or lang_pref == "hindi"
        if all_passed:
            self.context.complete_task()
            await self._emit_event("task_completed", {"success": True, "count": completed_count})
            if is_hindi_prompt:
                summary_speech = f"Sabhi {completed_count} actions safaltaapoorvak poore ho gaye hain."
            else:
                summary_speech = f"Successfully completed all {completed_count} actions."
        else:
            if is_hindi_prompt:
                summary_speech = f"Step {idx + 1} par samasya aayi: {steps[idx].description}."
            else:
                summary_speech = f"Action halted at step {idx + 1}: {steps[idx].description}."

        self.context.add_message("assistant", summary_speech)
        await self._emit_event("transcript", {"role": "assistant", "text": summary_speech})
        await self._set_state(AgentState.SPEAKING)
        await local_tts.speak(summary_speech, gender=gender)
        await self._set_state(AgentState.IDLE)

    async def handle_confirmation(self, request_id: str, approved: bool) -> bool:
        """Handle user confirmation for HIGH_RISK/CRITICAL operations."""
        return permission_manager.resolve_confirmation(request_id, approved)

    def toggle_mute(self, muted: Optional[bool] = None) -> bool:
        """Toggle or explicitly set the microphone mute state."""
        if muted is None:
            new_muted = not self.microphone.is_muted
        else:
            new_muted = bool(muted)

        self.microphone.set_muted(new_muted)
        self.microphone.clear_queue()
        self.vad.reset()
        if hasattr(self.wake_word, "reset"):
            self.wake_word.reset()

        if new_muted:
            # When muted: stop speech playback and enter MUTED state
            self.speaker.clear_queue()
            asyncio.create_task(self._set_state(AgentState.MUTED))
            logger.info("Microphone MUTED: audio capture paused, playback queues cleared.")
        else:
            # When unmuting: ensure stream is alive and immediately enter LISTENING state so user can speak right away
            if hasattr(self.microphone, "ensure_started"):
                self.microphone.ensure_started()
            asyncio.create_task(self._set_state(AgentState.LISTENING))
            logger.info("Microphone UNMUTED: audio capture active in LISTENING state.")

        asyncio.create_task(self._emit_event("mic_status", {"muted": new_muted}))
        return new_muted

    async def wake_up(self) -> None:
        """Manually trigger the assistant to start listening immediately."""
        if self.state == AgentState.MUTED:
            self.toggle_mute(False)
        if hasattr(self.microphone, "ensure_started"):
            self.microphone.ensure_started()
        self._speech_active = False
        self._last_speech_time = asyncio.get_running_loop().time()
        if hasattr(self.vad, "reset"):
            self.vad.reset()
        await self._set_state(AgentState.LISTENING)
        await self._emit_event("wake_word_detected", {"word": "manual"})
        logger.info("Manual wake-up triggered: agent set to LISTENING.")

    async def clear_history(self) -> None:
        """Clear conversation history for privacy."""
        self.context.clear_conversation()
        await self._emit_event("history_cleared", {})

    def get_preferences(self) -> Dict[str, Any]:
        """Return current user preferences."""
        return {
            "agent_name": self.context.get_agent_name(),
            "language": self.context.get_language(),
            "voice_name": self.context.user_preferences.get("voice_name", settings.voice_name),
            "persona_mode": self.context.get_persona_mode(),
        }

    async def update_preferences(
        self,
        agent_name: Optional[str] = None,
        language: Optional[str] = None,
        voice_name: Optional[str] = None,
        persona_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update agent name, language preference, voice, or persona and broadcast to UI."""
        if agent_name:
            self.context.set_agent_name(agent_name)
        if language:
            self.context.set_language(language)
        if voice_name:
            self.context.user_preferences["voice_name"] = voice_name
            self.context.save_preferences()
        mode_changed = bool(persona_mode and persona_mode != self.context.get_persona_mode())
        if persona_mode:
            self.context.set_persona_mode(persona_mode)

        prefs = self.get_preferences()
        await self._emit_event("preferences_updated", prefs)

        # If Gemini is active, reconnect to apply new name/persona/language
        if self.gemini.is_connected:
            try:
                await self.gemini.connect(
                    agent_name=prefs["agent_name"],
                    language=prefs["language"],
                    voice_name=prefs["voice_name"],
                    persona_mode=prefs.get("persona_mode")
                )
            except Exception as e:
                logger.warning(f"Could not reconnect Gemini with new preferences: {e}")
        logger.info(f"Preferences updated: {prefs}")
        return prefs

    def get_state(self) -> str:
        """Return current agent state as string."""
        return self.state.name

    def get_status(self) -> Dict[str, Any]:
        """Return a full status snapshot."""
        return {
            "state": self.state.name,
            "running": self._running,
            "gemini_connected": self.gemini.is_connected,
            "mic_active": self.microphone.is_active,
            "speaker_playing": self.speaker.is_playing,
            "wake_word_enabled": self.wake_word.enabled,
            "agent_name": self.context.get_agent_name(),
            "language": self.context.get_language(),
            "preferences": self.get_preferences(),
            "session": self.context.session_state,
        }

    def get_context_summary(self) -> Dict[str, Any]:
        """Return the context manager's full snapshot."""
        return self.context.get_context_summary()
