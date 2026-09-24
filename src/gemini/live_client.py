import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
import logging
from pydantic import BaseModel

from google import genai
from google.genai import types

from src.config import settings
from src.tools.registry import tool_registry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Nova, an AI Voice Desktop Assistant for Windows.
You can converse naturally and control the user's computer via function calling when asked.

IMPORTANT INSTRUCTIONS:
1. ONLY call tools that match what the user explicitly requested in their latest message.
2. For conversational questions, explanations, greetings, or chat (e.g. "what is AI", "how are you", "please talk to me", "stop"), respond with conversational speech. Do NOT call open_browser_url or any other tool unless the user explicitly requested to open a website or search the web.
3. To open desktop applications (e.g. "open calculator", "open notepad", "open vs code", "open file manager"), call 'launch_application' with the application name.
4. Only call 'open_browser_url' when the user explicitly asks to open a specific website or URL (e.g. "open youtube", "open github.com").
5. Never repeat previous tool calls unless the user explicitly asks again.
6. When a tool finishes, confirm what was done briefly and concisely.
"""

class ToolCallInfo(BaseModel):
    """Information about a tool call requested by the model."""
    name: str
    args: Dict[str, Any]

class GeminiResponse(BaseModel):
    """Parsed response from the Gemini Live API."""
    audio_data: Optional[bytes] = None
    input_transcript: Optional[str] = None
    output_transcript: Optional[str] = None
    interrupted: bool = False
    tool_call: Optional[ToolCallInfo] = None
    tool_call_id: Optional[str] = None

class GeminiLiveClient:
    """Client for connecting to the Gemini Live API."""

    def __init__(self, max_retries: int = 3):
        """Initialize the Gemini Live client."""
        self.max_retries = max_retries
        self.api_key = settings.gemini_api_key
        if self.api_key and self.api_key != "your_gemini_api_key_here":
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Error creating genai.Client: {e}")
                self.client = None
        else:
            self.client = None

        self.session = None
        self._session_cm = None
        self.is_connected = False
        self.connection_error: Optional[Exception] = None

    async def connect(self) -> None:
        """Establish a live session with the Gemini API with retry logic."""
        if not self.client:
            raise RuntimeError("GEMINI_API_KEY is not set or valid.")
        retries = 0
        while retries <= self.max_retries:
            try:
                tools = []
                declarations = tool_registry.get_gemini_declarations()
                if declarations:
                    tools = [
                        types.Tool(
                            function_declarations=[
                                types.FunctionDeclaration(**d) for d in declarations
                            ]
                        )
                    ]

                config = types.LiveConnectConfig(
                    response_modalities=[types.Modality.AUDIO],
                    system_instruction=types.Content(
                        parts=[types.Part(text=SYSTEM_PROMPT)]
                    ),
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=settings.voice_name
                            )
                        )
                    ),
                    tools=tools
                )

                self._session_cm = self.client.aio.live.connect(
                    model=settings.gemini_live_model, 
                    config=config
                )
                self.session = await self._session_cm.__aenter__()
                
                self.is_connected = True
                self.connection_error = None
                logger.info("Connected to Gemini Live API")
                return
            except Exception as e:
                self.connection_error = e
                logger.error(f"Failed to connect to Gemini Live API: {e} (attempt {retries + 1})")
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(2 ** retries)
                else:
                    raise

    async def disconnect(self) -> None:
        """Cleanly close the connection."""
        if self.is_connected and self._session_cm:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error disconnecting from Gemini Live API: {e}")
            self.session = None
            self._session_cm = None
            self.is_connected = False
            logger.info("Disconnected from Gemini Live API")

    async def send_audio(self, chunk: bytes) -> None:
        """Send audio data to the Gemini Live session."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Not connected to Gemini Live API")
        await self.session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type='audio/pcm;rate=16000')
        )

    async def send_text(self, text: str) -> None:
        """Send text data to the Gemini Live session."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Not connected to Gemini Live API")
        await self.session.send_realtime_input(text=text)

    async def receive_responses(self) -> AsyncGenerator[GeminiResponse, None]:
        """Receive and parse responses from the Gemini Live session."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Not connected to Gemini Live API")
            
        try:
            async for response in self.session.receive():
                gemini_response = GeminiResponse()
                
                if response.server_content:
                    if response.server_content.model_turn and response.server_content.model_turn.parts:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                gemini_response.audio_data = part.inline_data.data
                    
                    if response.server_content.input_transcription and response.server_content.input_transcription.text:
                        gemini_response.input_transcript = response.server_content.input_transcription.text
                    
                    if response.server_content.output_transcription and response.server_content.output_transcription.text:
                        gemini_response.output_transcript = response.server_content.output_transcription.text
                    
                    if response.server_content.interrupted:
                        gemini_response.interrupted = True

                if response.tool_call and response.tool_call.function_calls:
                    for fc in response.tool_call.function_calls:
                        call_resp = gemini_response.model_copy()
                        call_resp.tool_call = ToolCallInfo(
                            name=fc.name,
                            args=fc.args or {}
                        )
                        call_resp.tool_call_id = getattr(fc, 'id', None)
                        yield call_resp
                else:
                    yield gemini_response
        except Exception as e:
            logger.error(f"Error receiving from Gemini Live API: {e}")
            self.connection_error = e
            self.is_connected = False
            raise

    async def send_tool_response(self, function_responses: list) -> None:
        """Send a tool response back to the Gemini Live session."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Not connected to Gemini Live API")
        await self.session.send_tool_response(function_responses=function_responses)
