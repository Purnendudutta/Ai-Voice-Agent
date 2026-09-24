"""
Security Permissions & Risk Management Module
"""

from enum import Enum
from typing import Optional, Dict, Any, Callable, Awaitable
import asyncio
import uuid
import time
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Graduated risk levels for all desktop actions and tools."""
    READ_ONLY = "READ_ONLY"       # Probes, queries, screenshots, window reads
    LOW_RISK = "LOW_RISK"         # Focus window, launch safe browser URL
    MODERATE = "MODERATE"         # Type text, write new scratch file, clipboard write
    HIGH_RISK = "HIGH_RISK"       # Terminate process, modify system files, terminal scripts
    CRITICAL = "CRITICAL"         # File deletion, shutdown, disk modifications


class ConfirmationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ConfirmationRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    risk_level: RiskLevel
    action_description: str
    parameters: Dict[str, Any]
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    status: ConfirmationStatus = ConfirmationStatus.PENDING


class PermissionManager:
    """Manages tool execution permissions, authorization checks, and explicit confirmations."""

    def __init__(self, confirmation_timeout: float = 30.0, auto_approve: bool = False):
        self.confirmation_timeout = confirmation_timeout
        self.auto_approve = auto_approve
        self._pending_confirmations: Dict[str, ConfirmationRequest] = {}
        self._confirmation_futures: Dict[str, asyncio.Future[bool]] = {}
        # Callback to broadcast confirmation requests to UI/Speech
        self.on_confirmation_requested: Optional[Callable[[ConfirmationRequest], Awaitable[None]]] = None

    def requires_confirmation(self, risk_level: RiskLevel) -> bool:
        """Determines if the risk level demands explicit user approval."""
        if self.auto_approve:
            return False
        return risk_level in (RiskLevel.HIGH_RISK, RiskLevel.CRITICAL)

    def set_full_computer_access(self, enabled: bool) -> None:
        """Dynamically enable or disable full autonomous computer access."""
        self.auto_approve = enabled

    async def request_approval(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        action_description: str,
        parameters: Dict[str, Any]
    ) -> bool:
        """
        Creates a confirmation request and suspends until user approves/rejects
        or the confirmation request times out.
        """
        req_id = str(uuid.uuid4())
        req = ConfirmationRequest(
            request_id=req_id,
            tool_name=tool_name,
            risk_level=risk_level,
            action_description=action_description,
            parameters=parameters,
            expires_at=time.time() + self.confirmation_timeout,
            status=ConfirmationStatus.PENDING
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()

        self._pending_confirmations[req_id] = req
        self._confirmation_futures[req_id] = future

        if self.on_confirmation_requested:
            try:
                await self.on_confirmation_requested(req)
            except Exception as e:
                print(f"[PermissionManager] Error dispatching confirmation request: {e}")

        try:
            approved = await asyncio.wait_for(future, timeout=self.confirmation_timeout)
            req.status = ConfirmationStatus.APPROVED if approved else ConfirmationStatus.REJECTED
            return approved
        except asyncio.TimeoutError:
            req.status = ConfirmationStatus.EXPIRED
            return False
        finally:
            self._pending_confirmations.pop(req_id, None)
            self._confirmation_futures.pop(req_id, None)

    def resolve_confirmation(self, request_id: str, approved: bool) -> bool:
        """Called by UI or Voice agent to approve or reject a pending operation."""
        future = self._confirmation_futures.get(request_id)
        if future and not future.done():
            future.set_result(approved)
            if request_id in self._pending_confirmations:
                self._pending_confirmations[request_id].status = (
                    ConfirmationStatus.APPROVED if approved else ConfirmationStatus.REJECTED
                )
            return True
        return False

    def get_pending(self) -> Dict[str, ConfirmationRequest]:
        return {
            k: v for k, v in self._pending_confirmations.items()
            if time.time() < v.expires_at
        }


def _init_permission_manager() -> PermissionManager:
    try:
        from src.config import settings
        auto = bool(settings.full_computer_access and not settings.require_confirmation_for_high_risk)
        return PermissionManager(auto_approve=auto)
    except Exception:
        return PermissionManager(auto_approve=False)


permission_manager = _init_permission_manager()
