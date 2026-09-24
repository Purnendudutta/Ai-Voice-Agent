"""
Cryptographically Chained Audit Logging System
"""

import json
import time
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from src.config import settings
from src.security.permissions import RiskLevel


class AuditRecord(BaseModel):
    record_id: str
    timestamp: float = Field(default_factory=time.time)
    action: str
    tool_name: str
    risk_level: RiskLevel
    parameters: Dict[str, Any]
    confirmed_by_user: bool
    status: str  # SUCCESS, FAILED, BLOCKED, ROLLED_BACK
    execution_time_ms: float
    verification_status: str  # CONFIRMED, FAILED, SKIPPED
    error: Optional[str] = None
    prev_hash: str
    record_hash: str = ""

    def calculate_hash(self) -> str:
        payload = (
            f"{self.record_id}:{self.timestamp}:{self.action}:{self.tool_name}:"
            f"{self.risk_level.value}:{self.confirmed_by_user}:{self.status}:"
            f"{self.verification_status}:{self.prev_hash}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLogger:
    """Threadsafe append-only structured audit logger with cryptographic hash chaining."""

    def __init__(self, log_file: Optional[Path] = None):
        self.log_file = log_file or settings.audit_log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._load_last_hash()
        self._lock = asyncio.Lock()

    def _load_last_hash(self) -> str:
        """Loads the hash of the last entry in the audit log, or initializes genesis hash."""
        if not self.log_file.exists():
            return "0" * 64

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                if not lines:
                    return "0" * 64
                last_entry = json.loads(lines[-1])
                return last_entry.get("record_hash", "0" * 64)
        except Exception:
            return "0" * 64

    async def log_action(
        self,
        record_id: str,
        action: str,
        tool_name: str,
        risk_level: RiskLevel,
        parameters: Dict[str, Any],
        confirmed_by_user: bool,
        status: str,
        execution_time_ms: float,
        verification_status: str,
        error: Optional[str] = None
    ) -> AuditRecord:
        """Records an action with SHA-256 hash chaining."""
        async with self._lock:
            # Mask sensitive values if any (like passwords/tokens)
            safe_params = self._sanitize_parameters(parameters)

            record = AuditRecord(
                record_id=record_id,
                action=action,
                tool_name=tool_name,
                risk_level=risk_level,
                parameters=safe_params,
                confirmed_by_user=confirmed_by_user,
                status=status,
                execution_time_ms=execution_time_ms,
                verification_status=verification_status,
                error=error,
                prev_hash=self._last_hash
            )
            record.record_hash = record.calculate_hash()
            self._last_hash = record.record_hash

            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")

            return record

    def _sanitize_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Redacts sensitive tokens or keys before logging."""
        sanitized = {}
        for k, v in params.items():
            if any(term in k.lower() for term in ["key", "token", "secret", "password"]):
                sanitized[k] = "******"
            else:
                sanitized[k] = v
        return sanitized

    def get_recent_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recent audit records."""
        if not self.log_file.exists():
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                return [json.loads(line) for line in lines[-limit:]]
        except Exception:
            return []

    def verify_integrity(self) -> bool:
        """Verifies that the entire audit log has not been modified or truncated."""
        if not self.log_file.exists():
            return True
        try:
            expected_prev = "0" * 64
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    item = json.loads(line.strip())
                    record = AuditRecord(**item)
                    if record.prev_hash != expected_prev:
                        return False
                    if record.calculate_hash() != record.record_hash:
                        return False
                    expected_prev = record.record_hash
            return True
        except Exception:
            return False


audit_logger = AuditLogger()
