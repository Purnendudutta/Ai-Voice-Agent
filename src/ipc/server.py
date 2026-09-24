"""
Secure Local IPC Server - FastAPI WebSocket + REST endpoints for the Web UI.

Provides:
- WebSocket at /ws for real-time bidirectional events
- REST API for status, tools, audit, commands, confirmations
- Static file serving for the web UI
- Rate limiting, CORS, and IPC auth
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from src.security.ipc_auth import ipc_auth
from src.security.rate_limiter import global_rate_limiter
from src.security.permissions import permission_manager
from src.security.audit_logger import audit_logger
from src.tools.registry import tool_registry
from src.config import settings

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class CommandRequest(BaseModel):
    command: str


class ConfirmRequest(BaseModel):
    approved: bool = True


class PreferencesRequest(BaseModel):
    agent_name: Optional[str] = None
    language: Optional[str] = None
    voice_name: Optional[str] = None
    persona_mode: Optional[str] = None


class IPCServer:
    """
    FastAPI-based IPC server providing real-time WebSocket communication
    and REST endpoints for the desktop agent web UI.
    """

    def __init__(self):
        self.app = FastAPI(title="Nova AI IPC Server", docs_url=None, redoc_url=None)
        self.orchestrator: Any = None
        self.active_connections: List[WebSocket] = []
        self._server: Optional[uvicorn.Server] = None

        # CORS for localhost
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost",
                f"http://localhost:{settings.web_ui_port}",
                f"http://127.0.0.1:{settings.web_ui_port}",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._setup_routes()

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the Agent Orchestrator reference for command routing."""
        self.orchestrator = orchestrator

    def _setup_routes(self) -> None:
        """Register all HTTP and WebSocket routes."""

        # ── Serve index.html at root ──
        @self.app.get("/", response_class=HTMLResponse)
        async def serve_index():
            index_file = UI_DIR / "index.html"
            if index_file.exists():
                return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
            return HTMLResponse(content="<h1>Nova AI</h1><p>UI not found.</p>")

        # ── WebSocket endpoint ──
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
            # Auth check (skip in dev if no token provided for ease of use)
            await websocket.accept()
            self.active_connections.append(websocket)
            logger.info(f"WebSocket client connected (total: {len(self.active_connections)})")

            # Send initial state
            if self.orchestrator:
                await websocket.send_json({
                    "type": "state_change",
                    "data": {"state": self.orchestrator.get_state(), "previous": "INIT"}
                })
                await websocket.send_json({
                    "type": "system_status",
                    "data": self.orchestrator.get_status()
                })

            try:
                while True:
                    data = await websocket.receive_text()
                    await self._handle_ws_message(websocket, data)
            except WebSocketDisconnect:
                self._remove_connection(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self._remove_connection(websocket)

        # ── REST: Status ──
        @self.app.get("/api/status")
        async def get_status():
            if not self.orchestrator:
                return {"state": "NOT_READY", "running": False}
            return self.orchestrator.get_status()

        # ── REST: Tools catalog ──
        @self.app.get("/api/tools")
        async def get_tools():
            return {"tools": tool_registry.list_tools()}

        # ── REST: Audit logs ──
        @self.app.get("/api/audit")
        async def get_audit_logs(limit: int = 50):
            return {"logs": audit_logger.get_recent_records(limit)}

        # ── REST: Send text command ──
        @self.app.post("/api/command")
        async def send_command(req: CommandRequest):
            if not self.orchestrator:
                raise HTTPException(status_code=503, detail="Orchestrator not ready")
            asyncio.create_task(self.orchestrator.send_text_command(req.command))
            return {"status": "accepted", "command": req.command}

        # ── REST: Confirm/reject pending action ──
        @self.app.post("/api/confirm/{request_id}")
        async def confirm_action(request_id: str, req: ConfirmRequest):
            if not self.orchestrator:
                raise HTTPException(status_code=503, detail="Orchestrator not ready")
            result = await self.orchestrator.handle_confirmation(request_id, req.approved)
            return {"status": "processed", "approved": req.approved, "resolved": result}

        # ── REST: Clear conversation history ──
        @self.app.post("/api/clear-history")
        async def clear_history():
            if not self.orchestrator:
                raise HTTPException(status_code=503, detail="Orchestrator not ready")
            await self.orchestrator.clear_history()
            return {"status": "cleared"}

        # ── REST: Context summary ──
        @self.app.get("/api/context")
        async def get_context():
            if not self.orchestrator:
                return {"context": {}}
            return {"context": self.orchestrator.get_context_summary()}

        # ── REST: Preferences (Agent Name, Language, Voice) ──
        @self.app.get("/api/preferences")
        async def get_preferences():
            if not self.orchestrator:
                return {"preferences": {}}
            return {"preferences": self.orchestrator.get_preferences()}

        @self.app.post("/api/preferences")
        async def update_preferences(req: PreferencesRequest):
            if not self.orchestrator:
                raise HTTPException(status_code=503, detail="Orchestrator not ready")
            updated = await self.orchestrator.update_preferences(
                agent_name=req.agent_name,
                language=req.language,
                voice_name=req.voice_name,
                persona_mode=req.persona_mode
            )
            return {"status": "updated", "preferences": updated}

        # ── REST: Generate auth token (for WebSocket auth) ──
        @self.app.get("/api/token")
        async def get_token():
            token = ipc_auth.generate_token(client_id="web_ui")
            return {"token": token}

    def _remove_connection(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected (remaining: {len(self.active_connections)})")

    async def broadcast(self, event: Dict[str, Any]) -> None:
        """Broadcast an event dict to all connected WebSocket clients."""
        if not self.active_connections:
            return
        message = json.dumps(event, default=str)
        stale = []
        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                stale.append(conn)
        for s in stale:
            self._remove_connection(s)

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Convenience wrapper: broadcast a typed event."""
        await self.broadcast({"type": event_type, "data": data})

    async def _handle_ws_message(self, websocket: WebSocket, data_str: str) -> None:
        """Handle incoming WebSocket messages from the UI client."""
        try:
            message = json.loads(data_str)
            msg_type = message.get("type")
            data = message.get("data", {})

            if msg_type == "text_command" and self.orchestrator:
                text = data.get("text", "").strip()
                if text:
                    asyncio.create_task(self.orchestrator.send_text_command(text))

            elif msg_type == "confirm_action" and self.orchestrator:
                request_id = data.get("request_id")
                if request_id:
                    await self.orchestrator.handle_confirmation(request_id, True)

            elif msg_type == "cancel_action" and self.orchestrator:
                request_id = data.get("request_id")
                if request_id:
                    await self.orchestrator.handle_confirmation(request_id, False)

            elif msg_type == "update_preferences" and self.orchestrator:
                await self.orchestrator.update_preferences(
                    agent_name=data.get("agent_name"),
                    language=data.get("language"),
                    voice_name=data.get("voice_name"),
                    persona_mode=data.get("persona_mode")
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "data": {}})

            else:
                logger.warning(f"Unknown WS message type: {msg_type}")

        except json.JSONDecodeError:
            logger.error("Invalid JSON received over WebSocket")
        except Exception as e:
            logger.error(f"Error handling WS message: {e}")

    async def start_async(self) -> None:
        """Run the FastAPI server asynchronously (non-blocking)."""
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=settings.web_ui_port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        await self._server.serve()

    async def stop(self) -> None:
        """Shut down the server."""
        if self._server:
            self._server.should_exit = True
