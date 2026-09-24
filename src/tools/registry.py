"""
Extensible Tool Registry and Robust Execution Pipeline
"""

import time
import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable, Awaitable
from pydantic import ValidationError

from src.tools.base import BaseTool, ToolResult
from src.security.permissions import permission_manager, RiskLevel
from src.security.audit_logger import audit_logger
from src.security.rate_limiter import global_rate_limiter

logger = logging.getLogger("ToolRegistry")


class ToolExecutionError(Exception):
    pass


class ToolRegistry:
    """Central registry and execution coordinator for all assistant tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        # Hook for UI/IPC updates
        self.on_tool_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

    def register(self, tool: BaseTool) -> None:
        """Registers a tool in the registry."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tool registration: {tool.name}")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} [Risk: {tool.risk_level.value}]")

    def unregister(self, tool_name: str) -> None:
        self._tools.pop(tool_name, None)

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        return self._tools.get(tool_name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns catalog of all registered tools with risk levels and schemas."""
        catalog = []
        for name, tool in self._tools.items():
            catalog.append({
                "name": name,
                "description": tool.description,
                "risk_level": tool.risk_level.value,
                "timeout": tool.timeout,
                "schema": tool.parameters_schema.model_json_schema()
            })
        return catalog

    def get_gemini_declarations(self) -> List[Dict[str, Any]]:
        """Exports all registered tools into Gemini Live API function declarations."""
        return [tool.to_gemini_declaration() for tool in self._tools.values()]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        client_id: str = "orchestrator",
        task_id: Optional[str] = None
    ) -> ToolResult:
        """
        Executes a tool through the full enterprise pipeline:
        1. Tool lookup
        2. Rate limiting check
        3. Schema validation & pre-execution validation
        4. Permission check & user confirmation (if HIGH_RISK or CRITICAL)
        5. Execution with timeout & retry policy
        6. Post-execution verification
        7. Rollback if verification fails
        8. Audit logging & UI event notification
        """
        start_time = time.time()
        record_id = f"tool_{int(start_time * 1000)}"

        # 1. Lookup
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' is not registered in the system.",
                execution_time_ms=0.0
            )

        # Notify UI of tool execution started
        await self._emit_event({
            "type": "tool_started",
            "task_id": task_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_level": tool.risk_level.value
        })

        # 2. Rate limiting
        if not await global_rate_limiter.acquire(client_id):
            err_msg = f"Rate limit exceeded for tool execution: {tool_name}"
            await audit_logger.log_action(
                record_id=record_id,
                action=f"execute_{tool_name}",
                tool_name=tool_name,
                risk_level=tool.risk_level,
                parameters=arguments,
                confirmed_by_user=False,
                status="BLOCKED",
                execution_time_ms=0.0,
                verification_status="SKIPPED",
                error=err_msg
            )
            return ToolResult(tool_name=tool_name, success=False, error=err_msg)

        # 3. Schema validation
        try:
            parsed_params = tool.parameters_schema(**arguments)
            await tool.validate(parsed_params)
        except ValidationError as ve:
            err_msg = f"Invalid arguments for tool '{tool_name}': {ve}"
            return ToolResult(tool_name=tool_name, success=False, error=err_msg)
        except Exception as ex:
            err_msg = f"Pre-execution validation failed: {ex}"
            return ToolResult(tool_name=tool_name, success=False, error=err_msg)

        # 4. Permission & Explicit Confirmation Check
        confirmed_by_user = False
        if permission_manager.requires_confirmation(tool.risk_level):
            await self._emit_event({
                "type": "confirmation_required",
                "task_id": task_id,
                "tool_name": tool_name,
                "risk_level": tool.risk_level.value,
                "parameters": arguments
            })
            approved = await permission_manager.request_approval(
                tool_name=tool_name,
                risk_level=tool.risk_level,
                action_description=f"Tool '{tool_name}' requests execution with parameters: {arguments}",
                parameters=arguments
            )
            confirmed_by_user = approved
            if not approved:
                err_msg = f"Operation '{tool_name}' was rejected or timed out by user."
                await audit_logger.log_action(
                    record_id=record_id,
                    action=f"execute_{tool_name}",
                    tool_name=tool_name,
                    risk_level=tool.risk_level,
                    parameters=arguments,
                    confirmed_by_user=False,
                    status="REJECTED",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    verification_status="SKIPPED",
                    error=err_msg
                )
                await self._emit_event({
                    "type": "tool_rejected",
                    "task_id": task_id,
                    "tool_name": tool_name
                })
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=err_msg,
                    requires_confirmation=True,
                    confirmation_status="REJECTED"
                )

        # 5. Execution with Retry Policy and Timeout
        retries_remaining = tool.retry_policy.max_retries
        delay = tool.retry_policy.initial_delay_sec
        last_error = None
        exec_data = None
        exec_success = False

        while retries_remaining >= 0:
            try:
                exec_data = await asyncio.wait_for(
                    tool.execute(parsed_params),
                    timeout=tool.timeout
                )
                exec_success = True
                break
            except asyncio.TimeoutError:
                last_error = f"Execution timed out after {tool.timeout}s"
                logger.warning(f"Tool {tool_name} timed out. Retries left: {retries_remaining}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Tool {tool_name} failed: {e}. Retries left: {retries_remaining}")

            if retries_remaining > 0 and tool.retry_policy.is_retryable(last_error or ""):
                await asyncio.sleep(delay)
                delay *= tool.retry_policy.backoff_multiplier
                retries_remaining -= 1
            else:
                break

        exec_time_ms = (time.time() - start_time) * 1000

        if not exec_success:
            await audit_logger.log_action(
                record_id=record_id,
                action=f"execute_{tool_name}",
                tool_name=tool_name,
                risk_level=tool.risk_level,
                parameters=arguments,
                confirmed_by_user=confirmed_by_user,
                status="FAILED",
                execution_time_ms=exec_time_ms,
                verification_status="FAILED",
                error=last_error
            )
            await self._emit_event({
                "type": "tool_failed",
                "task_id": task_id,
                "tool_name": tool_name,
                "error": last_error
            })
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=last_error,
                execution_time_ms=exec_time_ms,
                verification_status="FAILED"
            )

        # 6. Post-execution Verification
        verif_confirmed, verif_details = await tool.verify(parsed_params, exec_data)
        rolled_back = False

        # 7. Rollback if verification fails
        if not verif_confirmed:
            logger.warning(f"Verification failed for {tool_name}: {verif_details}. Attempting rollback...")
            try:
                rolled_back = await tool.rollback(parsed_params, exec_data)
            except Exception as rb_ex:
                logger.error(f"Rollback failed for {tool_name}: {rb_ex}")

        # 8. Audit Logging & Notification
        final_status = "SUCCESS" if verif_confirmed else "VERIFICATION_FAILED"
        if rolled_back:
            final_status = "ROLLED_BACK"

        await audit_logger.log_action(
            record_id=record_id,
            action=f"execute_{tool_name}",
            tool_name=tool_name,
            risk_level=tool.risk_level,
            parameters=arguments,
            confirmed_by_user=confirmed_by_user,
            status=final_status,
            execution_time_ms=exec_time_ms,
            verification_status="CONFIRMED" if verif_confirmed else "FAILED",
            error=verif_details if not verif_confirmed else None
        )

        result = ToolResult(
            tool_name=tool_name,
            success=verif_confirmed,
            data=exec_data,
            error=verif_details if not verif_confirmed else None,
            execution_time_ms=exec_time_ms,
            verification_status="CONFIRMED" if verif_confirmed else "FAILED",
            verification_details=verif_details,
            rolled_back=rolled_back,
            requires_confirmation=permission_manager.requires_confirmation(tool.risk_level),
            confirmation_status="APPROVED" if confirmed_by_user else None
        )

        await self._emit_event({
            "type": "tool_completed",
            "task_id": task_id,
            "tool_name": tool_name,
            "success": verif_confirmed,
            "verification_status": result.verification_status,
            "execution_time_ms": exec_time_ms,
            "result_data": str(exec_data)[:200]
        })

        return result

    async def _emit_event(self, event: Dict[str, Any]) -> None:
        if self.on_tool_event:
            try:
                await self.on_tool_event(event)
            except Exception as e:
                logger.error(f"Error in tool event listener: {e}")


tool_registry = ToolRegistry()
