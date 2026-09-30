# SHRUTI - Intelligent Voice Desktop Agent: Architecture

SHRUTI is a production-grade, interruptible, observable desktop agent powered by the **Gemini Live WebSocket API** (`gemini-3.1-flash-live-preview`), bidirectional raw PCM audio streaming, an extensible typed Tool Registry, secure local IPC, and an action verification engine.

---

## 1. System Architecture Overview

```mermaid
flowchart TD
    subgraph Audio_Layer["Audio & Voice Pipeline"]
        MIC["Microphone (sounddevice)\n16kHz 16-bit PCM Mono"] --> VAD["Voice Activity Detection\n(RMS Energy & Threshold)"]
        VAD --> WAKE["Wake Word Engine\n(OpenWakeWord / Fallback)"]
        WAKE --> ORCH["Agent Orchestrator\n(State Machine & Coordination)"]
        ORCH --> SPK["Speaker Output (sounddevice)\n24kHz 16-bit PCM Mono"]
    end

    subgraph Cloud_AI["Google Gemini Live"]
        ORCH <-->|"Bi-directional WebSocket\n(gemini-3.1-flash-live-preview)"| GEMINI["Gemini Live Session\n(Native Audio + Function Calling)"]
    end

    subgraph Security_Layer["Security & IPC Layer"]
        ORCH --> SEC["Security & Policy Engine"]
        SEC -->|"HMAC Auth & Rate Limiting"| IPC["Secure Local IPC Server\n(FastAPI / WebSockets / Port 8000)"]
        SEC --> AUDIT[("Cryptographic Audit Log\nSHA-256 Hash Chain")]
        SEC --> CONFIRM{"Explicit Confirmation\n(HIGH_RISK / CRITICAL)"}
    end

    subgraph Desktop_Execution["Tool Registry & Desktop Automation"]
        ORCH --> REG["Tool Registry\n(Typed Pydantic Schemas)"]
        CONFIRM -->|Approved| REG
        REG --> TOOLS["Desktop Tools\n(Apps, Windows, Files, Mouse, Keyboard)"]
        TOOLS --> VERIF["Verification Engine\n(OS State Probes: Win32 / psutil / Filesystem)"]
        VERIF -->|Confirmed| AUDIT
        VERIF -->|Failed| ROLLBACK["Rollback Engine\n(Restore Backup / Undo Action)"]
    end

    subgraph User_Interface["Web Desktop UI"]
        IPC <-->|"Real-Time Events & Commands"| UI["Glassmorphism Dashboard\n(Transcript, Timeline, Tool Logs, Audio Wave)"]
    end
```

---

## 2. Core Concepts & Subsystems

### 2.1 Audio Pipeline & Low Latency
- **Input**: `MicrophoneStream` continuously buffers 16kHz, 16-bit, little-endian mono PCM audio (`audio/pcm;rate=16000`).
- **VAD**: `VoiceActivityDetector` measures RMS energy against an adaptive noise threshold, detecting `SPEECH_START`, `SPEECH_CONTINUE`, `SPEECH_END`, and `SILENCE`.
- **Wake Word**: `WakeWordDetector` listens for target activation phrases ("Jarvis", "Gemini", "Computer", "Shruti") and switches the state from `IDLE` to `LISTENING`.
- **Output**: `SpeakerOutput` plays 24kHz raw PCM audio streamed directly from Gemini Live.
- **Barge-In / Interruption**: When user speech is detected while the agent is speaking or Gemini emits `server_content.interrupted`, the speaker buffer is cleared instantly (<10ms latency) and the state transitions back to `LISTENING`.

### 2.2 Gemini Live Integration
- Utilizes the official `google-genai` SDK (`gemini-3.1-flash-live-preview`).
- Synchronous function calling: Tool declarations are dynamically exported from the `ToolRegistry` and passed during connection setup.
- Session Management & Resumption: Exponential backoff reconnects automatically on network drops.
- **Local Degraded Mode**: If offline or no API key is supplied, `LocalPlanner` decomposes natural language requests into multi-step DAGs and executes them with local TTS feedback (`pyttsx3`).

### 2.3 Tool Registry & Execution Pipeline
Every tool implements `BaseTool`:
1. **Schema Validation**: Strongly typed Pydantic parameters.
2. **Permission Check**: Risk levels (`READ_ONLY`, `LOW_RISK`, `MODERATE`, `HIGH_RISK`, `CRITICAL`).
3. **Execution**: Sandboxed execution with timeout and bounded retries.
4. **Verification**: Never assumes success. Probes OS state (process list, active window hwnd, filesystem attributes).
5. **Rollback**: Automatic recovery if verification fails (e.g. restoring backup copy of modified/deleted files).
6. **Audit**: Appended to tamper-evident SHA-256 hash-chained log.

---

## 3. Request Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Mic as MicrophoneStream
    participant Orch as AgentOrchestrator
    participant Gemini as Gemini Live API
    participant Registry as ToolRegistry
    participant OS as Windows OS
    participant Spk as SpeakerOutput

    User->>Mic: "Open VS Code and check Git status"
    Mic->>Orch: Raw PCM 16kHz Chunks
    Orch->>Gemini: send_realtime_input(audio)
    Gemini-->>Orch: ToolCall(launch_application, app_name='code')
    Orch->>Registry: execute_tool('launch_application')
    Registry->>OS: Launch 'code.exe'
    Registry->>OS: Verify 'code.exe' in running processes
    OS-->>Registry: Verified (PID 14220)
    Registry-->>Orch: ToolResult(success=True, verification='CONFIRMED')
    Orch->>Gemini: send_tool_response(result)
    Gemini-->>Orch: Audio chunks ("VS Code is open. Checking git status...")
    Orch->>Spk: Play 24kHz Audio
    Spk-->>User: Spoken Response
```
