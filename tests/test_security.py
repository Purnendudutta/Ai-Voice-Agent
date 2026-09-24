import pytest
import asyncio
from src.security.permissions import RiskLevel, PermissionManager
from src.security.ipc_auth import IPCAuthenticator
from src.security.rate_limiter import RateLimiter
from src.security.sandbox import ExecutionSandbox
from src.security.audit_logger import AuditLogger


def test_risk_level_values():
    assert RiskLevel.READ_ONLY.value == "READ_ONLY"
    assert RiskLevel.LOW_RISK.value == "LOW_RISK"
    assert RiskLevel.MODERATE.value == "MODERATE"
    assert RiskLevel.HIGH_RISK.value == "HIGH_RISK"
    assert RiskLevel.CRITICAL.value == "CRITICAL"


def test_permission_manager_requires_confirmation():
    pm = PermissionManager()
    assert not pm.requires_confirmation(RiskLevel.READ_ONLY)
    assert not pm.requires_confirmation(RiskLevel.LOW_RISK)
    assert not pm.requires_confirmation(RiskLevel.MODERATE)
    assert pm.requires_confirmation(RiskLevel.HIGH_RISK)
    assert pm.requires_confirmation(RiskLevel.CRITICAL)


def test_ipc_authenticator_token():
    auth = IPCAuthenticator(secret_key="test_secret_key_1234567890123456")
    token = auth.generate_token(client_id="desktop_ui", ttl_seconds=3600)
    assert auth.validate_token(token) is True


def test_ipc_authenticator_expired_token():
    auth = IPCAuthenticator(secret_key="test_secret_key_1234567890123456")
    token = auth.generate_token(client_id="desktop_ui", ttl_seconds=-10)
    assert auth.validate_token(token) is False


def test_ipc_authenticator_tampered_token():
    auth = IPCAuthenticator(secret_key="test_secret_key_1234567890123456")
    token = auth.generate_token(client_id="desktop_ui", ttl_seconds=3600)
    tampered = token[:-5] + "aaaaa"
    assert auth.validate_token(tampered) is False


@pytest.mark.asyncio
async def test_rate_limiter():
    limiter = RateLimiter(capacity=2, refill_rate_per_sec=0.1)
    assert await limiter.acquire("user1", cost=1.0) is True
    assert await limiter.acquire("user1", cost=1.0) is True
    assert await limiter.acquire("user1", cost=1.0) is False


def test_execution_sandbox_commands():
    sandbox = ExecutionSandbox()
    valid, _ = sandbox.validate_command("echo hello")
    assert valid is True
    valid, _ = sandbox.validate_command("git status")
    assert valid is True
    valid, _ = sandbox.validate_command("format C:")
    assert valid is False
    valid, _ = sandbox.validate_command("diskpart")
    assert valid is False


@pytest.mark.asyncio
async def test_audit_logger(tmp_path):
    log_file = tmp_path / "audit.jsonl"
    logger = AuditLogger(log_file=log_file)
    rec = await logger.log_action(
        record_id="rec_1",
        action="execute_test",
        tool_name="test_tool",
        risk_level=RiskLevel.LOW_RISK,
        parameters={"query": "test"},
        confirmed_by_user=False,
        status="SUCCESS",
        execution_time_ms=12.5,
        verification_status="CONFIRMED"
    )
    records = logger.get_recent_records()
    assert len(records) == 1
    assert records[0]["action"] == "execute_test"
    assert logger.verify_integrity() is True
