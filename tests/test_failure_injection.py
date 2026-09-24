import pytest
import asyncio
from typing import Dict, Any, Tuple
from pydantic import BaseModel
from src.tools.base import BaseTool, ToolResult, RetryPolicy
from src.tools.registry import ToolRegistry
from src.security.permissions import RiskLevel


class FailingInput(BaseModel):
    fail_count: int = 1
    error_type: str = "temporary"


class SimulatedFlakyTool(BaseTool):
    """Tool that fails a predetermined number of times before succeeding or failing."""
    name = "simulated_flaky_tool"
    description = "A simulated flaky tool for failure injection testing."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = FailingInput
    timeout = 2.0
    retry_policy = RetryPolicy(
        max_retries=2,
        initial_delay_sec=0.05,
        backoff_multiplier=1.5,
        retryable_error_keywords=["temporary", "timeout"]
    )

    def __init__(self):
        super().__init__()
        self.attempts = 0
        self.rollback_called = False

    async def execute(self, params: FailingInput) -> Dict[str, Any]:
        self.attempts += 1
        if self.attempts <= params.fail_count:
            if params.error_type == "timeout":
                await asyncio.sleep(3.0)  # triggers timeout > 2.0
            raise RuntimeError(f"temporary error attempt #{self.attempts}")
        return {"status": "recovered", "attempts": self.attempts}

    async def verify(self, params: FailingInput, result: Any) -> Tuple[bool, str]:
        return True, "Verification successful after recovery."

    async def rollback(self, params: FailingInput, result: Any) -> bool:
        self.rollback_called = True
        return True


class SimulatedUnrecoverableTool(BaseTool):
    """Tool that always fails verification, testing rollback mechanics."""
    name = "simulated_unrecoverable_tool"
    description = "Fails verification to test rollback."
    risk_level = RiskLevel.MODERATE
    parameters_schema = FailingInput

    def __init__(self):
        super().__init__()
        self.rollback_called = False

    async def execute(self, params: FailingInput) -> Dict[str, Any]:
        return {"action": "performed_bad_state"}

    async def verify(self, params: FailingInput, result: Any) -> Tuple[bool, str]:
        return False, "Verification failed: State is corrupted."

    async def rollback(self, params: FailingInput, result: Any) -> bool:
        self.rollback_called = True
        return True


@pytest.mark.asyncio
async def test_flaky_tool_recovers_within_retry_limit():
    registry = ToolRegistry()
    tool = SimulatedFlakyTool()
    registry.register(tool)

    # Fail 1 time, retry recovers on attempt 2 (max_retries is 2)
    result = await registry.execute_tool("simulated_flaky_tool", {"fail_count": 1, "error_type": "temporary"})
    assert result.success is True
    assert result.data["attempts"] == 2
    assert result.verification_status == "CONFIRMED"


@pytest.mark.asyncio
async def test_flaky_tool_exceeds_retry_limit_no_infinite_loop():
    registry = ToolRegistry()
    tool = SimulatedFlakyTool()
    registry.register(tool)

    # Fail 10 times, exceeds max_retries of 2, terminates cleanly
    result = await registry.execute_tool("simulated_flaky_tool", {"fail_count": 10, "error_type": "temporary"})
    assert result.success is False
    assert "temporary error" in result.error
    assert tool.attempts == 3  # initial + 2 retries = 3 attempts total (bounded)


@pytest.mark.asyncio
async def test_unrecoverable_verification_triggers_rollback():
    registry = ToolRegistry()
    tool = SimulatedUnrecoverableTool()
    registry.register(tool)

    result = await registry.execute_tool("simulated_unrecoverable_tool", {"fail_count": 0})
    assert result.success is False
    assert result.verification_status == "FAILED"
    assert result.rolled_back is True
    assert tool.rollback_called is True
