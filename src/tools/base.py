"""
Base Tool Specification, Execution Result, and Retry Policy
"""

import abc
import asyncio
import time
from typing import Type, Dict, Any, Optional, Tuple, List
from pydantic import BaseModel, Field
from src.security.permissions import RiskLevel


class RetryPolicy(BaseModel):
    """Configurable retry policy with exponential backoff."""
    max_retries: int = 2
    initial_delay_sec: float = 0.5
    backoff_multiplier: float = 2.0
    retryable_error_keywords: List[str] = Field(
        default_factory=lambda: ["timeout", "temporary", "busy", "locked", "not ready"]
    )

    def is_retryable(self, error_message: str) -> bool:
        err_lower = error_message.lower()
        return any(keyword in err_lower for keyword in self.retryable_error_keywords)


class ToolResult(BaseModel):
    """Strongly typed output of a tool invocation."""
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    verification_status: str = "SKIPPED"  # CONFIRMED, FAILED, SKIPPED
    verification_details: str = ""
    rolled_back: bool = False
    requires_confirmation: bool = False
    confirmation_status: Optional[str] = None


class BaseTool(abc.ABC):
    """
    Abstract Base Class for every assistant tool.
    Guarantees typed schemas, permission levels, validation, execution,
    verification, timeout, retry policy, and optional rollback.
    """

    name: str
    description: str
    risk_level: RiskLevel
    parameters_schema: Type[BaseModel]
    timeout: float = 15.0
    retry_policy: RetryPolicy = RetryPolicy()

    async def validate(self, params: BaseModel) -> None:
        """
        Pre-execution semantic validation.
        Override to verify preconditions before running.
        Raises ValueError if invalid.
        """
        pass

    @abc.abstractmethod
    async def execute(self, params: BaseModel) -> Any:
        """
        Primary execution routine. Must be idempotent where feasible.
        """
        pass

    async def verify(self, params: BaseModel, result: Any) -> Tuple[bool, str]:
        """
        Post-execution verification probe.
        Returns (confirmed: bool, details: str).
        """
        return True, "Default verification: action completed without unhandled exceptions."

    async def rollback(self, params: BaseModel, result: Any) -> bool:
        """
        Optional rollback/undo handler called if execution succeeds but verification fails.
        """
        return False

    def to_gemini_declaration(self) -> Dict[str, Any]:
        """Converts tool name, description, and Pydantic schema into Gemini FunctionDeclaration format."""
        schema_dict = self.parameters_schema.model_json_schema()
        # Clean schema for Gemini format
        properties = {}
        required = schema_dict.get("required", [])

        for prop_name, prop_def in schema_dict.get("properties", {}).items():
            prop_type = prop_def.get("type", "string").upper()
            if prop_type == "INTEGER":
                gemini_type = "INTEGER"
            elif prop_type == "NUMBER":
                gemini_type = "NUMBER"
            elif prop_type == "BOOLEAN":
                gemini_type = "BOOLEAN"
            elif prop_type == "ARRAY":
                gemini_type = "ARRAY"
            elif prop_type == "OBJECT":
                gemini_type = "OBJECT"
            else:
                gemini_type = "STRING"

            item = {
                "type": gemini_type,
                "description": prop_def.get("description", prop_name)
            }
            if "enum" in prop_def:
                item["enum"] = prop_def["enum"]

            if gemini_type == "ARRAY":
                raw_items = prop_def.get("items", {})
                raw_item_type = raw_items.get("type", "string").upper()
                if raw_item_type == "INTEGER":
                    item_type = "INTEGER"
                elif raw_item_type == "NUMBER":
                    item_type = "NUMBER"
                elif raw_item_type == "BOOLEAN":
                    item_type = "BOOLEAN"
                else:
                    item_type = "STRING"
                item["items"] = {"type": item_type}

            properties[prop_name] = item

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
                "required": required
            }
        }
